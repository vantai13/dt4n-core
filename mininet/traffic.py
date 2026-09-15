#!/usr/bin/env python3
"""
traffic.py — Sinh traffic theo KỊCH BẢN cho DT4N (Phase 1, Lesson 1.3) — LỚP 1

Làm mạng "sống" để có gì đó đo. Profile tải nền chạy qua mnexec trong
namespace host, không chiếm shell điều khiển nội bộ của Mininet.
Các hàm debug blocking cũ bên dưới vẫn dùng shell tương tác.

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
    """Legacy saturated TCP diagnostic; ML runners use rate-limited profiles."""
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
        stop_varying_load(h)
        run_host_shell(h, 'pkill -f "[i]perf" 2>/dev/null')
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
def start_background_load(net, scenario='normal', duration=60, rate='50M',
                          normal_rate='2M', server_bg_rate=2.0):
    """Rate-limited normal TCP and high-rate flood UDP on every client.

    Alternate srv1/srv2 destinations to exercise both s1 uplinks. The separate
    srv1->srv2 UDP flow exercises s2-s3. Rates are per client, not aggregate.
    """
    import shlex
    if scenario not in ('normal', 'flood'):
        raise ValueError('scenario must be normal or flood')
    clients = sorted((h for h in net.hosts if h.name.startswith('h')
                      and h.name[1:].isdigit()), key=lambda h: int(h.name[1:]))
    if not clients:
        raise ValueError('traffic profile requires at least one client')
    servers = (net.get('srv1'), net.get('srv2'))
    hosts = tuple(clients) + servers
    stop_all_iperf(*hosts)
    udp = scenario == 'flood'
    for server in servers:
        start_iperf_server(server, udp=udp)
    if server_bg_rate > 0:
        start_server_to_server(net, rate_mbps=server_bg_rate, duration=duration + 5)
    for i, client in enumerate(clients):
        server = servers[i % len(servers)]
        offered_rate = rate if udp else normal_rate
        run_host_shell(client,
            'iperf -c %s -p %d %s -b %s -t %d -i 1 '
            '> /tmp/iperf_cli_%s.log 2>&1 &' %
            (shlex.quote(server.IP()), IPERF_PORT, '-u' if udp else '',
             shlex.quote(offered_rate), duration, client.name))
        print('[traffic] %s: %s -> %s %s @%s per client' %
              (scenario.upper(), client.name, server.name,
               'UDP' if udp else 'TCP', offered_rate))
    return hosts


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


def schedule_segments(schedule, duration):
    """Validate strictly increasing integer boundaries and positive rates."""
    import math
    if not schedule or not isinstance(duration, (int,float)) or not math.isfinite(duration) or duration <= 0 or int(duration) != duration:
        raise ValueError('schedule and positive integer duration required')
    starts = [t for t, _ in schedule]
    if any(not isinstance(t,(int,float)) or not math.isfinite(t) or int(t) != t for t in starts):
        raise ValueError('schedule boundaries must be finite integers')
    if starts[0] != 0 or any(a >= b for a,b in zip(starts,starts[1:])) or starts[-1] >= duration:
        raise ValueError('schedule must start at 0 and increase strictly below duration')
    if any(not math.isfinite(float(r)) or float(r) <= 0 for _,r in schedule):
        raise ValueError('rates must be finite and positive')
    return tuple((float(rate), int((schedule[i+1][0] if i+1 < len(schedule) else duration)-t))
                 for i,(t,rate) in enumerate(schedule))


def stop_varying_load(host):
    """Stop the owning process group so later steps cannot restart iperf."""
    import shlex
    marker = getattr(host, '_dt4n_varying_marker', None)
    if marker:
        quoted = shlex.quote(marker)
        run_host_shell(host, 'if [ -f '+quoted+' ]; then '
            'vary_pid=$(cat '+quoted+'); case "$vary_pid" in '
            '\"\"|*[!0-9]*) ;; *) /bin/kill -TERM -- -"$vary_pid" 2>/dev/null ;; esac; '
            'rm -f '+quoted+'; fi')
        host._dt4n_varying_marker = None


def start_varying_load(net, schedule, duration=60, server_bg_rate=2.0,
                       rotate=True):
    """Tải "bình thường" BIẾN THIÊN theo bậc thang. Lesson 5.3.

    VÌ SAO CẦN: dataset pilot v2 chỉ có normal ở MỘT mức tải cố định
    (2 Mbps/client, std của rxRate ~0.02 Mbps). Một mô hình học "bình thường"
    từ một hằng số sẽ coi MỌI thay đổi tải hợp lệ là bất thường -> false
    positive rate cao ngất ở Phase 6, và bạn sẽ không hiểu tại sao.

    Mô hình cần học "HÌNH DẠNG nào là hợp lệ", không chỉ "con số nào là hợp lệ".

    CÁCH LÀM: iperf v2 không đổi được `-b` giữa dòng, nên ta NỐI TIẾP nhiều
    lần gọi iperf trong MỘT lệnh shell nền. Timing do chính `-t` của iperf
    giữ, không cần thread Python -> không có gì tranh chấp với collector.
    Mỗi lần gọi có ~0.1-0.3 s khởi động, nên bậc thang trôi nhẹ; chấp nhận
    được vì ta cần "tải thay đổi", không cần mốc chính xác tới ms.

    `rotate=True`: xoay lịch theo chỉ số client, để client dùng mức tải khác nhau tại cùng một bậc.
    Ranh giới bậc vẫn đồng thời khi các đoạn có cùng độ dài. Nhảy đồng thời tạo một cú giật gấp 3 lần — một dạng "thundering
    herd" nhân tạo. Xoay đa dạng hóa mức tải từng client; không bảo đảm tải tổng mượt.
    Đặt `rotate=False` nếu bạn MUỐN bậc thang đồng bộ rõ nét để dễ nhìn.
    """
    import shlex
    segments = schedule_segments(schedule, duration)
    clients = sorted((h for h in net.hosts if h.name.startswith('h')
                      and h.name[1:].isdigit()), key=lambda h: int(h.name[1:]))
    if not clients:
        raise ValueError('varying profile requires at least one client')
    servers = (net.get('srv1'), net.get('srv2'))
    hosts = tuple(clients) + servers
    stop_all_iperf(*hosts)
    for server in servers:
        start_iperf_server(server, udp=False)
    if server_bg_rate > 0:
        start_server_to_server(net, rate_mbps=server_bg_rate, duration=duration + 5)

    for i, client in enumerate(clients):
        server = servers[i % len(servers)]
        segs = segments
        if rotate and len(segments) > 1:
            k = i % len(segments)
            segs = segments[k:] + segments[:k]
        parts = [
            'iperf -c %s -p %d -b %gM -t %d -i 1 >> /tmp/iperf_cli_%s.log 2>&1'
            % (shlex.quote(server.IP()), IPERF_PORT, rate, secs, client.name)
            for rate, secs in segs
        ]
        marker = '/tmp/dt4n_varying_%s.pid' % client.name
        client._dt4n_varying_marker = marker
        body = ' ; '.join(parts)
        run_host_shell(client, 'setsid sh -c %s </dev/null >/tmp/iperf_vary_%s.log 2>&1 & echo $! > %s'
                       % (shlex.quote(body), client.name, shlex.quote(marker)))
        print('[traffic] VARYING %s -> %s TCP lịch %s'
              % (client.name, server.name,
                 ','.join('%gM/%ds' % (r, d) for r, d in segs)))
    return hosts


def schedule_with_preroll(schedule, pre_roll):
    """Prefix the first rate and shift the nominal schedule; integer seconds."""
    import math
    if not isinstance(pre_roll,(int,float)) or not math.isfinite(pre_roll) or pre_roll < 0 or int(pre_roll) != pre_roll:
        raise ValueError('pre_roll must be a nonnegative integer number of seconds')
    if not schedule:
        raise ValueError('schedule empty')
    schedule_segments(schedule,int(schedule[-1][0])+1)
    schedule = tuple(tuple(x) for x in schedule)
    if pre_roll == 0:
        return schedule
    return ((0,schedule[0][1]),)+tuple((int(t+pre_roll),r) for t,r in schedule)
