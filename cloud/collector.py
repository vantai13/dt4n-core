#!/usr/bin/env python3
"""
collector.py — Đọc trạng thái nhóm máy AWS và đẩy lên Thing 'cloud-pool' (GĐ1.2).

Vai trò giống bridge/collector.py + sync_agent.py của Mininet, chỉ khác NGUỒN:
  Mininet : đọc counter trong /proc/net/dev        -> Ditto
  Cloud   : đọc API AWS (ASG + target health của ALB) -> Ditto

CÁCH CHẠY (từ thư mục gốc repo, KHÔNG cần sudo; Ditto phải đang chạy):
    python3 -m cloud.collector bootstrap          # tạo Thing cloud-pool (một lần)
    python3 -m cloud.collector once               # đọc 1 lần, in ra, đẩy lên Ditto
    python3 -m cloud.collector run --period 5     # chạy liên tục (Ctrl+C để dừng)
    python3 -m cloud.collector run --dry-run      # chỉ in, không đẩy (khi chưa bật Ditto)

Mỗi chu kỳ ghi 1 dòng JSON vào logs/cloud_collector.jsonl để GĐ1.5 đo thời gian.
"""

import argparse
import json
import sys
import time
from pathlib import Path

from cloud import config as C
from cloud.infra import aws, find_asg, find_tg
from cloud.twin import THING_ID, error_features, snapshot_to_features, thing_body


# ===========================================================================
# PHẦN 1 — đọc AWS thành một "ảnh chụp" (snapshot) thuần dữ liệu
# ===========================================================================
def read_pool(asg_client, elb_client):
    """Đọc ASG + sức khỏe từng máy theo ALB. Trả dict thuần (không đụng Ditto).

    'healthy' = máy đang InService VÀ ALB báo healthy = máy thật sự phục vụ được.
    Đây là con số controller GĐ1.4 sẽ dùng: thêm máy chỉ "xong" khi healthy tăng,
    không phải khi desired tăng.
    """
    group = find_asg(asg_client)
    if group is None:
        raise RuntimeError('Không thấy ASG %s (chưa chạy `cloud.infra up`?)' % C.NAMES['asg'])

    tg_health = {}
    tg = find_tg(elb_client)
    if tg:
        for d in elb_client.describe_target_health(
                TargetGroupArn=tg['TargetGroupArn'])['TargetHealthDescriptions']:
            tg_health[d['Target']['Id']] = d['TargetHealth']['State']

    # Đóng dấu thời gian NGAY SAU khi đọc xong: đây là "dữ liệu này đúng vào lúc nào".
    t_source = time.time()

    instances = []
    for i in sorted(group['Instances'], key=lambda x: x['InstanceId']):
        instances.append({
            'id': i['InstanceId'],
            'az': i['AvailabilityZone'],
            'lifecycle': i['LifecycleState'],        # Pending / InService / Terminating ...
            'asgHealth': i['HealthStatus'],          # Healthy / Unhealthy (theo ASG)
            'albHealth': tg_health.get(i['InstanceId'], 'unregistered'),
        })

    def count(pred):
        return sum(1 for x in instances if pred(x))

    return {
        't_source': t_source,
        'desired': group['DesiredCapacity'],
        'min': group['MinSize'],
        'max': group['MaxSize'],
        'total': len(instances),
        'pending': count(lambda x: x['lifecycle'].startswith('Pending')),
        'inService': count(lambda x: x['lifecycle'] == 'InService'),
        'healthy': count(lambda x: x['lifecycle'] == 'InService'
                         and x['albHealth'] == 'healthy'),
        'terminating': count(lambda x: x['lifecycle'].startswith('Terminating')),
        'instances': instances,
    }


def summary(snap):
    """Một dòng ngắn để in ra màn hình."""
    return 'desired=%d total=%d pending=%d inService=%d healthy=%d terminating=%d' % (
        snap['desired'], snap['total'], snap['pending'],
        snap['inService'], snap['healthy'], snap['terminating'])


# ===========================================================================
# PHẦN 2 — một chu kỳ: đọc -> đẩy (hoặc báo lỗi) -> ghi log
# ===========================================================================
def default_push(thing_id, features):
    """Đẩy lên Ditto bằng CHÍNH hàm sync agent đang dùng (merge-patch + retry)."""
    from bridge.pusher import patch_thing
    return patch_thing(thing_id, features)


def cycle(asg_client, elb_client, push, log_path=None):
    """Chạy 1 chu kỳ. Trả (snap hoặc None, pushed_ok)."""
    t_attempt = time.time()
    try:
        snap = read_pool(asg_client, elb_client)
    except Exception as e:  # noqa: BLE001 — lỗi AWS/mạng: báo lên twin, không sập
        ok = push(THING_ID, error_features(e, t_attempt)) if push else False
        _log(log_path, {'tAttempt': t_attempt, 'pollOk': False, 'error': str(e)[:200],
                        'pushed': bool(ok)})
        print('%s  ❌ đọc AWS lỗi: %s' % (_hms(t_attempt), str(e)[:120]))
        return None, ok

    ok = push(THING_ID, snapshot_to_features(snap)) if push else False
    _log(log_path, {'tSource': snap['t_source'], 'pollOk': True, 'pushed': bool(ok),
                    **{k: snap[k] for k in ('desired', 'total', 'pending', 'inService',
                                            'healthy', 'terminating')}})
    return snap, ok


def _hms(t):
    return time.strftime('%H:%M:%S', time.localtime(t))


def _log(path, row):
    if not path:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(row, sort_keys=True) + '\n')


# ===========================================================================
# PHẦN 3 — vòng lặp: lịch theo đồng hồ MONOTONIC, tem thời gian theo đồng hồ TƯỜNG
#   monotonic : không nhảy khi đồng bộ giờ hệ thống -> giữ nhịp chu kỳ đều
#   time.time : so sánh được giữa các tiến trình -> dùng cho tSource (bài P3)
# ===========================================================================
def run(period=5.0, push=default_push, log_path='logs/cloud_collector.jsonl',
        max_cycles=None):
    asg_client, elb_client = aws('autoscaling'), aws('elbv2')
    print('☁️  cloud collector: %s mỗi %.1fs -> %s%s' % (
        C.NAMES['asg'], period, THING_ID, '' if push else '  (dry-run, KHÔNG đẩy)'))
    next_t = time.monotonic()
    last_line, n = None, 0
    try:
        while True:
            snap, ok = cycle(asg_client, elb_client, push, log_path)
            if snap is not None:
                line = summary(snap)
                if line != last_line:              # chỉ in khi trạng thái đổi
                    mark = '' if (ok or not push) else '  ⚠️ đẩy Ditto lỗi'
                    print('%s  %s%s' % (_hms(snap['t_source']), line, mark))
                    last_line = line
            n += 1
            if max_cycles is not None and n >= max_cycles:
                return
            next_t += period
            time.sleep(max(0.0, next_t - time.monotonic()))
    except KeyboardInterrupt:
        print('\n⏹  dừng collector.')


# ===========================================================================
def main(argv=None):
    p = argparse.ArgumentParser(description='Cloud collector: AWS -> Ditto (GĐ1.2)')
    sub = p.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('bootstrap', help='tạo Thing cloud-pool')
    b.add_argument('--recreate', action='store_true', help='xóa rồi tạo lại Thing')
    o = sub.add_parser('once', help='đọc 1 lần, in JSON, đẩy lên Ditto')
    o.add_argument('--dry-run', action='store_true')
    r = sub.add_parser('run', help='chạy liên tục')
    r.add_argument('--period', type=float, default=5.0)
    r.add_argument('--dry-run', action='store_true')
    r.add_argument('--log', default='logs/cloud_collector.jsonl')
    a = p.parse_args(argv)

    if a.cmd == 'bootstrap':
        from bridge.bootstrap import delete_thing, put_thing
        if a.recreate:
            delete_thing(THING_ID)
        put_thing(THING_ID, thing_body(), skip_if_exists=not a.recreate)
    elif a.cmd == 'once':
        snap, ok = cycle(aws('autoscaling'), aws('elbv2'),
                         None if a.dry_run else default_push)
        if snap is not None:
            print(json.dumps(snap, indent=2, ensure_ascii=False))
            print('đẩy lên Ditto: %s' % ('bỏ qua (dry-run)' if a.dry_run
                                        else ('✅ OK' if ok else '❌ lỗi')))
    elif a.cmd == 'run':
        run(period=a.period, push=None if a.dry_run else default_push, log_path=a.log)


if __name__ == '__main__':
    sys.exit(main())
