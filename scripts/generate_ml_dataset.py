#!/usr/bin/env python3
"""Lesson 5.4 — thực thi 18 run của hợp đồng đã khóa.

CHẠY QUA LAUNCHER, KHÔNG CHẠY TRỰC TIẾP:
    .venv/bin/python scripts/launch_ml_dataset.py

Tiến trình này chạy dưới `sudo /usr/bin/python3` và CHỈ dùng thư viện chuẩn
(+ mininet). Kiểm tra toàn vẹn hợp đồng cần numpy nên nằm ở launcher, chạy
TRƯỚC khi tiến trình này khởi động.

BA CHÍNH SÁCH LỖI, KHÁC NHAU CÓ CHỦ Ý:
  lỗi hợp đồng   -> dừng trước khi chạy run nào (launcher lo)
  lỗi môi trường -> dừng chiến dịch, giữ nguyên run đã xong
  lỗi một run    -> cách ly run đó, chạy tiếp; dừng sau 2 lần liên tiếp
Không bao giờ âm thầm bỏ qua một run: nó phải để lại dấu vết nhìn thấy được.
"""
import argparse
import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml import campaign as C
import traceback
import re
import uuid


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        '%Y-%m-%dT%H:%M:%SZ')


def start_profile(env, plan):
    """Bật traffic theo kế hoạch đã tính ở ml.campaign.traffic_plan().

    `iperf_seconds = pre_roll + duration + 10` cho CẢ HAI chế độ. Với lịch bậc
    thang, schedule_segments kéo dài BẬC CUỐI ra đúng bằng phần dư, nên tải phủ
    trọn thời gian ghi ở cả hai đầu. Đây là chỗ vá lỗi pre-roll.
    """
    from mininet import traffic
    if plan['mode'] == 'varying':
        return traffic.start_varying_load(
            env.net, plan['schedule_with_preroll'],
            duration=plan['iperf_seconds'],
            server_bg_rate=plan['server_bg_rate'])
    return traffic.start_background_load(
        env.net, scenario='normal', duration=plan['iperf_seconds'],
        normal_rate=plan['normal_rate'],
        server_bg_rate=plan['server_bg_rate'])


def execute_run(env, record, contract, design_sha):
    """Chạy MỘT run trọn vẹn. Trả (status, outcome_dict).

    status: 'ok' | 'failed'   (lỗi môi trường thì ném exception ra ngoài)
    """
    from bridge.collector import Collector
    from mininet import traffic
    from mininet.run_sync import configure_file_logging

    constants = contract['constants']
    run_id = record['run_id']
    paths = C.run_paths(run_id)
    plan = C.traffic_plan(record, constants)
    period = float(constants['period_sec'])

    archive_attempt(paths)
    configure_file_logging(str(paths['log']))       # log RIÊNG cho run này
    started = utc_now()
    print('\n' + '=' * 72, flush=True)
    print('[%s] RUN %-30s exec_index=%s split=%s'
          % (started, run_id, record['exec_index'], record['split']), flush=True)

    # --- 1. đưa mạng về baseline sạch + health gate ----------------------
    # QUAN TRỌNG: soft_reset() tự bật traffic MẶC ĐỊNH (normal 2 Mbps/client)
    # rồi mới chạy health gate. Phải để nó làm vậy, ĐỪNG bật profile của run
    # trước. Lý do: assert_baseline_healthy đòi throughput_norm >= 0.30, tức
    # khoảng 6 Mbps trên backbone 20. Run N-load1M chỉ tạo ~5 Mbps -> health
    # gate sẽ FAIL cho một cấu hình hoàn toàn hợp lệ.
    # Trình tự đúng: reset (2M mặc định) -> health gate -> ĐỔI sang profile run.
    reset_info = env.soft_reset()           # KHÔNG truyền scenario
    if reset_info['reset_dirty']:
        raise EnvironmentError(
            'run %s: soft_reset báo dirty (steady_ok=%s fresh_ok=%s '
            'aoi_norm=%s iperf_leaked=%s). Dừng chiến dịch — chạy tiếp chỉ '
            'tạo rác.' % (run_id, reset_info['reset_steady_ok'],
                          reset_info['reset_fresh_ok'],
                          reset_info['reset_aoi_norm'],
                          reset_info['iperf_leaked']))

    # --- 2. đổi sang profile của run + pre-roll --------------------------
    hosts = start_profile(env, plan)
    print('[gen] profile=%s, pre-roll %gs' % (plan['mode'],
                                              constants['pre_roll_sec']), flush=True)
    time.sleep(float(constants['pre_roll_sec']))

    # --- 3. thu, có hook inject/revert -----------------------------------
    provenance = C.collection_provenance(ROOT)
    meta = C.snapshot_meta(record, constants, provenance, design_sha)
    scenario = C.scenario_from_record(record)
    inject_tick = (int(round(record['t_inject'] / period))
                   if record.get('fault') else None)
    revert_tick = (int(round(record['t_revert'] / period))
                   if record.get('fault') else None)
    events = []

    def on_tick(n, snap, t_rel):
        """Chạy TRONG luồng collector, SAU khi snapshot n đã ghi xuống đĩa.

        Nhờ vậy snapshot tại inject_tick vẫn là trạng thái TRƯỚC sự cố, và ta
        biết CHÍNH XÁC fault rơi giữa tick nào với tick nào. Không có thread,
        không tranh net_lock, thời gian apply được ghi riêng để kiểm tra độ trễ.
        """
        if scenario is None:
            return
        if n == inject_tick:
            t0 = time.monotonic()
            env.injection.apply(scenario)
            events.append({'kind': 'inject', 'tick': n,
                           't_rel': round(t_rel, 6),
                           't_source': time.time(),
                           'completed_t_rel': round(t_rel + time.monotonic() - t0, 6),
                           'apply_ms': round((time.monotonic() - t0) * 1000, 1),
                           'scenario': scenario.describe()})
            print('[gen] INJECT tick=%d t_rel=%.3f %s'
                  % (n, t_rel, scenario.describe()), flush=True)
        elif n == revert_tick:
            t0 = time.monotonic()
            env.injection.revert_all()
            events.append({'kind': 'revert', 'tick': n,
                           't_rel': round(t_rel, 6),
                           't_source': time.time(),
                           'completed_t_rel': round(t_rel + time.monotonic() - t0, 6),
                           'apply_ms': round((time.monotonic() - t0) * 1000, 1)})
            print('[gen] REVERT tick=%d t_rel=%.3f' % (n, t_rel), flush=True)

    paths['partial'].parent.mkdir(parents=True, exist_ok=True)
    collector = Collector(env.net, interval=period, net_lock=env.net_lock,
                          log_path=str(paths['partial']),
                          pretty_log_path=None, overwrite=True,
                          run_meta=meta)
    collection_error = None
    try:
        collector.run(duration=record['duration_sec'], on_tick=on_tick)
    except Exception as exc:
        collection_error = repr(exc)
        traceback.print_exc()
    finally:
        # Idempotent: nếu tick revert đã chạy thì _active rỗng, không làm gì.
        # Nếu collector chết giữa lúc fault đang bật, đây là chỗ gỡ nó ra —
        # nếu không, run KẾ TIẾP sẽ khởi động trên một mạng đang hỏng.
        try:
            env.injection.revert_all()
        finally:
            traffic.stop_all_iperf(*hosts)

    # --- 4. kiểm tra, rồi mới COMMIT --------------------------------------
    finished = utc_now()
    snapshots = C.read_snapshots(paths['partial'])
    checks = C.verify_run(record, constants, snapshots, events)
    checks.setdefault('failed_gates', [])
    checks['runtime_error_count'] = C.runtime_error_count(paths['log'].read_text())
    checks['runtime_log_ok'] = checks['runtime_error_count'] == 0
    if not checks['runtime_log_ok']:
        checks['passed'] = False
        checks['failed_gates'].append('runtime_log_ok')

    if collection_error:
        checks['passed'] = False
        checks['failed_gates'].append('collection_exception')
        checks['collection_error'] = collection_error
    sha = C.sha256_file(paths['partial'])
    status = 'ok' if checks['passed'] else 'failed'
    destination = paths['final'] if status == 'ok' else paths['quarantine']
    meta_path = paths['meta'] if status == 'ok' else paths['quarantine_meta']
    destination.parent.mkdir(parents=True, exist_ok=True)
    sidecar = C.build_sidecar(record, constants, checks, events, provenance,
                              design_sha, sha, reset_info, plan,
                              started, finished)
    sidecar['status'] = status
    C.atomic_json(meta_path, sidecar)
    if destination.exists():
        raise RuntimeError('Refusing to overwrite raw observations: %s' % destination)
    os.rename(paths['partial'], destination)
    if status == 'failed':
        print('[gen] FAILED gates: %s' % checks['failed_gates'], flush=True)

    print('[gen] %-6s %s  snapshots=%d  sep=%s  sha=%s'
          % (status.upper(), run_id, checks['n_snapshots'],
             checks.get('max_separation', '-'), sha[:12]), flush=True)
    return status, {'status': status, 'sha256': sha, 'checks': checks,
                    'events': events, 'started_utc': started,
                    'finished_utc': finished,
                    'reset_dirty': reset_info['reset_dirty'],
                    'reset_mode': reset_info['reset_mode']}


def archive_attempt(paths):
    if paths['final'].exists():
        raise RuntimeError('Accepted/orphan raw file must be investigated, never overwritten')
    suffix = '.attempt-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
    for key in ('partial', 'meta', 'quarantine', 'quarantine_meta', 'log'):
        path = paths[key]
        if path.exists():
            destination = paths['quarantine'].parent / (path.stem + suffix + path.suffix)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(path, destination)


def already_done(record, design_sha):
    paths = C.run_paths(record['run_id'])
    if not paths['final'].exists():
        return False
    try:
        sidecar = json.loads(paths['meta'].read_text(encoding='utf-8'))
        valid = (sidecar.get('checks', {}).get('passed') is True
                 and sidecar.get('record') == record
                 and sidecar.get('design_content_sha256') == design_sha
                 and sidecar.get('sha256') == C.sha256_file(paths['final']))
    except (OSError, ValueError):
        valid = False
    if not valid:
        raise RuntimeError('Accepted raw/sidecar integrity failed: ' + record['run_id'])
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='+', default=None)
    parser.add_argument('--hard-every', type=int, default=6)
    args = parser.parse_args()
    namespace = os.environ.get('DT4N_NAMESPACE')
    if not namespace or namespace == 'org.dt4n':
        raise SystemExit('DT4N_NAMESPACE must be a dedicated campaign namespace')
    contract = C.load_contract()
    design_sha = contract['design_content_sha256']
    integrity = json.loads(os.environ.get('DT4N_CONTRACT_INTEGRITY', '{}'))
    if not (integrity.get('match') is True and
            integrity.get('stored') == integrity.get('content') == integrity.get('recomputed') == design_sha == C.contract_hash(contract)):
        raise SystemExit('Run through launcher: independent contract integrity is required')
    by_id = {r['run_id']: r for r in contract['runs']}
    if args.only and not set(args.only) <= set(by_id):
        raise SystemExit('Unknown run IDs: ' + str(set(args.only)-set(by_id)))
    order = [rid for rid in contract['execution_order'] if args.only is None or rid in args.only]
    started = utc_now()
    outcomes, consecutive_failures, env = {}, 0, None
    campaign_error = None
    for record in contract['runs']:
        if already_done(record, design_sha):
            sidecar = json.loads(C.run_paths(record['run_id'])['meta'].read_text())
            outcomes[record['run_id']] = {k: sidecar[k] for k in ('status','sha256','checks','events','started_utc','finished_utc','collection_provenance')}
        elif C.run_paths(record['run_id'])['quarantine_meta'].exists():
            sidecar = json.loads(C.run_paths(record['run_id'])['quarantine_meta'].read_text())
            outcomes[record['run_id']] = {k: sidecar[k] for k in ('status','sha256','checks','events','started_utc','finished_utc')}
    pending = [rid for rid in order if outcomes.get(rid, {}).get('status') != 'ok']
    print('[gen] namespace=%s selected=%d pending=%d' % (namespace,len(order),len(pending)), flush=True)
    try:
        if pending:
            from mininet.env_runner import EnvRunner
            from mininet.run_sync import configure_file_logging
            configure_file_logging('logs/ml_dataset_startup.log')
            env = EnvRunner(policy_path='ditto/policy_core_lab.json', sync_period=contract['constants']['period_sec'],
                            clients=3, do_pingall=True, hard_every=args.hard_every, mininet_log_level='warning')
            env.start()
        for run_id in order:
            if run_id not in pending:
                print('[gen] SKIP %s (checksum and contract verified)' % run_id, flush=True)
                continue
            try:
                status, outcome = execute_run(env, by_id[run_id], contract, design_sha)
            except Exception as exc:
                outcomes[run_id] = {'status':'failed','checks':{'passed':False,'failed_gates':['environment_exception']},'error':repr(exc)}
                raise
            outcomes[run_id] = outcome
            C.atomic_json(C.MANIFEST_PATH, C.build_manifest(contract,outcomes,C.collection_provenance(ROOT),integrity,started,utc_now()))
            consecutive_failures = 0 if status == 'ok' else consecutive_failures + 1
            if consecutive_failures >= C.MAX_CONSECUTIVE_FAILURES:
                break
    except Exception as exc:
        campaign_error = repr(exc)
        traceback.print_exc()
    finally:
        try:
            if env is not None:
                env.close()
        except Exception as exc:
            campaign_error = repr(exc)
            traceback.print_exc()
        finally:
            manifest = C.build_manifest(contract,outcomes,C.collection_provenance(ROOT),integrity,started,utc_now())
            if campaign_error:
                manifest['campaign_error'] = campaign_error
                manifest['complete'] = False
            C.atomic_json(C.MANIFEST_PATH,manifest)
            print('[gen] ok=%d failed=%d complete=%s base_rate=%s manifest=%s' %
                  (manifest['n_runs_ok'],manifest['n_runs_failed'],manifest['complete'],manifest['base_rate'],C.MANIFEST_PATH),flush=True)
    return 0 if all(outcomes.get(rid,{}).get('status') == 'ok' for rid in order) and not campaign_error else 1


if __name__ == '__main__':
    raise SystemExit(main())
