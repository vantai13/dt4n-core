#!/usr/bin/env python3
"""Test phần LOGIC THUẦN của collector — KHÔNG cần Mininet.
Chứng minh: parse /proc/net/dev, parse ping, tính rate đều đúng.
Đây cũng là cách bạn nên test ở Lesson 1.5 (PHASE_1.md: 'test collector độc lập')."""

import sys
sys.path.insert(0, 'bridge')
import collector as collector_mod
from collector import (parse_proc_net_dev, parse_proc_net_dev_full,
                       parse_ping, compute_rate,
                       parse_ovs_dump_ports_state, link_configured_bw,
                       canonical_link_key, link_side_a_intf, Collector)

passed = failed = 0
def check(name, got, want):
    global passed, failed
    ok = got == want
    print(("  ✓ " if ok else "  ✗ ") + name + ("" if ok else "  got=%r want=%r" % (got, want)))
    if ok: passed += 1
    else:  failed += 1

print("== TEST 1: parse_proc_net_dev (đọc counter từ /proc/net/dev) ==")
sample = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo:    1234      10    0    0    0     0          0         0    1234      10    0    0    0     0       0          0
 h1-eth0:  98765     321    0    2    0     0          0         0   54321     210    0    3    0     0       0          0
"""
check("rx,tx của h1-eth0", parse_proc_net_dev(sample, 'h1-eth0'), (98765, 54321))
check("interface không tồn tại -> None", parse_proc_net_dev(sample, 'h9-eth0'), None)
switch_sample = """Inter-| Receive | Transmit
 face |bytes packets errs drop fifo frame compressed multicast|bytes packets
 s1-eth2:  4000      4    0    0    0     0          0         0    8000      8
"""
check("rx,tx của switch intf s1-eth2",
      parse_proc_net_dev(switch_sample, 's1-eth2'), (4000, 8000))
ifconfig_like = """h1-eth0: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500
        inet 10.0.0.1  netmask 255.0.0.0  broadcast 10.255.255.255
"""
check("output ifconfig bị trộn -> None, không crash",
      parse_proc_net_dev(ifconfig_like, 'h1-eth0'), None)
check("full counters đọc bytes/packets/drop",
      parse_proc_net_dev_full(sample, 'h1-eth0'),
      {
          'rx_bytes': 98765, 'rx_packets': 321, 'rx_drop': 2,
          'tx_bytes': 54321, 'tx_packets': 210, 'tx_drop': 3,
      })

print("\n== TEST 2: parse_ping (đọc latency + packet loss) ==")
ping_ok = """PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
64 bytes from 10.0.0.1: icmp_seq=1 ttl=64 time=0.052 ms
--- 10.0.0.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2003ms
rtt min/avg/max/mdev = 0.041/0.055/0.078/0.013 ms
"""
r1 = parse_ping(ping_ok)
check("latency avg = 0.055", r1['latency_ms'], 0.055)
check("packet loss = 0%", r1['packet_loss_pct'], 0.0)

ping_loss = """PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
--- 10.0.0.1 ping statistics ---
10 packets transmitted, 9 received, 10% packet loss, time 9012ms
rtt min/avg/max/mdev = 1.2/3.4/9.9/2.1 ms
"""
r2 = parse_ping(ping_loss)
check("loss = 10%", r2['packet_loss_pct'], 10.0)
check("latency avg = 3.4", r2['latency_ms'], 3.4)

ping_dead = """PING 10.0.0.1 (10.0.0.1) 56(84) bytes of data.
--- 10.0.0.1 ping statistics ---
5 packets transmitted, 0 received, 100% packet loss, time 4080ms
"""
r3 = parse_ping(ping_dead)
check("100% loss (host down)", r3['packet_loss_pct'], 100.0)
check("không có rtt -> latency None", r3['latency_ms'], None)

print("\n== TEST 3: compute_rate (tính tốc độ từ delta counter) ==")
check("chu kỳ đầu (prev=None) -> 0", compute_rate(1000, None, 1.0), 0.0)
check("bình thường: (2000-1000)/2s = 500", compute_rate(2000, 1000, 2.0), 500.0)
check("counter reset (now<prev) -> 0", compute_rate(50, 1000, 1.0), 0.0)
check("dt=0 (tránh chia 0) -> 0", compute_rate(2000, 1000, 0), 0.0)
check("dt âm (clock skew) -> 0", compute_rate(2000, 1000, -1), 0.0)

print("\n== TEST 4: parse_ovs_dump_ports_state (trạng thái switch) ==")
ovs_ok = """OFPST_PORT reply (xid=0x2): 3 ports
  port  1: rx pkts=10, bytes=840, drop=0, errs=0, frame=0, over=0, crc=0
"""
ovs_down = """ovs-ofctl: s1: failed to connect to socket (Broken pipe)"""
check("dump-ports hợp lệ -> up", parse_ovs_dump_ports_state(ovs_ok), 'up')
check("dump-ports lỗi kết nối -> down", parse_ovs_dump_ports_state(ovs_down), 'down')
check("output rỗng -> unknown", parse_ovs_dump_ports_state(''), 'unknown')

print("\n== TEST 5: link_configured_bw (đọc capacity link) ==")

class FakeIntf:
    def __init__(self, bw=None):
        self.params = {}
        if bw is not None:
            self.params['bw'] = bw


class FakeLink:
    def __init__(self, bw_attr=None, bw_param=None):
        self.intf1 = FakeIntf(bw_param)
        self.intf2 = FakeIntf()
        if bw_attr is not None:
            self.dt4n_bw = bw_attr


check("ưu tiên dt4n_bw", link_configured_bw(FakeLink(bw_attr=10, bw_param=20)), 10.0)
check("fallback intf.params['bw']", link_configured_bw(FakeLink(bw_param=20)), 20.0)
check("bw không hợp lệ -> None", link_configured_bw(FakeLink(bw_attr='bad')), None)
check("không có bw -> None", link_configured_bw(FakeLink()), None)

print("\n== TEST 6: collect_link traffic counters ==")

class FakeNode:
    def __init__(self, name):
        self.name = name


class FakeLinkIntf:
    def __init__(self, node, name, up=True):
        self.node = node
        self.name = name
        self.params = {}
        self._up = up

    def isUp(self):
        return self._up


class FakeTrafficLink:
    def __init__(self):
        self.intf1 = FakeLinkIntf(FakeNode('s3'), 's3-eth2')
        self.intf2 = FakeLinkIntf(FakeNode('s2'), 's2-eth3')
        self.dt4n_bw = 5


traffic_link = FakeTrafficLink()
check("canonical key sort theo tên node",
      canonical_link_key('s3', 's2'), 'link-s2-s3')
check("side A là intf phía s2",
      link_side_a_intf(traffic_link).name, 's2-eth3')

collector = object.__new__(Collector)
collector._prev_link = {}
old_read_intf_counters = collector_mod.read_intf_counters
old_read_intf_counters_full = collector_mod.read_intf_counters_full
counter_values = [
    {
        'rx_bytes': 1000, 'rx_packets': 10, 'rx_drop': 0,
        'tx_bytes': 2000, 'tx_packets': 20, 'tx_drop': 0,
    },
    {
        'rx_bytes': 1400, 'rx_packets': 14, 'rx_drop': 1,
        'tx_bytes': 2600, 'tx_packets': 26, 'tx_drop': 2,
    },
]

def fake_read_intf_counters_full(_intf):
    return counter_values.pop(0)

collector_mod.read_intf_counters_full = fake_read_intf_counters_full
try:
    no_rate = Collector.collect_link(collector, traffic_link)
    check("collect_link cũ không tự thêm traffic khi now_ts=None",
          'traffic' not in no_rate['features'], True)
    first = Collector.collect_link(collector, traffic_link, now_ts=100.0)
    check("chu kỳ đầu link rate = 0",
          first['features']['traffic']['rxRate'] == 0.0
          and first['features']['traffic']['txRate'] == 0.0, True)
    second = Collector.collect_link(collector, traffic_link, now_ts=102.0)
    check("link rxRate = delta rx / dt",
          second['features']['traffic']['rxRate'], 200.0)
    check("link txRate = delta tx / dt",
          second['features']['traffic']['txRate'], 300.0)
    check("link lossPct = delta drop / (delta tx packets + drop)",
          second['features']['traffic']['lossPct'], 33.333)
finally:
    collector_mod.read_intf_counters = old_read_intf_counters
    collector_mod.read_intf_counters_full = old_read_intf_counters_full

print("\n" + "="*50)
print("KẾT QUẢ: %d pass, %d fail" % (passed, failed))


def test_collector_logic_script_checks_passed():
    assert failed == 0


if __name__ == "__main__":
    sys.exit(0 if failed == 0 else 1)
