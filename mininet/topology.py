#!/usr/bin/env python3
"""
topology.py — Physical Twin cho DT4N (Phase 1, Lesson 1.2) — LỚP 1

Dựng topology TAM GIÁC có vòng (redundancy):

            s1
           /  \\
   (bw cao)    (bw cao)
         /      \\
        s2 ----- s3   <- link bottleneck (bw thấp) để tạo nghẽn cho ML/auto-scale

  - s1 gắn các CLIENT;  s2 gắn srv1;  s3 gắn srv2  -> load-balance/failover
  - Vòng s1-s2-s3 = đường dự phòng -> demo what-if link down / failover

THAY ĐỔI KIẾN TRÚC (so với bản cũ):
  Tách "DỰNG mạng" (build_net) khỏi "VẬN HÀNH vòng đời" (start/stop).
  - build_net()  -> trả `net` CHƯA start.
  - start_net()  -> start mạng, dump port map, đợi controller static hội tụ.
  - run_cli()    -> chế độ cũ: dựng + mở CLI gõ tay (giữ lại để debug thủ công).
  Lý do: file này thuộc Lớp 1, chỉ lo "mạng trông thế nào". Việc ghép với
  collector (Lớp 2) là trách nhiệm của runner, KHÔNG nhét vào đây -> giữ tách lớp.

Cách chạy ĐỘC LẬP (debug thủ công, KHÔNG có collector):
    # terminal 1: controller static cho vòng (không flood, không STP)
    ryu-manager mininet.controller_static --ofp-tcp-listen-port 6653
    # terminal 2:
    sudo mn -c
    sudo python3 -m mininet.topology            # mở CLI gõ tay
"""

import argparse
import json
import os
import time

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.link import TCLink          # link đặt được bw/delay/loss (Linux tc)
from mininet.node import OVSSwitch, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.tc_filter import install_tc_warning_filter


install_tc_warning_filter()


class TriangleTopo(Topo):
    """Bản VẼ (blueprint) của mạng. Lớp Topo chỉ MÔ TẢ cấu trúc."""

    @staticmethod
    def _host_params(octet):
        return {
            'ip': '10.0.0.%d/8' % octet,
            'mac': '00:00:00:00:00:%02x' % octet,
        }

    def build(self, clients=3,
              bw_backbone=20,        # bw 2 link "xương sống" s1-s2, s1-s3 (Mbps)
              bw_bottleneck=5,       # bw link nghẽn s2-s3 (Mbps) -- CỐ TÌNH thấp
              delay='2ms',
              loss=0):
        # 1) 3 SWITCH
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')
        s3 = self.addSwitch('s3', protocols='OpenFlow13')

        # 2) Nối TAM GIÁC (cái VÒNG)
        self.addLink(s1, s2, bw=bw_backbone, delay=delay)    # xương sống
        self.addLink(s1, s3, bw=bw_backbone, delay=delay)    # xương sống
        self.addLink(s2, s3, bw=bw_bottleneck, delay=delay)  # BOTTLENECK

        # 3) 2 SERVER vào s2, s3
        # IP/MAC match ditto/topology_spec.json. Do not rely on addHost order.
        srv1 = self.addHost('srv1', **self._host_params(4))
        srv2 = self.addHost('srv2', **self._host_params(5))
        self.addLink(srv1, s2, bw=bw_backbone, delay=delay)
        self.addLink(srv2, s3, bw=bw_backbone, delay=delay)

        # 4) N CLIENT vào s1 (THAM SỐ HÓA)
        for i in range(1, clients + 1):
            # Default spec has h1..h3 at .1..3, srv1/srv2 at .4/.5.
            # Extra clients get .6+ and require regenerating topology_spec/routes
            # before they can be used by the static controller.
            octet = i if i <= 3 else i + 2
            h = self.addHost('h%d' % i, **self._host_params(octet))
            self.addLink(h, s1, bw=bw_backbone, delay=delay, loss=loss)


def build_net(clients=3, bw_backbone=20, bw_bottleneck=5,
              delay='2ms', loss=0,
              controller_ip='127.0.0.1', controller_port=6653):
    """DỰNG đối tượng Mininet từ blueprint, nhưng CHƯA start().

    Runner cầm `net` này để điều phối vòng đời: start, bật traffic, chạy
    collector, rồi net.stop() trong finally. Tách như vậy để topology.py chỉ
    mô tả/tạo mạng, không quyết định toàn bộ kịch bản demo.
    """
    topo = TriangleTopo(clients=clients, bw_backbone=bw_backbone,
                        bw_bottleneck=bw_bottleneck, delay=delay, loss=loss)
    net = Mininet(topo=topo, link=TCLink, switch=OVSSwitch,
                  controller=None, autoSetMacs=False, waitConnected=True)
    net.addController('c0', controller=RemoteController,
                      ip=controller_ip, port=controller_port)

    # Stamp configured capacity on runtime links so the twin can reflect it.
    # Keep delay too: TCIntf.config rebuilds qdisc, so bandwidth changes must
    # pass the original delay back or the link silently loses its latency.
    bottleneck = {'s2', 's3'}
    for link in net.links:
        a, b = link.intf1.node.name, link.intf2.node.name
        link.dt4n_bw = bw_bottleneck if {a, b} == bottleneck else bw_backbone
        link.dt4n_delay = delay
    return net


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def remove_stale_port_map(path='ditto/port_map.json'):
    try:
        os.remove(path)
    except OSError:
        pass


def dump_port_map(net, path='ditto/port_map.json'):
    """Write {switch: {neighbor: port_no}} from live Mininet state."""
    ensure_parent_dir(path)
    port_map = {}

    for sw in net.switches:
        port_map[sw.name] = {}
        for intf in sw.intfList():
            link = getattr(intf, 'link', None)
            if link is None:
                continue
            other = link.intf2 if link.intf1 is intf else link.intf1
            port_no = sw.ports.get(intf)
            if port_no is None:
                try:
                    port_no = int(intf.name.rsplit('eth', 1)[1])
                except (IndexError, ValueError):
                    continue
            port_map[sw.name][other.node.name] = int(port_no)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(port_map, f, indent=2, sort_keys=True)
        f.write('\n')

    info('*** Ghi port map runtime -> %s\n' % path)
    return port_map


def wait_convergence(net, timeout=8.0, poll=0.3):
    """Measure controller convergence by pinging h1 -> srv1/srv2."""
    t0 = time.monotonic()
    try:
        src = net.get('h1')
    except KeyError:
        if not net.hosts:
            return True, 0.0
        src = net.hosts[0]

    targets = []
    for name in ('srv1', 'srv2'):
        try:
            targets.append(net.get(name))
        except KeyError:
            pass
    targets = [target for target in targets if target is not src]
    if not targets:
        return True, 0.0

    deadline = t0 + float(timeout)
    while time.monotonic() < deadline:
        ok = True
        for target in targets:
            out = src.cmd('ping -c 1 -W 1 %s' % target.IP())
            if '1 received' not in out or '0% packet loss' not in out:
                ok = False
                break
        if ok:
            elapsed = time.monotonic() - t0
            info('*** Controller static hội tụ sau %.2fs\n' % elapsed)
            return True, elapsed
        time.sleep(poll)

    info('*** CẢNH BÁO: controller chưa hội tụ sau %.1fs\n' % float(timeout))
    return False, float(timeout)


def start_net(net, convergence_timeout=8.0, do_pingall=True,
              dump_ports=True, port_map_path='ditto/port_map.json',
              stp_wait=None):
    """Start mạng đã build, đợi controller static hội tụ, rồi ping nếu cần.

    stp_wait is kept as a deprecated compatibility alias for callers that have
    not been updated yet. It is now a maximum convergence timeout, not a sleep.
    """
    if stp_wait is not None:
        convergence_timeout = stp_wait

    info('*** Bật mạng (tạo namespace, dựng switch, nối link)\n')
    if dump_ports:
        remove_stale_port_map(port_map_path)
    net.start()

    if dump_ports:
        dump_port_map(net, port_map_path)

    ok, secs = wait_convergence(net, timeout=convergence_timeout)
    net.dt4n_convergence_ok = ok
    net.dt4n_convergence_sec = secs

    info('*** Node: %s\n' % ', '.join(sorted(n.name for n in net.values())))

    if do_pingall:
        info('*** pingAll kiểm tra thông mạng\n')
        loss_pct = net.pingAll()
        info('*** pingAll packet loss = %.0f%%\n' % loss_pct)
    return net


def run_cli(convergence_timeout=8.0, do_pingall=True, **kwargs):
    """Chế độ debug thủ công: dựng + mở CLI + tự tắt khi thoát CLI."""
    net = build_net(**kwargs)
    try:
        start_net(net, convergence_timeout=convergence_timeout,
                  do_pingall=do_pingall)
        info('*** Mở CLI. Gõ "exit" hoặc Ctrl-D để thoát.\n')
        CLI(net)
    finally:
        info('*** Tắt mạng và dọn dẹp\n')
        net.stop()


def parse_args():
    p = argparse.ArgumentParser(description='DT4N triangle topology (Phase 1)')
    p.add_argument('--clients', type=int, default=3, help='Số client gắn vào s1')
    p.add_argument('--bw-backbone', type=float, default=20, help='bw link xương sống (Mbps)')
    p.add_argument('--bw-bottleneck', type=float, default=5, help='bw link nghẽn s2-s3 (Mbps)')
    p.add_argument('--delay', type=str, default='2ms', help="độ trễ mỗi link, vd '5ms'")
    p.add_argument('--loss', type=float, default=0, help='tỉ lệ mất gói client link (%%)')
    p.add_argument('--convergence-timeout', type=float, default=8.0,
                   help='số giây tối đa chờ controller static hội tụ')
    p.add_argument('--stp-wait', type=float, default=None,
                   help='deprecated: alias cho --convergence-timeout, không sleep STP')
    p.add_argument('--skip-pingall', action='store_true', help='bỏ qua pingAll sau khi start')
    return p.parse_args()


if __name__ == '__main__':
    setLogLevel('info')
    a = parse_args()
    convergence_timeout = (a.stp_wait if a.stp_wait is not None
                           else a.convergence_timeout)
    run_cli(clients=a.clients, bw_backbone=a.bw_backbone,
            bw_bottleneck=a.bw_bottleneck, delay=a.delay,
            loss=a.loss, convergence_timeout=convergence_timeout,
            do_pingall=not a.skip_pingall)
