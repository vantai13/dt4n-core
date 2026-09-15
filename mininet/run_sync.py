#!/usr/bin/env python3
"""
run_sync.py — Khởi động Phase 2 Lesson 2.3: topology + bootstrap + sync agent.
Chạy 1 lệnh là twin bắt đầu sống. Mininet cần root.

CHẠY:
    # terminal 1: controller static
    ryu-manager mininet.controller_static --ofp-tcp-listen-port 6653
    # terminal 2:
    sudo mn -c
    sudo python3 -m mininet.run_sync --period 1.0
"""
import argparse, sys, time
import logging
import os
from mininet.log import setLogLevel, info

# mininet.log changes the global logger class. Reset it so bridge loggers
# (sync_agent/pusher) do not inherit Mininet's stderr handler.
logging.setLoggerClass(logging.Logger)

try:
    import requests  # noqa: F401
except ImportError:
    raise SystemExit(
        'THIẾU requests trong interpreter này (%s). '
        'Chạy bằng interpreter CÓ requests, ví dụ: '
        'sudo /usr/bin/python3 -m mininet.run_sync --period 1.0'
        % sys.executable)

from mininet.env_runner import EnvRunner
from mininet.cli import CLI
from measurements.measure_latency import main as measure_latency
from measurements.measure_command_latency import main as measure_command_latency


class LockedCLI(CLI):
    """Serialize topology-changing CLI commands with the sync collector."""

    def __init__(self, net, net_lock, *args, **kwargs):
        self.net_lock = net_lock
        super().__init__(net, *args, **kwargs)

    def do_link(self, line):
        with self.net_lock:
            return super().do_link(line)

    def do_switch(self, line):
        with self.net_lock:
            return super().do_switch(line)


def ensure_parent_dir(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)


def configure_file_logging(path, append=False):
    ensure_parent_dir(path)
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    mode = 'a' if append else 'w'
    handler = logging.FileHandler(path, mode=mode, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    for name in ('run_sync', 'env_runner', 'injection', 'sync_agent',
                 'command_agent', 'pusher', 'verify'):
        logger = logging.getLogger(name)
        for existing in list(logger.handlers):
            logger.removeHandler(existing)
            existing.close()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--clients', type=int, default=3)
    p.add_argument('--period', type=float, default=1.0)
    p.add_argument('--convergence-timeout', type=float, default=8.0,
                   help='số giây tối đa chờ controller static hội tụ')
    p.add_argument('--stp-wait', type=float, default=None,
                   help='deprecated: alias cho --convergence-timeout, không sleep STP')
    p.add_argument('--ping-every', type=int, default=20,
                   help='đo latency mỗi N chu kỳ; 0 = tắt ping probe')
    p.add_argument('--reconcile-every', type=int, default=30,
                   help='cứ N chu kỳ gửi full state; 0 = tắt reconciliation')
    p.add_argument('--measure-latency', action='store_true',
                   help='chạy đo sync latency link down rồi thoát, không mở CLI')
    p.add_argument('--measure-command', action='store_true',
                   help='chạy đo command latency end-to-end rồi thoát, không mở CLI')
    p.add_argument('--measure-flow', action='store_true',
                   help='tự bật/tắt link qua Ditto và in latency từng chặng rồi thoát')
    p.add_argument('--trials', type=int, default=10,
                   help='số lần đo khi dùng --measure-latency/--measure-command')
    p.add_argument('--measure-link', default='h1-s1',
                   help='link để đo, dạng nodeA-nodeB, mặc định h1-s1')
    p.add_argument('--flow-timeout', type=float, default=20.0,
                   help='số giây chờ twin phản ánh mỗi lệnh khi --measure-flow')
    p.add_argument('--flow-settle', type=float, default=1.0,
                   help='số giây nghỉ giữa 2 lệnh khi --measure-flow')
    p.add_argument('--flow-reset-log', action='store_true',
                   help='xóa logs/command_flow.log trước khi --measure-flow')
    p.add_argument('--flow-report', default='logs/command_flow_measure.log',
                   help='file report dạng bảng khi --measure-flow')
    p.add_argument('--verify', action='store_true',
                   help='chạy nghiệm thu Phase 2 rồi thoát, không mở CLI')
    p.add_argument('--long', action='store_true',
                   help='khi --verify: chạy consistency dài hạn')
    p.add_argument('--duration', type=float, default=30,
                   help='số phút chạy consistency khi --verify --long')
    p.add_argument('--verify-interval', type=float, default=5,
                   help='số phút giữa mỗi lần check accuracy khi --verify --long')
    p.add_argument('--n-events', type=int, default=20,
                   help='số event link down để đo event fidelity khi --verify')
    p.add_argument('--verify-link', default='h1-s1',
                   help='link để verify event fidelity, dạng nodeA-nodeB')
    p.add_argument('--output', default='docs/phase-2/verify_report.json',
                   help='file JSON output khi --verify')
    p.add_argument('--policy', default='ditto/policy.json')
    p.add_argument('--log-path', default='logs/run_sync.log',
                   help='file log runtime cho sync agent/pusher')
    p.add_argument('--append-log', action='store_true',
                   help='ghi nối tiếp --log-path thay vì tạo log mới')
    p.add_argument('--server-bg-rate', type=float, default=2.0,
                   help='Mbps UDP nền srv1->srv2 qua s2-s3; 0 = tắt')
    a = p.parse_args()
    if a.stp_wait is not None:
        a.convergence_timeout = a.stp_wait
    if sum(bool(x) for x in (a.measure_latency, a.measure_command,
                             a.measure_flow, a.verify)) > 1:
        p.error('--measure-latency, --measure-command, --measure-flow và --verify chỉ chạy một mode mỗi lần')

    configure_file_logging(a.log_path, append=a.append_log)
    log = logging.getLogger('run_sync')
    log.info('Log runtime -> %s', os.path.abspath(a.log_path))

    setLogLevel('info')

    runner = None
    try:
        # 1) component dùng chung cho CLI demo và TwinEnv tương lai.
        log.info('Dung EnvRunner + start Mininet')
        runner = EnvRunner(policy_path=a.policy,
                           sync_period=a.period,
                           clients=a.clients,
                           convergence_timeout=a.convergence_timeout,
                           do_pingall=True,
                           ping_every=a.ping_every,
                           reconcile_every=a.reconcile_every,
                           hard_every=0,
                           mininet_log_level='info')
        runner.start()
        net, net_lock = runner.net, runner.net_lock

        if a.server_bg_rate > 0:
            runner.start_server_background(rate_mbps=a.server_bg_rate)

        if a.measure_latency:
            # Cho sync agent vài chu kỳ đầu để đẩy trạng thái baseline lên Ditto.
            time.sleep(max(2.0, a.period * 3))
            h, s = a.measure_link.split('-', 1)
            measure_latency(net, n_trials=a.trials, h=h, s=s,
                            net_lock=net_lock)
            return

        if a.measure_command:
            # Cần cả Sync Agent (phản ánh state) và Command Agent (thực thi lệnh).
            time.sleep(max(2.0, a.period * 3))
            h, s = a.measure_link.split('-', 1)
            measure_command_latency(net, n_trials=a.trials, h=h, s=s,
                                    net_lock=net_lock)
            return

        if a.measure_flow:
            # Cần cả Sync Agent + Command Agent, rồi tự gửi lệnh qua Ditto.
            from measurements.measure_command_flow import main as measure_flow
            time.sleep(max(2.0, a.period * 3))
            h, s = a.measure_link.split('-', 1)
            measure_flow(net, n_trials=a.trials, h=h, s=s,
                         net_lock=net_lock, settle=a.flow_settle,
                         reflection_timeout=a.flow_timeout,
                         reset_log=a.flow_reset_log,
                         report_path=a.flow_report)
            return

        if a.verify:
            from bridge.verify import run_full_verification
            time.sleep(max(2.0, a.period * 3))
            run_full_verification(net, a, net_lock=net_lock)
            return

        # 4) mở CLI để bạn chạy demo. Twin sống trong lúc bạn gõ lệnh.
        log.info('CLI san sang')
        info('*** CLI sẵn sàng. Thử:  h1 iperf -s &   rồi  h2 iperf -c h1 -t 30\n')
        info('*** Mở Ditto UI xem rxRate nhảy. Gõ exit để dừng.\n')
        setLogLevel('output')
        LockedCLI(net, net_lock)
    finally:
        if runner is not None:
            logging.getLogger('run_sync').info('Tat EnvRunner')
            runner.close()

if __name__ == '__main__':
    main()
