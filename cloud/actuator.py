#!/usr/bin/env python3
"""
actuator.py — Bộ chấp hành cloud (GĐ1.3): hai lệnh duy nhất được phép chạm AWS.

  set_capacity(n)          : ĐẶT số máy mong muốn = n   (Auto Scaling)
  replace_instance(id)     : báo máy `id` hỏng -> ASG tự thay máy mới, giữ số lượng
                             (Failover theo nghĩa thuyết minh ND4)

HỢP ĐỒNG AN TOÀN (giống tinh thần setBandwidth ở Phase 7–8, bài P6):
  1. GHI TRƯỚC (write-ahead): dòng 'intent' vào audit TRƯỚC khi gọi AWS,
     dòng 'result' SAU khi gọi. Sập giữa chừng -> còn intent không có result
     ("bản ghi vô chủ"), lệnh `audit` tìm ra được.
  2. CHUỖI HASH: dùng chính controller/audit.py -> sửa/xóa một dòng là lộ.
  3. ĐẶT MỨC + KIỂM TRƯỚC: đã đúng mức thì KHÔNG gọi AWS (outcome = noop).
     Gửi lại cùng lệnh bao nhiêu lần cũng không làm sai trạng thái.
  4. NHẮM ĐÚNG MÁY: replace cần instance-id cụ thể. Lặp lại lệnh -> máy đó đã
     unhealthy hoặc đã biến mất -> noop/skipped, không thay nhầm máy khác.
  5. KẸP TRẦN: n luôn nằm trong [0, MAX_SIZE].
  6. DRY-RUN: ghi audit, KHÔNG gọi AWS -> dùng cho "đề xuất, người duyệt".
  7. HIỆN Ý ĐỊNH LÊN TWIN: kết quả lệnh cuối được ghi vào feature 'command'
     của Thing cloud-pool, tách khỏi 'pool' (cái thực sự đang có).

CÁCH CHẠY (từ thư mục gốc repo, KHÔNG cần sudo):
    python3 -m cloud.actuator set 2 --reason "thu tay"
    python3 -m cloud.actuator set 2 --dry-run
    python3 -m cloud.actuator replace i-0abc123 --reason "thu failover"
    python3 -m cloud.actuator audit             # kiểm chuỗi hash + tìm bản ghi vô chủ
"""

import argparse
import json
import sys
import time
import uuid

from cloud import config as C
from cloud.infra import aws, find_asg
from cloud.twin import THING_ID
from controller.audit import AuditLog, read_rows, verify_chain

AUDIT_PATH = 'logs/cloud_actuator_audit.jsonl'


def new_cid():
    """Mã lệnh: nối dòng intent với dòng result của cùng một lệnh."""
    return 'cloud-' + uuid.uuid4().hex[:12]


def default_push(thing_id, features):
    from bridge.pusher import patch_thing
    return patch_thing(thing_id, features)


class CloudActuator:
    def __init__(self, audit_path=AUDIT_PATH, dry_run=False, push=default_push,
                 asg_client=None):
        self.audit = AuditLog(audit_path)
        self.dry_run = dry_run
        self.push = push
        self.asg = asg_client or aws('autoscaling')

    # ------------------------------------------------------------ ghi audit
    def _intent(self, cid, action, params, reason):
        return self.audit.append({
            'kind': 'intent', 'cid': cid, 'action': action, 'params': params,
            'reason': reason, 'dry_run': self.dry_run,
            't_wall': time.time(), 't_mono': time.monotonic(),
        })

    def _result(self, cid, action, t0, ok, outcome, before=None, after=None, error=''):
        row = self.audit.append({
            'kind': 'result', 'cid': cid, 'action': action, 'ok': ok,
            'outcome': outcome, 'before': before, 'after': after, 'error': error,
            'latency_ms': round((time.monotonic() - t0) * 1000.0, 1),
            't_wall': time.time(), 't_mono': time.monotonic(),
        })
        return row

    def _mirror(self, intent_row, result_row):
        """Ghi lệnh cuối lên twin. Lỗi ở đây KHÔNG được làm hỏng lệnh đã chạy."""
        if not self.push:
            return
        try:
            self.push(THING_ID, {'command': {'properties': {
                'lastCid': intent_row['cid'],
                'lastAction': intent_row['action'],
                'lastParams': intent_row['params'],
                'lastReason': intent_row['reason'],
                'lastOutcome': result_row['outcome'],
                'lastOk': result_row['ok'],
                'dryRun': intent_row['dry_run'],
                'tIntent': intent_row['t_wall'],
                'tResult': result_row['t_wall'],
            }}})
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ lệnh 1
    def set_capacity(self, n, reason='', cid=None):
        """ĐẶT số máy mong muốn. Trả dòng 'result' của audit."""
        cid = cid or new_cid()
        requested = int(n)
        target = max(0, min(requested, C.MAX_SIZE))
        intent = self._intent(cid, 'set_capacity',
                              {'requested': requested, 'target': target}, reason)
        t0 = time.monotonic()
        try:
            group = find_asg(self.asg)
            if group is None:
                raise RuntimeError('không thấy ASG %s' % C.NAMES['asg'])
            before = group['DesiredCapacity']
            if before == target:
                outcome, after = 'noop', before          # đã đúng mức: không gọi AWS
            elif self.dry_run:
                outcome, after = 'dry_run', before
            else:
                self.asg.set_desired_capacity(AutoScalingGroupName=C.NAMES['asg'],
                                              DesiredCapacity=target, HonorCooldown=False)
                outcome, after = 'applied', target
            result = self._result(cid, 'set_capacity', t0, True, outcome, before, after)
        except Exception as e:  # noqa: BLE001
            result = self._result(cid, 'set_capacity', t0, False, 'error', error=str(e)[:300])
        self._mirror(intent, result)
        return result

    # ------------------------------------------------------------ lệnh 2
    def replace_instance(self, instance_id, reason='', cid=None):
        """Báo máy `instance_id` hỏng -> ASG tự terminate và bật máy mới thay thế.

        Không đổi desired: số lượng máy được GIỮ NGUYÊN (đúng chữ thuyết minh).
        """
        cid = cid or new_cid()
        intent = self._intent(cid, 'replace_instance', {'instanceId': instance_id}, reason)
        t0 = time.monotonic()
        try:
            group = find_asg(self.asg)
            if group is None:
                raise RuntimeError('không thấy ASG %s' % C.NAMES['asg'])
            inst = next((i for i in group['Instances']
                         if i['InstanceId'] == instance_id), None)
            if inst is None:
                outcome, before = 'skipped_not_in_group', None   # đã bị thay / sai id
            elif inst['HealthStatus'] == 'Unhealthy':
                outcome, before = 'noop_already_unhealthy', 'Unhealthy'
            elif self.dry_run:
                outcome, before = 'dry_run', inst['HealthStatus']
            else:
                before = inst['HealthStatus']
                self.asg.set_instance_health(InstanceId=instance_id, HealthStatus='Unhealthy',
                                             ShouldRespectGracePeriod=False)
                outcome = 'applied'
            after = 'Unhealthy' if outcome == 'applied' else before
            result = self._result(cid, 'replace_instance', t0, True, outcome, before, after)
        except Exception as e:  # noqa: BLE001
            result = self._result(cid, 'replace_instance', t0, False, 'error',
                                  error=str(e)[:300])
        self._mirror(intent, result)
        return result


# ===========================================================================
# Kiểm audit: chuỗi hash còn nguyên không, có lệnh nào "vô chủ" không
# ===========================================================================
def check_audit(path=AUDIT_PATH):
    chain = verify_chain(path)
    rows = read_rows(path) if chain.get('ok') else []
    intents = {r['cid']: r for r in rows if r.get('kind') == 'intent'}
    results = {r['cid'] for r in rows if r.get('kind') == 'result'}
    orphans = sorted(set(intents) - results)
    return {'chain_ok': chain.get('ok'), 'chain': chain,
            'n_intent': len(intents), 'n_result': len(results), 'orphans': orphans}


def _print_result(r):
    mark = '✅' if r['ok'] else '❌'
    print('%s %s  cid=%s  outcome=%s  before=%s  after=%s  (%.0f ms)%s' % (
        mark, r['action'], r['cid'], r['outcome'], r['before'], r['after'],
        r['latency_ms'], ('  lỗi: ' + r['error']) if r['error'] else ''))


def main(argv=None):
    p = argparse.ArgumentParser(description='Bộ chấp hành cloud (GĐ1.3)')
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('set', help='đặt số máy mong muốn')
    s.add_argument('n', type=int)
    r = sub.add_parser('replace', help='báo một máy hỏng để ASG thay máy mới')
    r.add_argument('instance_id')
    for x in (s, r):
        x.add_argument('--reason', default='manual')
        x.add_argument('--dry-run', action='store_true')
        x.add_argument('--no-twin', action='store_true', help='không ghi lệnh lên Ditto')
    a_ = sub.add_parser('audit', help='kiểm chuỗi hash và bản ghi vô chủ')
    a_.add_argument('--path', default=AUDIT_PATH)
    a = p.parse_args(argv)

    if a.cmd == 'audit':
        print(json.dumps(check_audit(a.path), indent=2, ensure_ascii=False))
        return
    act = CloudActuator(dry_run=a.dry_run, push=None if a.no_twin else default_push)
    if a.cmd == 'set':
        _print_result(act.set_capacity(a.n, reason=a.reason))
    elif a.cmd == 'replace':
        _print_result(act.replace_instance(a.instance_id, reason=a.reason))


if __name__ == '__main__':
    sys.exit(main())
