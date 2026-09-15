#!/usr/bin/env python3
"""Ryu app for DT4N static multipath forwarding with proxy ARP.

This replaces ryu.app.simple_switch_stp_13 for the fixed triangle topology.
The rule is simple: never flood. IPv4 packets are forwarded by dst IP using a
generated next-hop table, and ARP requests are answered by the controller.
"""

import json
import logging
import os

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.lib import hub
from ryu.lib.packet import arp, ethernet, ether_types, packet
from ryu.ofproto import ofproto_v1_3

from mininet.gen_routes import host_attachment, load_spec, next_hop_table

try:
    from bridge.flow_log import flow_event
except Exception:  # pragma: no cover - Ryu can still run without bridge imports.
    def flow_event(*_args, **_kwargs):
        return None


LOG = logging.getLogger("dt4n.controller")

SPEC_PATH = os.environ.get("DT4N_TOPOLOGY_SPEC", "ditto/topology_spec.json")
ROUTING_PATH = os.environ.get("DT4N_ROUTING_TABLE", "ditto/routing_table.json")
PORT_MAP_PATH = os.environ.get("DT4N_PORT_MAP", "ditto/port_map.json")

PRIO_TABLE_MISS = 0
PRIO_ARP = 1
PRIO_IPV4 = 10

PORT_MAP_RETRIES = 30
PORT_MAP_RETRY_SEC = 0.2


class StaticMultipath(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.spec = load_spec(SPEC_PATH)
        self.spec_dpid_to_name = self._build_dpid_to_name()
        self.primary_routes = self._load_primary_routes()
        self.host_info = host_attachment(self.spec)
        self.ip_to_mac = self._build_ip_to_mac()

        self.datapaths = {}
        self.dpid_to_name = {}
        self.name_to_dpid = {}
        self.port_map = {}
        self.down_edges = set()
        self.installed_routes = {}

        LOG.info("DT4N static controller started")
        LOG.info("spec=%s route_table=%s port_map=%s",
                 SPEC_PATH, ROUTING_PATH, PORT_MAP_PATH)
        LOG.info("IP->MAC: %s", self.ip_to_mac)

    def _load_primary_routes(self):
        generated = next_hop_table(self.spec)
        try:
            with open(ROUTING_PATH, encoding="utf-8") as f:
                loaded = json.load(f).get("next_hop", {})
        except OSError:
            LOG.warning("%s not found; using routes generated from spec",
                        ROUTING_PATH)
            return generated
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            LOG.warning("%s invalid (%s); using routes generated from spec",
                        ROUTING_PATH, exc)
            return generated

        if loaded != generated:
            LOG.warning("%s is stale; using routes generated from spec",
                        ROUTING_PATH)
            return generated

        return loaded

    def _build_ip_to_mac(self):
        """Use the DT4N convention: 10.0.0.N -> 00:00:00:00:00:NN."""
        out = {}
        for host in self.spec.get("hosts", []):
            ip = host["ip"]
            last = int(ip.rsplit(".", 1)[1])
            out[ip] = "00:00:00:00:00:%02x" % last
        return out

    def _build_dpid_to_name(self):
        """Map explicit switch DPID metadata from the topology spec.

        The Phase 1 triangle used canonical names s1/s2/s3, so dpid=1 -> s1
        was enough. The routing calibration topology uses semantic switch names
        such as sA and sF; those must be declared explicitly in the spec.
        """
        out = {}
        for item in self.spec.get("switches", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            dpid = item.get("dpid")
            if not name or dpid is None:
                continue
            try:
                out[int(str(dpid).replace(":", ""), 16)] = name
            except ValueError:
                LOG.warning("Ignoring invalid dpid for %s: %s", name, dpid)
        return out

    def _dpid_to_switch_name(self, dpid):
        """Mininet default: s1 has dpid 1, s2 has dpid 2, etc."""
        return self.spec_dpid_to_name.get(int(dpid), "s%d" % dpid)

    def add_flow(self, dp, priority, match, actions, buffer_id=None):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        instructions = [
            parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)
        ]
        kwargs = {
            "datapath": dp,
            "priority": priority,
            "match": match,
            "instructions": instructions,
            "idle_timeout": 0,
            "hard_timeout": 0,
        }
        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id
        dp.send_msg(parser.OFPFlowMod(**kwargs))

    def del_flows_for_dst(self, dp, ip_dst):
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst=ip_dst,
        )
        dp.send_msg(parser.OFPFlowMod(
            datapath=dp,
            command=ofp.OFPFC_DELETE,
            out_port=ofp.OFPP_ANY,
            out_group=ofp.OFPG_ANY,
            match=match,
            priority=PRIO_IPV4,
        ))
        self.installed_routes.pop((dp.id, ip_dst), None)

    def _set_ipv4_flow(self, dp, ip_dst, out_port):
        key = (dp.id, ip_dst)
        if self.installed_routes.get(key) == out_port:
            return False

        parser = dp.ofproto_parser
        self.del_flows_for_dst(dp, ip_dst)
        match = parser.OFPMatch(
            eth_type=ether_types.ETH_TYPE_IP,
            ipv4_dst=ip_dst,
        )
        self.add_flow(dp, PRIO_IPV4, match,
                      [parser.OFPActionOutput(out_port)])
        self.installed_routes[key] = out_port
        return True

    def _load_port_map_file(self):
        with open(PORT_MAP_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        return {
            sw: {neighbor: int(port) for neighbor, port in ports.items()}
            for sw, ports in raw.items()
        }

    def _refresh_port_map(self, dp):
        name = self.dpid_to_name.get(dp.id)
        if not name:
            return False
        try:
            all_ports = self._load_port_map_file()
        except OSError:
            return False
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            LOG.error("Cannot parse %s: %s", PORT_MAP_PATH, exc)
            return False

        ports = all_ports.get(name)
        if not ports:
            return False

        self.port_map[dp.id] = ports
        LOG.info("%s port_map=%s", name, ports)
        return True

    def _install_routes_when_ready(self, dp):
        for attempt in range(1, PORT_MAP_RETRIES + 1):
            if self._refresh_port_map(dp):
                self._install_routes(dp)
                return
            if attempt == 1:
                LOG.info("Waiting for %s before installing routes", PORT_MAP_PATH)
            hub.sleep(PORT_MAP_RETRY_SEC)

        LOG.error("No port map for %s after %.1fs; routes not installed",
                  self.dpid_to_name.get(dp.id), PORT_MAP_RETRIES * PORT_MAP_RETRY_SEC)

    def _install_routes(self, dp):
        name = self.dpid_to_name.get(dp.id)
        pmap = self.port_map.get(dp.id)
        if not name or not pmap:
            if self._refresh_port_map(dp):
                pmap = self.port_map.get(dp.id)
            else:
                LOG.warning("%s has no port map yet; route install skipped", name)
                return

        routes_by_switch = (next_hop_table(self.spec, excluded_edges=self.down_edges)
                            if self.down_edges else self.primary_routes)
        routes = routes_by_switch.get(name, {})
        changed = 0

        for ip_dst, next_hop in sorted(routes.items()):
            port = pmap.get(next_hop)
            if port is None:
                LOG.error("%s cannot route %s: no port to %s",
                          name, ip_dst, next_hop)
                self.del_flows_for_dst(dp, ip_dst)
                continue
            if self._set_ipv4_flow(dp, ip_dst, port):
                changed += 1
                LOG.info("%s route %s -> %s(port %s)",
                         name, ip_dst, next_hop, port)

        known_ips = {host["ip"] for host in self.spec.get("hosts", [])}
        for ip_dst in sorted(known_ips - set(routes)):
            LOG.warning("%s: %s unreachable; deleting flow", name, ip_dst)
            self.del_flows_for_dst(dp, ip_dst)

        if changed:
            flow_event("CTRL", "FLOW_INSTALL", target=name,
                       detail="%d ipv4 flows changed" % changed)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        ofp = dp.ofproto
        name = self._dpid_to_switch_name(dp.id)

        self.datapaths[dp.id] = dp
        self.dpid_to_name[dp.id] = name
        self.name_to_dpid[name] = dp.id

        for key in list(self.installed_routes):
            if key[0] == dp.id:
                self.installed_routes.pop(key, None)

        LOG.info("Switch %s connected (dpid=%s)", name, dp.id)

        self.add_flow(dp, PRIO_TABLE_MISS, parser.OFPMatch(),
                      [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                              ofp.OFPCML_NO_BUFFER)])
        self.add_flow(dp, PRIO_ARP,
                      parser.OFPMatch(eth_type=ether_types.ETH_TYPE_ARP),
                      [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                              ofp.OFPCML_NO_BUFFER)])

        hub.spawn(self._install_routes_when_ready, dp)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            self._handle_arp(dp, in_port, pkt, eth)
            return

        if eth.ethertype == ether_types.ETH_TYPE_IP:
            LOG.warning("IPv4 PacketIn on %s port %s; refreshing routes",
                        self.dpid_to_name.get(dp.id), in_port)
            self._install_routes(dp)

    def _handle_arp(self, dp, in_port, pkt, eth):
        req = pkt.get_protocol(arp.arp)
        if req is None or req.opcode != arp.ARP_REQUEST:
            return

        target_mac = self.ip_to_mac.get(req.dst_ip)
        if target_mac is None:
            LOG.debug("Ignoring ARP for unknown IP %s", req.dst_ip)
            return

        parser = dp.ofproto_parser
        ofp = dp.ofproto

        reply = packet.Packet()
        reply.add_protocol(ethernet.ethernet(
            ethertype=ether_types.ETH_TYPE_ARP,
            dst=eth.src,
            src=target_mac,
        ))
        reply.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=target_mac,
            src_ip=req.dst_ip,
            dst_mac=req.src_mac,
            dst_ip=req.src_ip,
        ))
        reply.serialize()

        dp.send_msg(parser.OFPPacketOut(
            datapath=dp,
            buffer_id=ofp.OFP_NO_BUFFER,
            in_port=ofp.OFPP_CONTROLLER,
            actions=[parser.OFPActionOutput(in_port)],
            data=reply.data,
        ))
        LOG.debug("Proxy ARP: %s asked for %s -> %s",
                  req.src_ip, req.dst_ip, target_mac)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        desc = msg.desc
        name = self.dpid_to_name.get(dp.id)

        pmap = self.port_map.get(dp.id)
        if not pmap and self._refresh_port_map(dp):
            pmap = self.port_map.get(dp.id)
        if not name or not pmap:
            return

        neighbor = None
        for candidate, port_no in pmap.items():
            if port_no == desc.port_no:
                neighbor = candidate
                break
        if neighbor is None:
            return

        edge = frozenset((name, neighbor))
        is_down = bool(desc.state & ofp.OFPPS_LINK_DOWN)
        target = "link-%s-%s" % tuple(sorted(edge))

        if is_down and edge not in self.down_edges:
            self.down_edges.add(edge)
            LOG.warning("LINK DOWN %s-%s; rerouting", name, neighbor)
            flow_event("CTRL", "REROUTE", target=target,
                       detail="down edge=%s-%s" % (name, neighbor))
        elif (not is_down) and edge in self.down_edges:
            self.down_edges.remove(edge)
            LOG.info("LINK UP %s-%s; rerouting", name, neighbor)
            flow_event("CTRL", "REROUTE", target=target,
                       detail="up edge=%s-%s" % (name, neighbor))
        else:
            return

        for datapath in list(self.datapaths.values()):
            self._install_routes(datapath)
