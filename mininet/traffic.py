#!/usr/bin/env python3
"""
traffic.py — Sinh traffic theo KỊCH BẢN cho DT4N (Phase 1, Lesson 1.3) — LỚP 1

Làm mạng "sống" để có gì đó ĐÁNG đo. Mọi lệnh chạy qua host.cmd() => TRONG
namespace của host (điểm bản lề Lesson 1.2). Riêng traffic nền dùng mnexec
để không chiếm shell điều khiển nội bộ của Mininet.

iperf v2 (Mininet đi kèm iperf v2, KHÔNG phải iperf3):
  server: iperf -s        (TCP)  |  iperf -s -u             (UDP)
  client: iperf -c IP -t 10 (TCP)|  iperf -c IP -u -b 50M -t 10  (UDP)
"""

import subprocess
import time

IPERF_PORT = 5001
SERVER_TO_SERVER_PORT = 5002


def run_host_shell(host, command, timeout=3):
    """Run a shell command inside a host namespace without using host.cmd().

    host.cmd() goes through Mininet's single interactive shell for that node. A
    background iperf start can race with collector/command activity and trip
    Mininet's "self.waiting" assertion. mnexec starts a separate process in the
    same namespace, so non-blocking traffic setup does not occupy that shell.
    """
    pid = getattr(host, 'pid', None)
    if pid:
        try:
            p = subprocess.run(
                ['mnexec', '-a', str(pid), 'sh', '-lc', command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=timeout,
                check=False,
            )
            return p.stdout or ''
        except subprocess.TimeoutExpired as e:
            out = e.output or ''
            if isinstance(out, bytes):
                out = out.decode(errors='replace')
            return out
        except OSError:
            pass
    return host.cmd(command)


def start_iperf_server(host, udp=False):
    """Bật iperf server CHẠY NỀN trên `host`."""
    proto = '-u' if udp else ''
    run_host_shell(
        host,
        'iperf -s %s -p %d > /tmp/iperf_srv_%s.log 2>&1 &'
        % (proto, IPERF_PORT, host.name),
    )
    time.sleep(1)   # cho server kịp mở cổng (tránh 'connection refused')
    print('[traffic] iperf server (%s) bật nền trên %s'
          % ('UDP' if udp else 'TCP', host.name))


def traffic_normal(client, server_ip, duration=10):
    """KỊCH BẢN 1: tải nền BÌNH THƯỜNG (TCP) — baseline cho ML."""
    print('[traffic] NORMAL (TCP) %s -> %s trong %ds'
          % (client.name, server_ip, duration))
    out = client.cmd('iperf -c %s -p %d -t %d' % (server_ip, IPERF_PORT, duration))
    print(out)
    return out


def traffic_flood(client, server_ip, rate='50M', duration=10):
    """KỊCH BẢN 2: FLOOD (UDP tốc độ cao). Vượt bw link -> packet loss CAO
    (ĐÚNG dự kiến, không phải bug). jitter+loss nằm ở report PHÍA SERVER."""
    print('[traffic] FLOOD (UDP @%s) %s -> %s trong %ds'
          % (rate, client.name, server_ip, duration))
    out = client.cmd('iperf -c %s -p %d -u -b %s -t %d'
                     % (server_ip, IPERF_PORT, rate, duration))
    print(out)
    return out


def read_server_udp_report(server):
    """Đọc report UDP từ log server (nơi CÓ jitter + packet loss)."""
    out = server.cmd('cat /tmp/iperf_srv_%s.log' % server.name)
    print('[traffic] ==== UDP server report (%s) — jitter + loss ở đây ===='
          % server.name)
    print(out)
    return out


def measure_latency(src, dst_ip, count=10):
    """Đo RTT bằng ping; cũng phát hiện MẤT KẾT NỐI (100% loss)."""
    print('[traffic] PING %s -> %s (%d gói)' % (src.name, dst_ip, count))
    out = src.cmd('ping -c %d %s' % (count, dst_ip))
    print(out)
    return out


def stop_all_iperf(*hosts):
    """Dọn dẹp iperf server nền (tránh chiếm cổng lần chạy sau)."""
    for h in hosts:
        run_host_shell(h, 'pkill -f iperf 2>/dev/null')
    print('[traffic] đã dừng các iperf server')


def start_server_to_server(net, rate_mbps=2, duration=100000):
    """Background srv1 -> srv2 traffic through bottleneck s2-s3.

    This keeps s2-s3 alive in the state vector. With the default 5 Mbps
    bottleneck, 2 Mbps gives util around 0.4 before any reroute.
    """
    srv1 = net.get('srv1')
    srv2 = net.get('srv2')
    rate_text = ('%g' % rate_mbps)

    run_host_shell(
        srv2,
        'iperf -s -u -p %d > /tmp/iperf_srv2_bg.log 2>&1 &'
        % SERVER_TO_SERVER_PORT,
    )
    time.sleep(0.5)
    run_host_shell(
        srv1,
        'iperf -c %s -u -b %sM -p %d -t %d '
        '> /tmp/iperf_srv1_to_srv2_bg.log 2>&1 &'
        % (srv2.IP(), rate_text, SERVER_TO_SERVER_PORT, duration),
    )
    print('[traffic] nền srv1->srv2 UDP @%sMbps qua bottleneck s2-s3'
          % rate_text)
    return (srv1, srv2)


# ---------------------------------------------------------------------------
# HÀM CHO RUNNER GỌI: bật tải nền NON-BLOCKING (chạy ngầm) để collector quan sát.
# Khác demo_scenarios cũ (chạy tuần tự, blocking). Runner cần traffic chạy SONG
# SONG với collector -> phải để client chạy nền.
# ---------------------------------------------------------------------------
def start_background_load(net, scenario='normal', duration=60, rate='50M'):
    """Bật tải NỀN chạy song song với collector.
    Trả về (server_host,) để runner cleanup sau. KHÔNG block.
    - scenario='normal': h1 -> srv1 TCP liên tục
    - scenario='flood' : h1 -> srv1 UDP tốc độ cao (tạo nghẽn/loss)
    """
    h1 = net.get('h1')
    srv1 = net.get('srv1')
    srv2 = net.get('srv2')
    srv1_ip = srv1.IP()

    stop_all_iperf(h1, srv1, srv2)
    bg_hosts = start_server_to_server(net, duration=duration + 5)

    udp = (scenario == 'flood')
    start_iperf_server(srv1, udp=udp)

    if scenario == 'flood':
        # client UDP chạy NỀN (& ) -> không chặn runner
        run_host_shell(
            h1,
            'iperf -c %s -p %d -u -b %s -t %d > /tmp/iperf_cli_h1.log 2>&1 &'
            % (srv1_ip, IPERF_PORT, rate, duration),
        )
        print('[traffic] FLOOD nền: h1 -> srv1 UDP @%s trong %ds' % (rate, duration))
    else:
        run_host_shell(
            h1,
            'iperf -c %s -p %d -t %d > /tmp/iperf_cli_h1.log 2>&1 &'
            % (srv1_ip, IPERF_PORT, duration),
        )
        print('[traffic] NORMAL nền: h1 -> srv1 TCP trong %ds' % duration)

    return tuple({h.name: h for h in (h1, srv1) + bg_hosts}.values())


def demo_scenarios(net):
    """(Giữ lại) Chạy thử cả 2 kịch bản TUẦN TỰ — dùng debug thủ công."""
    h1 = net.get('h1')
    srv1 = net.get('srv1')
    srv1_ip = srv1.IP()

    start_iperf_server(srv1, udp=False)
    traffic_normal(h1, srv1_ip, duration=10)
    stop_all_iperf(srv1)

    start_iperf_server(srv1, udp=True)
    run_host_shell(
        h1,
        'ping -c 12 %s > /tmp/ping_during_flood.log 2>&1 &' % srv1_ip,
    )
    traffic_flood(h1, srv1_ip, rate='50M', duration=10)
    read_server_udp_report(srv1)
    print(h1.cmd('cat /tmp/ping_during_flood.log'))
    stop_all_iperf(srv1)
