#!/usr/bin/env python3
"""
run_phase1.py — RUNNER / ENTRY-POINT cho Phase 1 (file keo dán)

ĐÂY LÀ THỨ BẠN CÒN THIẾU. Nó trả lời câu hỏi "làm sao chạy collector mà không
phải vào CLI gõ tay": orchestrator điều phối VÒNG ĐỜI, ghép 3 mảnh độc lập:

    topology.build_net()         (Lớp 1) -> tạo `net` chưa start
    topology.start_net()         (Lớp 1) -> start mạng + pingAll
    traffic.start_background_load (Lớp 1) -> bật tải nền SONG SONG
    Collector(net).run()         (Lớp 2) -> thu thập + ghi log

TRIẾT LÝ: runner KHÔNG chứa logic nghiệp vụ (không tự dựng switch, không tự đọc
metric). Nó chỉ ĐIỀU PHỐI THỨ TỰ + đảm bảo DỌN DẸP (try/finally -> net.stop()).
Đây là pattern "composition over monolith".

VÌ SAO try/finally LÀ BẮT BUỘC:
    start_net() trả `net` đã start nhưng KHÔNG tự tắt. Nếu giữa chừng lỗi (hoặc
    bạn Ctrl-C), mà không có finally -> mạng rác (namespace/switch thừa) -> lần
    sau chạy lỗi "RTNETLINK File exists". finally đảm bảo LUÔN net.stop().

CÁCH CHẠY (1 LỆNH DUY NHẤT — không cần vào CLI):
    # terminal 1: controller static (không STP, không flood)
    ryu-manager mininet.controller_static --ofp-tcp-listen-port 6653

    # terminal 2:
    sudo mn -c                                          # dọn mạng cũ
    sudo python3 -m mininet.run_phase1 --duration 60 --scenario flood

    # tùy chọn:
    sudo python3 -m mininet.run_phase1 --scenario normal --duration 30 --clients 5
    sudo python3 -m mininet.run_phase1 --scenario idle   --duration 20  # không traffic
"""

import argparse
import sys

from mininet.log import setLogLevel, info

# import theo package -> chạy bằng `python3 -m mininet.run_phase1` từ thư mục gốc dt4n/
from mininet.topology import build_net, start_net
from mininet import traffic as T
# collector ở LỚP 2 (bridge) — runner là chỗ DUY NHẤT hợp lệ để ghép L1 với L2
from bridge.collector import Collector


def main():
    p = argparse.ArgumentParser(description='DT4N Phase 1 runner (dựng mạng + traffic + collector)')
    # tham số mạng
    p.add_argument('--clients', type=int, default=3)
    p.add_argument('--bw-backbone', type=float, default=20)
    p.add_argument('--bw-bottleneck', type=float, default=5)
    p.add_argument('--delay', type=str, default='2ms')
    p.add_argument('--loss', type=float, default=0)
    p.add_argument('--convergence-timeout', type=float, default=8.0,
                   help='số giây tối đa chờ controller static hội tụ')
    p.add_argument('--stp-wait', type=float, default=None,
                   help='deprecated: alias cho --convergence-timeout, không sleep STP')
    # tham số kịch bản + thu thập
    p.add_argument('--scenario', choices=['idle', 'normal', 'flood'], default='normal',
                   help='idle=không traffic; normal=TCP nền; flood=UDP tốc độ cao')
    p.add_argument('--rate', type=str, default='50M', help='tốc độ UDP khi flood')
    p.add_argument('--duration', type=int, default=60, help='giây thu thập metrics')
    p.add_argument('--interval', type=float, default=1.0, help='chu kỳ polling (giây)')
    p.add_argument('--ping-every', type=int, default=20, help='đo latency mỗi N chu kỳ')
    p.add_argument('--log-path', type=str, default='logs/dt4n_snapshots.jsonl',
                   help='JSONL snapshot log cho validation; mặc định ghi đè mỗi lần chạy')
    p.add_argument('--pretty-log-path', type=str, default='logs/phase1.log',
                   help='log dễ đọc cho người xem demo; mặc định ghi đè mỗi lần chạy')
    args = p.parse_args()
    if args.stp_wait is not None:
        args.convergence_timeout = args.stp_wait

    setLogLevel('info')

    net = None
    load_hosts = ()
    try:
        # ---- 1) DỰNG MẠNG (Lớp 1) ----
        info('\n*** [1/3] Dựng topology + đợi controller static\n')
        net = build_net(clients=args.clients, bw_backbone=args.bw_backbone,
                        bw_bottleneck=args.bw_bottleneck, delay=args.delay,
                        loss=args.loss)
        start_net(net, convergence_timeout=args.convergence_timeout,
                  do_pingall=True)

        # ---- 2) BẬT TRAFFIC NỀN (Lớp 1) — song song với collector ----
        if args.scenario != 'idle':
            info('\n*** [2/3] Bật traffic nền: %s\n' % args.scenario)
            # tải nền nên kéo dài ÍT NHẤT bằng thời gian thu thập
            load_hosts = T.start_background_load(
                net, scenario=args.scenario,
                duration=args.duration + 5, rate=args.rate)
        else:
            info('\n*** [2/3] scenario=idle -> không bật traffic\n')

        # ---- 3) THU THẬP METRICS (Lớp 2) ----
        info('\n*** [3/3] Chạy collector %ds (interval=%.1fs)\n'
             % (args.duration, args.interval))
        col = Collector(net, interval=args.interval,
                        log_path=args.log_path,
                        pretty_log_path=args.pretty_log_path,
                        ping_every=args.ping_every,
                        overwrite=True)
        n = col.run(duration=args.duration)

        info('\n*** XONG. %d snapshot -> %s\n' % (n, args.log_path))
        info('*** Log dễ đọc -> %s\n' % args.pretty_log_path)
        info('*** Kiểm tra nhanh: python3 scenarios/check_snapshots.py %s\n' % args.log_path)

    except KeyboardInterrupt:
        info('\n*** Ctrl-C: dừng sớm, vẫn dọn dẹp...\n')
    finally:
        # ---- DỌN DẸP (LUÔN chạy, kể cả khi lỗi/Ctrl-C) ----
        if load_hosts:
            T.stop_all_iperf(*load_hosts)
        if net is not None:
            info('*** Tắt mạng (net.stop)\n')
            net.stop()


if __name__ == '__main__':
    main()
