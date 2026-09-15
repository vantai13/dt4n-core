#!/usr/bin/env python3
"""
test_command_security.py - Kiem thu an toan cho Command Agent (Lesson 4.5).

Chay khi he dang len: Ditto + Mininet + Sync Agent + Command Agent.
Script nay dong vai ke tan cong va doi audit log xac nhan agent da chan dung.
"""

import json
import os
import time
import uuid

import pytest

requests = pytest.importorskip('requests')

from bridge.ditto_common import DITTO_BASE_URL, DITTO_AUTH, NAMESPACE

CONTROLLER = '%s:controller' % NAMESPACE
AUDIT_PATH = os.environ.get('DT4N_COMMAND_AUDIT',
                            'logs/command_agent_audit.log')

pytestmark = pytest.mark.skipif(
    os.environ.get('DT4N_LIVE_COMMAND_TESTS') != '1',
    reason='requires live Ditto + Mininet + Command Agent; set DT4N_LIVE_COMMAND_TESTS=1',
)


def _send(subject, body):
    """Gui 1 lenh, tra (correlation_id, http_status, response_json)."""
    cid = str(uuid.uuid4())
    url = '%s/things/%s/inbox/messages/%s?timeout=0' % (
        DITTO_BASE_URL, CONTROLLER, subject)
    headers = {
        'Content-Type': 'application/json',
        'correlation-id': cid,
    }
    body = dict(body, clientCorrelationId=cid)
    r = requests.post(url, json=body, headers=headers, auth=DITTO_AUTH,
                      timeout=8)
    try:
        resp = r.json()
    except Exception:
        resp = None
    return cid, r.status_code, resp


def _find_audit(correlation_id, timeout=8.0):
    """Doi audit log co dong mang correlation_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with open(AUDIT_PATH, encoding='utf-8') as f:
                for line in f:
                    try:
                        row = json.loads(line)
                    except ValueError:
                        continue
                    if row.get('correlationId') == correlation_id:
                        return row
        except OSError:
            pass
        time.sleep(0.1)
    return None


def _send_and_wait(subject, body):
    cid, status, resp = _send(subject, body)
    row = _find_audit(cid)
    return cid, status, resp, row


def _rejected(resp, row, reason_part):
    if row is not None:
        return (row.get('result') == 'rejected'
                and reason_part in str(row.get('reason')))
    return (isinstance(resp, dict)
            and resp.get('status') == 'rejected'
            and reason_part in str(resp.get('result') or resp.get('reason')))


def test_1_unknown_command():
    """Ca 1: lenh ngoai whitelist -> bi tu choi."""
    cid, status, resp, row = _send_and_wait(
        'rebootEverything', {'target': NAMESPACE + ':link-h1-s1'})
    assert _rejected(resp, row, 'unknown command'), \
        'Lenh la khong bi tu choi! cid=%s status=%s resp=%s audit=%s' % (
            cid, status, resp, row)
    print('Ca 1 PASS: lenh ngoai whitelist bi tu choi')


def test_2_payload_injection():
    """Ca 2: payload giong shell command -> validate chan, khong exec."""
    cid, status, resp, row = _send_and_wait(
        'setBandwidth',
        {'target': NAMESPACE + ':link-s2-s3', 'bw': '$(rm -rf /)'})
    assert _rejected(resp, row, 'bw must be a number'), \
        'Payload injection khong bi chan! cid=%s status=%s resp=%s audit=%s' % (
            cid, status, resp, row)
    print('Ca 2 PASS: payload injection bi validate chan')


def test_3_target_not_found():
    """Ca 3: target bia -> 404/rejected, agent khong crash."""
    cid, status, resp, row = _send_and_wait(
        'disableLink', {'target': NAMESPACE + ':link-xx-yy'})
    assert _rejected(resp, row, 'target not found'), \
        'Target bia khong bi tu choi! cid=%s status=%s resp=%s audit=%s' % (
            cid, status, resp, row)
    print('Ca 3 PASS: target khong ton tai bi tu choi')


def test_4_idempotent():
    """Ca 4: gui disableLink lap lai -> khong loi."""
    for i in range(3):
        cid, status, resp, row = _send_and_wait(
            'disableLink', {'target': NAMESPACE + ':link-h1-s1'})
        if row is not None:
            ok = row.get('result') == 'ok'
        else:
            ok = ((isinstance(resp, dict) and resp.get('status') == 'accepted')
                  or (200 <= status < 300 and resp is None))
        assert ok, 'Lenh lap lan %d gay loi! cid=%s status=%s resp=%s audit=%s' % (
            i + 1, cid, status, resp, row)
    print('Ca 4 PASS: lenh lap idempotent, khong loi')

    # Don dep de cac test/demo sau khong bat dau tu link down.
    _send('enableLink', {'target': NAMESPACE + ':link-h1-s1'})


def run_all():
    for test in (test_1_unknown_command, test_2_payload_injection,
                 test_3_target_not_found, test_4_idempotent):
        test()
    print('\n=== TAT CA CA AN TOAN TU DONG PASS ===')


if __name__ == '__main__':
    run_all()
