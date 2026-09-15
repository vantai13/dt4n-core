#!/usr/bin/env python3
"""
bootstrap.py — Dựng "khung nhà rỗng" trong Ditto (Phase 2, Lesson 2.2). LỚP 2.

NHIỆM VỤ: tạo sẵn Policy + Thing khung (giá trị 0) tương ứng topology Mininet,
để Sync Agent (2.3) chỉ việc PATCH dữ liệu sống vào. Tự sinh từ topology
(KHÔNG gõ tay) -> giữ reproducibility; idempotent -> chạy lại an toàn.

THỨ TỰ NHÂN-QUẢ (Lesson 2.2 Phần 3): Policy TRƯỚC -> Thing SAU.
  (Thing trỏ vào Policy qua policyId; vật được tham chiếu phải tồn tại trước.)

HAI NGUỒN THỰC THỂ (đây là phần "linh hoạt"):
  A) Từ đối tượng `net` Mininet đang sống  -> entities_from_net(net)
  B) Từ file mô tả topology (JSON)         -> entities_from_spec(path)
  Cả hai trả về CÙNG một cấu trúc 'entities' -> phần PUT lên Ditto dùng chung.
  Nhờ vậy bootstrap chạy ĐỘC LẬP (không cần Mininet) hoặc tích hợp runner đều được.

CHẠY (độc lập, không cần Mininet — đọc topology từ file):
    python3 -m bridge.bootstrap --create --spec ditto/topology_spec.json
    python3 -m bridge.bootstrap --reset  --spec ditto/topology_spec.json

CHẠY (tích hợp, trong tiến trình có `net`):
    from bridge.bootstrap import bootstrap_all
    bootstrap_all(entities_from_net(net), mode='create')
"""

import argparse
import json
import sys

import requests

from bridge.ditto_common import (
    DITTO_BASE_URL, DITTO_AUTH, NAMESPACE, POLICY_ID, HTTP_TIMEOUT,
    make_thing_id_host, make_thing_id_switch, make_thing_id_link,
    make_thing_id_path,
)


# ===========================================================================
# PHẦN A — SINH "entities": danh sách thực thể chuẩn hóa, độc lập nguồn.
# Mỗi entity = dict {thing_id, kind, body}. Phần PUT không cần biết nó từ đâu.
# ===========================================================================
def _host_body(name, ip='0.0.0.0', role=None):
    if role is None:
        role = 'server' if name.startswith('srv') else 'client'
    # Giá trị 0 = PLACEHOLDER (Lesson 2.2 Phần 3a): feature TỒN TẠI, chờ dữ liệu.
    # Nếu để rỗng, dashboard Phase 3 đọc lúc chưa sync sẽ vẽ trống/lỗi.
    return {
        'policyId': POLICY_ID,
        'attributes': {'type': 'host', 'role': role, 'ip': ip},
        'features': {
            'status':  {'properties': {'state': 'up'}},
            'traffic': {'properties': {'rxBytes': 0, 'txBytes': 0,
                                       'rxRate': 0, 'txRate': 0}},
            'meta': {'properties': {'tSource': 0}},
        },
    }

def _switch_body(name):
    return {
        'policyId': POLICY_ID,
        'attributes': {'type': 'switch'},
        'features': {
            'status': {'properties': {'state': 'up'}},
            'portStats': {'properties': {'dump': ''}},
            'meta': {'properties': {'tSource': 0}},
        },
    }

def _link_body(a, b):
    return {
        'policyId': POLICY_ID,
        'attributes': {'type': 'link', 'endpointA': a, 'endpointB': b},
        'features': {
            'status':  {'properties': {'state': 'up'}},
            'capacity': {'properties': {'bwMbps': 0}},
            'traffic': {'properties': {'rxRate': 0, 'txRate': 0}},
            'quality': {'properties': {'latency_ms': 0, 'packetLoss_pct': 0}},
            'meta': {'properties': {'tSource': 0}},
        },
    }


def _spec_link_endpoints(link):
    if isinstance(link, dict):
        return link['endpoints'][0], link['endpoints'][1]
    return link[0], link[1]


def _path_body(src, dst):
    """Path Thing: a directed multi-hop measurement, not a physical edge."""
    return {
        'policyId': POLICY_ID,
        'attributes': {'type': 'path', 'src': src, 'dst': dst},
        'features': {
            'quality': {'properties': {'latency_ms': 0, 'packetLoss_pct': 0}},
            'meta': {'properties': {'tSource': 0}},
        },
    }


def _controller_body():
    """Controller Thing: inbox chung cho lệnh chiều xuống.

    Nó không phản ánh thiết bị vật lý nào; Thing này tồn tại để dashboard POST
    command message vào và Command Agent mở SSE đọc ra. Features tối thiểu giúp
    debug/audit nhẹ mà không làm dashboard vẽ thêm node/edge.
    """
    return {
        'policyId': POLICY_ID,
        'attributes': {'type': 'controller', 'role': 'command-sink'},
        'features': {
            'command': {'properties': {'lastSubject': '', 'lastTs': ''}},
        },
    }


def _append_controller(ents):
    ents.append({'thing_id': '%s:controller' % NAMESPACE,
                 'kind': 'controller', 'body': _controller_body()})
    return ents


def _append_paths(ents, probes=(('h1', 'srv1'),)):
    """Append fixed path probe Things. Collector currently probes h1 -> srv1."""
    for src, dst in probes:
        ents.append({'thing_id': make_thing_id_path(src, dst),
                     'kind': 'path', 'body': _path_body(src, dst)})
    return ents


def entities_from_net(net):
    """NGUỒN A: đọc từ Mininet `net` đang sống (cần Mininet)."""
    ents = []
    for h in net.hosts:
        ip = h.IP() if hasattr(h, 'IP') else '0.0.0.0'
        ents.append({'thing_id': make_thing_id_host(h.name),
                     'kind': 'host', 'body': _host_body(h.name, ip)})
    for s in net.switches:
        ents.append({'thing_id': make_thing_id_switch(s.name),
                     'kind': 'switch', 'body': _switch_body(s.name)})
    seen = set()
    for ln in net.links:
        a = ln.intf1.node.name           # link = 2 interface trên 2 node
        b = ln.intf2.node.name           # (Lesson 2.2: đừng nhầm link với interface)
        tid = make_thing_id_link(a, b)
        if tid in seen:                  # canonical -> chống trùng
            continue
        seen.add(tid)
        ents.append({'thing_id': tid, 'kind': 'link', 'body': _link_body(a, b)})
    _append_paths(ents)
    return _append_controller(ents)


def entities_from_spec(path):
    """NGUỒN B: đọc từ file JSON mô tả topology (KHÔNG cần Mininet).
    Cho phép test bootstrap độc lập. Format file: xem ditto/topology_spec.json."""
    spec = json.load(open(path))
    ents = []
    for h in spec.get('hosts', []):
        name = h['name'] if isinstance(h, dict) else h
        ip = h.get('ip', '0.0.0.0') if isinstance(h, dict) else '0.0.0.0'
        role = h.get('role') if isinstance(h, dict) else None
        ents.append({'thing_id': make_thing_id_host(name),
                     'kind': 'host', 'body': _host_body(name, ip, role)})
    for s in spec.get('switches', []):
        name = s['name'] if isinstance(s, dict) else s
        ents.append({'thing_id': make_thing_id_switch(name),
                     'kind': 'switch', 'body': _switch_body(name)})
    seen = set()
    for ln in spec.get('links', []):
        a, b = _spec_link_endpoints(ln)  # list pair or metadata dict
        tid = make_thing_id_link(a, b)
        if tid in seen:
            continue
        seen.add(tid)
        ents.append({'thing_id': tid, 'kind': 'link', 'body': _link_body(a, b)})
    _append_paths(ents, probes=spec.get('pathProbes', (('h1', 'srv1'),)))
    return _append_controller(ents)


# ===========================================================================
# PHẦN B — NÓI CHUYỆN VỚI DITTO. Phân loại status code, fail-fast đúng chỗ.
# ===========================================================================
def put_policy(policy_body):
    """Bước 1: PUT Policy. 201=tạo mới, 204=ghi đè (đều OK cho bootstrap)."""
    pid = policy_body['policyId']
    url = '%s/policies/%s' % (DITTO_BASE_URL, pid)
    r = requests.put(url, json=policy_body, auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
    if r.status_code in (201, 204):
        print('  ✅ policy %s (%d)' % (pid, r.status_code))
        return True
    # 401/403/400 = lỗi VĨNH VIỄN -> fail-fast, không retry (Lesson 2.2 Phần 2.4)
    print('  ❌ policy %s -> %d: %s' % (pid, r.status_code, r.text[:300]))
    _diagnose(r.status_code)
    r.raise_for_status()


def thing_exists(thing_id):
    """GET kiểm tra tồn tại (cho mode --create idempotent kiểu skip)."""
    url = '%s/things/%s' % (DITTO_BASE_URL, thing_id)
    r = requests.get(url, auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
    return r.status_code == 200


def put_thing(thing_id, body, skip_if_exists=True):
    """Bước 3: PUT một Thing.
    skip_if_exists=True (mode create): nếu đã có -> BỎ QUA, tránh ghi đè dữ liệu
    sống về 0 (Lesson 2.2 Phần 4.3 - cái bẫy reset metric)."""
    if skip_if_exists and thing_exists(thing_id):
        print('  ⏭️  %s đã tồn tại, bỏ qua' % thing_id)
        return 'skipped'
    url = '%s/things/%s' % (DITTO_BASE_URL, thing_id)
    r = requests.put(url, json=body, auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
    if r.status_code in (201, 204):
        print('  ✅ %s (%d)' % (thing_id, r.status_code))
        return 'created'
    print('  ❌ %s -> %d: %s' % (thing_id, r.status_code, r.text[:300]))
    _diagnose(r.status_code)
    r.raise_for_status()


def delete_thing(thing_id):
    url = '%s/things/%s' % (DITTO_BASE_URL, thing_id)
    r = requests.delete(url, auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
    # 204=xóa xong, 404=vốn không có (cũng coi là OK cho reset)
    ok = r.status_code in (204, 404)
    print('  %s %s (%d)' % ('🗑️ ' if ok else '❌', thing_id, r.status_code))
    return ok


def _diagnose(code):
    """In gợi ý debug theo status — biến lỗi khô khan thành hướng dẫn."""
    hints = {
        401: 'Sai/thiếu basic auth. Kiểm tra DITTO_USER/DITTO_PASSWORD.',
        403: 'Đã auth nhưng KHÔNG có quyền -> subject trong Policy không khớp '
             'prefix nginx phát ra. Chạy: python3 -m bridge.diagnose',
        400: 'Body sai cấu trúc / thingId chứa ký tự lạ. Đọc message ở trên.',
        404: 'Thing/Policy không tồn tại.',
    }
    if code in hints:
        print('     ↳ %s' % hints[code])
    elif code >= 500:
        print('     ↳ Lỗi phía Ditto (5xx) - lỗi TẠM THỜI, có thể thử lại.')


# ===========================================================================
# PHẦN C — ORCHESTRATE: Policy -> duyệt entities -> PUT từng Thing.
# ===========================================================================
def bootstrap_all(entities, policy_body, mode='create'):
    """mode='create': skip Thing đã có (an toàn lặp lại).
       mode='reset' : xóa hết Thing trong danh sách rồi tạo lại từ đầu."""
    print('=== BOOTSTRAP (mode=%s) ===' % mode)

    # Bước 1: Policy LUÔN trước.
    print('[1] Policy:')
    put_policy(policy_body)

    # Bước 2 (chỉ reset): xóa Thing cũ.
    if mode == 'reset':
        print('[2] Reset - xóa Thing cũ:')
        for e in entities:
            delete_thing(e['thing_id'])

    # Bước 3: tạo Thing.
    print('[3] Things:')
    counts = {'created': 0, 'skipped': 0}
    skip = (mode == 'create')   # reset thì không skip (vừa xóa xong)
    for e in entities:
        res = put_thing(e['thing_id'], e['body'], skip_if_exists=skip)
        counts[res] = counts.get(res, 0) + 1

    print('=== XONG: %d tạo, %d bỏ qua, tổng %d Thing ==='
          % (counts['created'], counts['skipped'], len(entities)))
    return counts


def main():
    p = argparse.ArgumentParser(description='DT4N Ditto bootstrap (Lesson 2.2)')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--create', action='store_true', help='tạo, skip nếu đã có (mặc định)')
    g.add_argument('--reset', action='store_true', help='XÓA hết rồi tạo lại')
    p.add_argument('--spec', default='ditto/topology_spec.json',
                   help='file JSON mô tả topology (nguồn B)')
    p.add_argument('--policy', default='ditto/policy.json',
                   help='file Policy JSON')
    args = p.parse_args()

    mode = 'reset' if args.reset else 'create'

    if mode == 'reset':
        ans = input('⚠️  --reset sẽ XÓA toàn bộ Thing. Gõ "yes" để tiếp: ')
        if ans.strip().lower() != 'yes':
            print('Hủy.'); sys.exit(0)

    policy_body = json.load(open(args.policy))
    entities = entities_from_spec(args.spec)

    try:
        bootstrap_all(entities, policy_body, mode=mode)
    except requests.exceptions.ConnectionError:
        print('\n❌ Không kết nối được Ditto tại %s' % DITTO_BASE_URL)
        print('   -> Ditto đang chạy chưa? Thử: python3 -m bridge.diagnose')
        sys.exit(1)


if __name__ == '__main__':
    main()
