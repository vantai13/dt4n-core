#!/usr/bin/env python3
"""Launcher cho chiến dịch Lesson 5.4. CHẠY BẰNG .venv/bin/python.

VÌ SAO CẦN HAI TIẾN TRÌNH:
    Runner cần root (Mininet) và Python hệ thống (module mininet). Ở đó không
    có numpy. Kiểm tra toàn vẹn hợp đồng cần numpy (dựng lại ma trận từ
    ml/design.py). Nên nó phải chạy ở ĐÂY, và phải chạy TRƯỚC — fail-fast:
    hợp đồng lệch thì không được khởi động bất cứ thứ gì.

VÌ SAO `mn -c` CHỈ CHẠY MỘT LẦN VÀ CHẠY Ở ĐÂY:
    `mn -c` giết luôn ryu-manager (xem docstring EnvRunner.close). Nếu runner
    gọi nó giữa các run, controller chết và mọi run sau đó hỏng. Vậy: dọn sạch
    MỘT lần, TRƯỚC khi ryu khởi động. Giữa các run dùng soft_reset/hard_reset.
    Đây là chỗ PHASE_5.md mâu thuẫn với kiến trúc của repo này.
"""
import os
import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

NAMESPACE = os.environ.get('DT4N_CAMPAIGN_NAMESPACE', 'org.dt4n.ml')
RYU = os.environ.get('DT4N_RYU',
                     '/home/ubuntu/miniforge3/envs/sdn_net/bin/ryu-manager')


def main():
    from ml import campaign as C
    from ml.design import git_provenance

    # --- 1. TOÀN VẸN HỢP ĐỒNG: trước tất cả -----------------------------
    contract = C.load_contract()
    integrity = C.check_contract_integrity(contract)      # lệch -> ném, dừng
    print('[launch] hợp đồng khớp: %s' % integrity['stored'][:12])
    print('[launch] %d run, base rate nominal %.4f'
          % (contract['n_runs'], contract['expected_base_rate_test']))

    prov = C.collection_provenance(ROOT)
    if prov['source_dirty']:
        raise SystemExit('Commit source changes before collection: %s' % prov['source_dirty_files'])
    print('[launch] source_clean=True git_dirty=%s commit=%s' % (prov['git_dirty'],prov['git_hash']),flush=True)
    from scripts.generate_ml_dataset import already_done
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='+')
    parser.add_argument('--hard-every', type=int, default=6)
    selected = parser.parse_args().only
    if selected and not set(selected) <= {r['run_id'] for r in contract['runs']}:
        raise SystemExit('Unknown run ID')
    done = {r['run_id']:already_done(r,integrity['stored']) for r in contract['runs']}
    child_env = dict(os.environ, DT4N_NAMESPACE=NAMESPACE, DT4N_CONTRACT_INTEGRITY=json.dumps(integrity))
    if all(done[rid] for rid in (selected or done)):
        return subprocess.run([sys.executable,'scripts/generate_ml_dataset.py']+sys.argv[1:],env=child_env).returncode

    # --- 2. dọn trạng thái Mininet MỘT LẦN, trước khi ryu chạy ----------
    print('[launch] mn -c (một lần duy nhất)')
    subprocess.run(['sudo', '-n', 'mn', '-c'], capture_output=True, check=False)
    subprocess.run(['sudo', '-n', 'pkill', '-9', '-f', '[i]perf'],
                   capture_output=True, check=False)

    # --- 3. controller ---------------------------------------------------
    env = dict(child_env, PYTHONPATH=str(ROOT))
    Path('logs').mkdir(exist_ok=True)
    with open('logs/ml_dataset_controller.log', 'a') as fh:
        controller = subprocess.Popen(
            [RYU, 'mininet.controller_static', '--ofp-tcp-listen-port', '6653'],
            env=env, stdout=fh, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if controller.poll() is not None:
                    raise RuntimeError('Controller exited; see controller log')
                try:
                    with socket.create_connection(('127.0.0.1', 6653), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError('controller không lên sau 20 s')
            print('[launch] controller sẵn sàng, namespace=%s' % NAMESPACE)

            # --- 4. runner dưới sudo + python hệ thống -------------------
            cmd = ['sudo', '-n', 'env',
                   'PYTHONPATH=%s' % ROOT,
                   'DT4N_NAMESPACE=%s' % NAMESPACE,
                   'DT4N_CONTRACT_INTEGRITY=%s' % json.dumps(integrity),
                   '/usr/bin/python3', 'scripts/generate_ml_dataset.py'
                   ] + sys.argv[1:]
            with open('logs/ml_dataset_stdout.log', 'a') as log:
                result = subprocess.run(cmd, env=env, stdout=log,
                                        stderr=subprocess.STDOUT)
            print('[launch] runner exit=%d' % result.returncode)
            print('[launch] log: logs/ml_dataset_stdout.log')
            return result.returncode
        finally:
            controller.terminate()
            try:
                controller.wait(timeout=10)
            except subprocess.TimeoutExpired:
                controller.kill()
                controller.wait()


if __name__ == '__main__':
    raise SystemExit(main())
