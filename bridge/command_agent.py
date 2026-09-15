#!/usr/bin/env python3
"""
command_agent.py — Command Agent (chiều XUỐNG, Phase 4). LỚP 2 (Bridge).

VAI TRÒ: đối xứng với sync_agent.py. Nếu Sync Agent là "miệng" (đẩy state LÊN
Ditto), thì Command Agent là "TAI" (nghe lệnh TỪ Ditto để thực thi XUỐNG mạng).

BẢN LESSON 4.2 — CHỈ PHẦN "TAI":
  - Mở SSE nghe messages gửi tới controller Thing.
  - Parse subject (tên lệnh) + payload (target/params) + correlation-id.
  - TẠM THỜI chỉ LOG. Chưa thực thi (đó là Lesson 4.3), chưa phản hồi (4.4).
  Mục đích: chứng minh phần "nghe" hoạt động ĐỘC LẬP trước khi ghép phần "tay".
  (isolate before integrate — cô lập từng phần trước khi tích hợp.)

VÌ SAO SSE (push) chứ không polling (pull):
  Lệnh tới BẤT CHỢT và cần phản ứng NGAY. Polling thì trễ + lãng phí (99% câu
  hỏi rỗng). SSE giữ 1 kết nối mở, Ditto ĐẨY lệnh xuống ngay khi có -> không trễ,
  không lãng phí. (Ngược với Sync Agent Phase 2 dùng polling vì metrics cần đọc
  định kỳ đằng nào cũng lấy — hai chiều, hai mô hình khác nhau, có chủ đích.)

VÌ SAO CHUNG TIẾN TRÌNH với Mininet:
  Lesson 4.3 sẽ gọi net.configLinkStatus(...) -> cần đối tượng `net`, mà `net`
  chỉ sống trong tiến trình giữ Mininet. Nên agent này chạy như 1 THREAD NỀN
  trong run_sync.py, cạnh thread Sync Agent, dùng CHUNG net_lock để tránh race.
"""

import json
import codecs
import datetime
import logging
import threading
import time
from collections import OrderedDict

import requests

from bridge.ditto_common import (
    DITTO_BASE_URL, DITTO_AUTH, NAMESPACE, POLICY_ID, HTTP_TIMEOUT,
)
from bridge.flow_log import flow_event
from mininet.tc_filter import install_tc_warning_filter


install_tc_warning_filter()

log = logging.getLogger('command_agent')

# controller Thing: điểm nhận MỌI lệnh (quyết định 4.1 — single control point).
CONTROLLER_THING_ID = '%s:controller' % NAMESPACE

# Endpoint SSE nghe message gửi tới inbox controller. KHÔNG lọc subject ở URL
# -> nhận cả 5 lệnh, tự phân loại trong code (đúng controller-Thing pattern).
INBOX_SSE_URL = '%s/things/%s/inbox/messages' % (DITTO_BASE_URL, CONTROLLER_THING_ID)

# Reconnect: kết nối sống-lâu SẼ rớt (Ditto restart, mạng chớp). Ở Python phải
# TỰ viết vòng reconnect (khác EventSource của trình duyệt tự làm giúp).
RECONNECT_DELAY = 2.0     # giây — chờ trước khi mở lại stream sau khi đứt
SSE_READ_TIMEOUT = None   # None = không timeout đọc; stream giữ mở chờ event
SSE_CHUNK_SIZE = 1        # đọc SSE từng byte để tránh iter_lines giữ event trong buffer

AUDIT_PATH = 'logs/command_agent_audit.log'   # JSON-mỗi-dòng (JSONL)

# Ngưỡng bandwidth hợp lệ (Mbps). Chặn giá trị điên rồ gây hành vi lạ ở tc.
BW_MIN = 0
BW_MAX = 100

# Switch restart is asynchronous in Mininet/OVS: sw.start() creates the bridge
# and controller rows, but OpenFlow connection can settle later.
SWITCH_CONNECT_TIMEOUT = 12.0
SWITCH_CONNECT_POLL = 0.3

# DEDUP: SSE/live-message có thể giao lại cùng một command. Mỗi correlation-id
# chỉ được thực thi một lần; các bản lặp được ack OK nhưng không chạm Mininet.
_processed_ids = OrderedDict()
_processed_lock = threading.Lock()
_PROCESSED_MAX = 500


def _ok(detail='ok'):
    return (True, 200, detail)


def _reject(code, reason):
    return (False, code, reason)


def processed_result(cid):
    """Return previous result tuple for correlation-id, or None if first time."""
    if not cid:
        log.warning('Message KHÔNG có correlation-id -> không dedup được.')
        return None
    with _processed_lock:
        item = _processed_ids.get(cid)
        if item is None:
            return None
        if isinstance(item, dict):
            return item.get('result')
        return _ok('duplicate ignored (already executed)')


def remember_processed(cid, result):
    """Remember the exact result so redeliveries get the same response."""
    if not cid:
        return
    with _processed_lock:
        _processed_ids[cid] = {'ts': time.time(), 'result': result}
        while len(_processed_ids) > _PROCESSED_MAX:
            _processed_ids.popitem(last=False)


def audit(correlation_id, subject, target, params, result, reason=None):
    """Ghi 1 dòng JSON vào audit log. Không để lỗi ghi log làm sập xử lý lệnh."""
    row = {
        'ts': datetime.datetime.utcnow().isoformat() + 'Z',
        'correlationId': correlation_id,
        'subject': subject,
        'target': target,
        'params': params,
        'result': result,
        'reason': reason,
    }
    try:
        with open(AUDIT_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
    except Exception as e:
        log.warning('Ghi audit lỗi (bỏ qua): %s', e)


def _resolve_link(net, thing_id):
    """org.dt4n:link-<a>-<b> -> đối tượng link trong net, hoặc None."""
    if not isinstance(thing_id, str) or ':link-' not in thing_id:
        return None
    body = thing_id.split(':link-', 1)[-1]
    parts = body.split('-')
    if len(parts) < 2:
        return None
    want = {parts[0], '-'.join(parts[1:])}
    for ln in net.links:
        a = ln.intf1.node.name
        b = ln.intf2.node.name
        if {a, b} == want:
            return ln
    return None


def _resolve_host(net, thing_id):
    """org.dt4n:host-<name> -> đối tượng host trong net, hoặc None."""
    if not isinstance(thing_id, str) or ':host-' not in thing_id:
        return None
    name = thing_id.split(':host-', 1)[-1]
    for h in net.hosts:
        if h.name == name:
            return h
    return None


def _resolve_switch(net, thing_id):
    """org.dt4n:switch-<name> -> đối tượng switch trong net, hoặc None."""
    if not isinstance(thing_id, str) or ':switch-' not in thing_id:
        return None
    name = thing_id.split(':switch-', 1)[-1]
    for sw in net.switches:
        if sw.name == name:
            return sw
    return None


def _controller_target(controller):
    protocol = getattr(controller, 'protocol', 'tcp')
    ip = controller.IP() if hasattr(controller, 'IP') else getattr(controller, 'ip', '127.0.0.1')
    port = getattr(controller, 'port', 6653) or 6653
    return '%s:%s:%s' % (protocol, ip, port)


def _controller_targets(controllers):
    return [_controller_target(c) for c in (controllers or [])]


def _switch_connected(sw):
    try:
        return bool(sw.connected())
    except Exception as e:
        log.warning('Kiểm tra switch.connected() lỗi cho %s: %s', sw.name, e)
        return False


def _switch_diag(sw):
    """Best-effort OVS diagnostics for logs; never fail command handling."""
    rows = []
    for label, cmd in (
            ('controllers', 'ovs-vsctl get-controller %s' % sw.name),
            ('ports', 'ovs-vsctl list-ports %s' % sw.name),
            ('bridge', 'ovs-vsctl br-exists %s; echo $?' % sw.name)):
        try:
            out = sw.cmd(cmd).strip().replace('\n', '|')
        except Exception as e:
            out = 'error:%s' % e
        rows.append('%s=%s' % (label, out[:180]))
    return '; '.join(rows)


def _reattach_switch_controllers(sw, controllers):
    targets = _controller_targets(controllers)
    if not targets:
        return []
    # sw.start(net.controllers) should configure this already. Re-applying it
    # makes restart behavior explicit after sw.stop() deletes the bridge.
    sw.cmd('ovs-vsctl set-controller %s %s' % (sw.name, ' '.join(targets)))
    return targets


def _wait_switch_connected(sw, timeout=SWITCH_CONNECT_TIMEOUT):
    started = time.monotonic()
    deadline = started + timeout
    while time.monotonic() < deadline:
        if _switch_connected(sw):
            return True, (time.monotonic() - started)
        time.sleep(SWITCH_CONNECT_POLL)
    return _switch_connected(sw), (time.monotonic() - started)


def h_disable_link(net, target, params):
    ln = _resolve_link(net, target)
    if ln is None:
        return _reject(404, 'target not found: %s' % target)
    a, b = ln.intf1.node.name, ln.intf2.node.name
    net.configLinkStatus(a, b, 'down')
    return _ok('link %s-%s -> down' % (a, b))


def h_enable_link(net, target, params):
    ln = _resolve_link(net, target)
    if ln is None:
        return _reject(404, 'target not found: %s' % target)
    a, b = ln.intf1.node.name, ln.intf2.node.name
    net.configLinkStatus(a, b, 'up')
    return _ok('link %s-%s -> up' % (a, b))


def h_set_bandwidth(net, target, params):
    ln = _resolve_link(net, target)
    if ln is None:
        return _reject(404, 'target not found: %s' % target)
    if not isinstance(params, dict) or 'bw' not in params:
        return _reject(400, 'missing param: bw')
    bw = params['bw']
    if not isinstance(bw, (int, float)):
        return _reject(400, 'bw must be a number, got %r' % (bw,))
    if not (BW_MIN < bw <= BW_MAX):
        return _reject(400, 'bw out of range (%d, %d], got %s' %
                       (BW_MIN, BW_MAX, bw))
    cfg = {'bw': float(bw)}
    delay = getattr(ln, 'dt4n_delay', None)
    if delay:
        cfg['delay'] = delay
    ln.intf1.config(**cfg)
    ln.intf2.config(**cfg)
    ln.dt4n_bw = float(bw)
    return _ok('link bw -> %s Mbps' % bw)


def h_disable_host(net, target, params):
    h = _resolve_host(net, target)
    if h is None:
        return _reject(404, 'target not found: %s' % target)
    intf = h.defaultIntf()
    h.cmd('ifconfig %s down' % intf)
    return _ok('host %s -> down' % h.name)


def h_enable_host(net, target, params):
    h = _resolve_host(net, target)
    if h is None:
        return _reject(404, 'target not found: %s' % target)
    intf = h.defaultIntf()
    h.cmd('ifconfig %s up' % intf)
    return _ok('host %s -> up' % h.name)


def h_disable_switch(net, target, params):
    sw = _resolve_switch(net, target)
    if sw is None:
        return _reject(404, 'target not found: %s' % target)
    sw.dt4n_admin_down = True
    sw.stop(deleteIntfs=False)
    return _ok('switch %s -> down' % sw.name)


def h_enable_switch(net, target, params):
    sw = _resolve_switch(net, target)
    if sw is None:
        return _reject(404, 'target not found: %s' % target)
    sw.start(net.controllers)
    sw.dt4n_admin_down = False
    targets = _reattach_switch_controllers(sw, net.controllers)
    connected, waited = _wait_switch_connected(sw)
    if connected:
        flow_event('AGENT', 'SWITCH_CONNECTED', target=target,
                   detail='switch %s connected' % sw.name,
                   waitMs=int(round(waited * 1000)),
                   controllers=targets)
        return _ok('switch %s -> up (controller connected)' % sw.name)

    diag = _switch_diag(sw)
    flow_event('AGENT', 'SWITCH_CONNECT_TIMEOUT', target=target,
               level='WARN',
               detail=diag,
               waitMs=int(round(waited * 1000)),
               controllers=targets)
    return _reject(504, 'switch %s started but not connected to controller: %s'
                   % (sw.name, diag))


HANDLERS = {
    'disableLink': h_disable_link,
    'enableLink': h_enable_link,
    'setBandwidth': h_set_bandwidth,
    'disableHost': h_disable_host,
    'enableHost': h_enable_host,
    'disableSwitch': h_disable_switch,
    'enableSwitch': h_enable_switch,
}


def parse_message_event(raw, event_name=None, sse_fields=None):
    """Nhận CHUỖI event.data thô từ SSE -> trả dict {subject, value, correlation_id}
    hoặc None nếu không phải message thật (heartbeat/comment/JSON hỏng).

    LƯU Ý QUAN TRỌNG (observe, don't assume ở cấp DEBUG):
      Cấu trúc envelope message của Ditto TÙY VERSION và hơi rườm rà. Ở bản 4.2
      này ta CỐ TÌNH log cả raw để NHÌN TẬN MẮT cấu trúc thật, rồi mới chỉnh path
      parse cho khớp. ĐỪNG parse mù theo trí nhớ. Các key dưới đây là điểm KHỞI
      ĐẦU hợp lý theo Ditto Protocol; bạn chỉnh lại sau khi thấy raw thật.
    """
    if not raw or not raw.strip():
        return None                      # heartbeat/dòng rỗng -> bỏ qua

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        log.warning('SSE: bỏ qua event không parse được JSON: %.120s', raw)
        return None

    sse_fields = sse_fields or {}

    if not isinstance(msg, dict):
        correlation_id = (sse_fields.get('correlation-id')
                          or sse_fields.get('correlationId'))
        correlation_source = ('sse-field' if correlation_id is not None
                              else 'missing')
        return {'subject': event_name, 'value': msg,
                'correlation_id': correlation_id,
                'correlation_source': correlation_source,
                'raw': msg}

    # Ditto có 2 dạng hay gặp:
    # 1) Protocol envelope: subject nằm trong topic/subject, payload ở value.
    # 2) SSE message endpoint bản hiện tại: subject nằm ở dòng "event:",
    #    data chính là payload JSON.
    topic = msg.get('topic', '')
    subject = topic.rsplit('/', 1)[-1] if topic else msg.get('subject')
    if subject is None:
        subject = event_name

    if 'value' in msg or 'topic' in msg or 'headers' in msg:
        value = msg.get('value')
    else:
        value = msg

    headers = msg.get('headers', {}) or {}
    correlation_source = 'missing'
    correlation_id = None
    for source, candidate in (
            ('sse-field:correlation-id', sse_fields.get('correlation-id')),
            ('sse-field:correlationId', sse_fields.get('correlationId')),
            ('headers:correlation-id', headers.get('correlation-id')),
            ('headers:correlationId', headers.get('correlationId')),
            ('message:correlation-id', msg.get('correlation-id')),
            ('message:correlationId', msg.get('correlationId'))):
        if candidate is not None:
            correlation_id = candidate
            correlation_source = source
            break
    if correlation_id is None and isinstance(value, dict):
        body_cid = value.get('clientCorrelationId')
        if body_cid is not None:
            correlation_id = body_cid
            correlation_source = 'payload:clientCorrelationId'

    return {'subject': subject, 'value': value,
            'correlation_id': correlation_id,
            'correlation_source': correlation_source,
            'path': msg.get('path'),
            'topic': topic,
            'raw': msg}


def _event_target(parsed):
    value = parsed.get('value') if isinstance(parsed, dict) else None
    return value.get('target') if isinstance(value, dict) else None


def _iter_sse_lines(resp, stop_event=None):
    """Yield SSE lines as soon as bytes arrive.

    requests.iter_lines() can wait for its internal chunk buffer before yielding.
    Ditto live messages are tiny, so a delayed yield can make commands look slow
    even though the TCP stream already has the event. Reading tiny chunks and
    splitting lines ourselves keeps command delivery responsive.
    """
    encoding = resp.encoding or 'utf-8'
    decoder = codecs.getincrementaldecoder(encoding)(errors='replace')
    buf = ''
    for chunk in resp.iter_content(chunk_size=SSE_CHUNK_SIZE,
                                   decode_unicode=True):
        if stop_event is not None and stop_event.is_set():
            return
        if not chunk:
            continue
        if isinstance(chunk, bytes):
            chunk = decoder.decode(chunk)
            if not chunk:
                continue
        buf += chunk
        while '\n' in buf:
            line, buf = buf.split('\n', 1)
            if line.endswith('\r'):
                line = line[:-1]
            yield line

    tail = decoder.decode(b'', final=True)
    if tail:
        buf += tail

    if buf:
        if buf.endswith('\r'):
            buf = buf[:-1]
        yield buf


def handle_command(parsed, net=None, net_lock=None):
    """Xử lý một lệnh: whitelist, resolve/validate, thực thi và audit.

    Trả (ok, http_code, detail) để Lesson 4.4 dùng làm response.
    """
    subject = parsed.get('subject')
    value = parsed.get('value') or {}
    cid = parsed.get('correlation_id')
    target = value.get('target') if isinstance(value, dict) else None
    params = {k: v for k, v in value.items()
              if k not in ('target', 'clientCorrelationId')} \
             if isinstance(value, dict) else {}

    cached = processed_result(cid)
    if cached is not None:
        reason = 'replay suppressed'
        log.warning('BỎ QUA lệnh LẶP [%s] %s target=%s',
                    cid, subject, target)
        audit(cid, subject, target, params, 'duplicate_ignored', reason)
        flow_event('AGENT', 'DUPLICATE_IGNORED', cid, subject, target,
                   level='WARN', detail=reason, params=params,
                   code=cached[1], cachedDetail=cached[2])
        return cached

    log.info('NHẬN LỆNH [%s] %s target=%s params=%s',
             cid, subject, target, params)
    flow_event('AGENT', 'RECEIVE', cid, subject, target, params=params)

    handler = HANDLERS.get(subject)
    if handler is None:
        reason = 'unknown command: %s' % subject
        log.warning('TỪ CHỐI [%s]: %s', cid, reason)
        audit(cid, subject, target, params, 'rejected', reason)
        flow_event('AGENT', 'REJECT', cid, subject, target,
                   level='WARN', detail=reason)
        result_tuple = _reject(400, reason)
        remember_processed(cid, result_tuple)
        return result_tuple

    if net is None:
        reason = 'agent chưa gắn net (chạy sai tiến trình?)'
        audit(cid, subject, target, params, 'error', reason)
        flow_event('AGENT', 'ERROR', cid, subject, target,
                   level='ERROR', detail=reason)
        result_tuple = _reject(500, reason)
        remember_processed(cid, result_tuple)
        return result_tuple

    try:
        # Khóa cả resolve + execute để trạng thái net không đổi giữa chừng.
        flow_event('AGENT', 'EXECUTE_START', cid, subject, target)
        if net_lock is not None:
            lock_wait_started = time.monotonic()
            with net_lock:
                wait_ms = (time.monotonic() - lock_wait_started) * 1000
                log.info('LOCK_WAIT [%s] %s target=%s %.0fms',
                         cid, subject, target, wait_ms)
                flow_event('AGENT', 'LOCK_WAIT', cid, subject, target,
                           waitMs=int(round(wait_ms)))
                ok, code, detail = handler(net, target, params)
        else:
            ok, code, detail = handler(net, target, params)
    except Exception as e:
        log.exception('THỰC THI LỖI [%s] %s: %s', cid, subject, e)
        audit(cid, subject, target, params, 'error', str(e))
        flow_event('AGENT', 'EXECUTE_ERROR', cid, subject, target,
                   level='ERROR', detail=str(e))
        result_tuple = _reject(500, 'execution error: %s' % e)
        remember_processed(cid, result_tuple)
        return result_tuple

    result = 'ok' if ok else 'rejected'
    log.info('%s [%s] %s target=%s -> %s',
             'THỰC THI' if ok else 'TỪ CHỐI', cid, subject, target, detail)
    audit(cid, subject, target, params, result, None if ok else detail)
    flow_event('AGENT', 'EXECUTE_DONE' if ok else 'REJECT',
               cid, subject, target,
               level='INFO' if ok else 'WARN',
               detail=detail, code=code)
    result_tuple = (ok, code, detail)
    remember_processed(cid, result_tuple)
    return result_tuple


def send_response(session, thing_id, subject, correlation_id, http_code, detail, ok,
                  correlation_source=None, original_path=None, original_topic=None):
    """Gửi biên nhận tức thì cho lệnh đã xử lý, nếu stream cung cấp correlation-id.

    Không cập nhật twin state ở đây. State thật vẫn đi vòng Mininet -> Sync Agent
    -> Ditto, đúng nguyên tắc observe don't assume.
    """
    if not correlation_id:
        log.warning('Message không có correlation-id -> không gửi được response')
        flow_event('AGENT', 'RESPONSE_SKIP', correlation_id, subject, thing_id,
                   level='WARN', detail='missing correlation-id')
        return
    if not subject:
        log.warning('Message không có subject -> không gửi được response [%s]',
                    correlation_id)
        flow_event('AGENT', 'RESPONSE_SKIP', correlation_id, subject, thing_id,
                   level='WARN', detail='missing subject')
        return

    # Response cho lệnh gửi tới inbox phải đi ra chiều outbox. Gửi lại inbox sẽ
    # tự tạo một lệnh mới cho Command Agent và có nguy cơ lặp.
    url = '%s/things/%s/outbox/messages/%s' % (
        DITTO_BASE_URL, thing_id, subject)
    body = {
        'status': 'accepted' if ok else 'rejected',
        'action': subject,
        'code': http_code,
        'result': detail,
    }
    headers = {
        'Content-Type': 'application/json',
        'correlation-id': correlation_id,
    }
    try:
        flow_event('AGENT', 'RESPONSE_SEND', correlation_id, subject, thing_id,
                   code=http_code, ok=ok,
                   correlationSource=correlation_source,
                   originalPath=original_path,
                   originalTopic=original_topic)
        r = session.post(url, json=body, headers=headers, auth=DITTO_AUTH,
                         params={'timeout': 0}, timeout=HTTP_TIMEOUT)
        if r.status_code not in (200, 201, 202, 204):
            log.warning('Gửi response [%s] trả HTTP %d: %.160s',
                        correlation_id, r.status_code, r.text)
            flow_event('AGENT', 'RESPONSE_WARN', correlation_id, subject, thing_id,
                       level='WARN', http_status=r.status_code,
                       detail=r.text[:160])
        else:
            flow_event('AGENT', 'RESPONSE_OK', correlation_id, subject, thing_id,
                       http_status=r.status_code)
    except Exception as e:
        log.warning('Gửi response [%s] lỗi (bỏ qua): %s', correlation_id, e)
        flow_event('AGENT', 'RESPONSE_ERROR', correlation_id, subject, thing_id,
                   level='ERROR', detail=str(e))


def _stream_once(session, stop_event, net, net_lock):
    """Mở MỘT phiên SSE, đọc từng dòng cho tới khi đứt/stop. Trả về khi cần
    reconnect. Không tự ngủ — vòng ngoài lo reconnect delay."""
    headers = {
        'Accept': 'text/event-stream',
        'Accept-Encoding': 'identity',
        'Cache-Control': 'no-cache',
    }
    with session.get(INBOX_SSE_URL, headers=headers, auth=DITTO_AUTH,
                     stream=True, timeout=SSE_READ_TIMEOUT) as resp:
        if resp.status_code != 200:
            if resp.status_code == 404:
                log.error(
                    'SSE 404: controller Thing "%s" chưa tồn tại trong Ditto. '
                    'Command Agent không thể nghe lệnh. Chạy lại bootstrap: '
                    'python3 -m bridge.bootstrap --create --spec ditto/topology_spec.json. '
                    'Tạo thủ công nếu cần: curl -u ditto:ditto -X PUT '
                    '%s/things/%s -H "Content-Type: application/json" '
                    '-d \'{"policyId":"%s"}\'',
                    CONTROLLER_THING_ID, DITTO_BASE_URL,
                    CONTROLLER_THING_ID, POLICY_ID)
                flow_event('AGENT', 'SSE_404', target=CONTROLLER_THING_ID,
                           level='ERROR',
                           detail='controller Thing missing')
            elif resp.status_code == 403:
                log.error(
                    'SSE 403: Policy thiếu quyền message:/ READ cho controller '
                    'Thing "%s". Kiểm tra ditto/policy.json và chạy lại bootstrap.',
                    CONTROLLER_THING_ID)
                flow_event('AGENT', 'SSE_403', target=CONTROLLER_THING_ID,
                           level='ERROR',
                           detail='missing message:/ READ')
            else:
                log.error('SSE mở thất bại: HTTP %d (%s)',
                          resp.status_code, resp.text[:120])
                flow_event('AGENT', 'SSE_OPEN_FAIL', target=CONTROLLER_THING_ID,
                           level='ERROR', http_status=resp.status_code,
                           detail=resp.text[:120])
            return
        log.info('SSE kết nối OK, đang nghe lệnh tại %s', INBOX_SSE_URL)
        flow_event('AGENT', 'SSE_OPEN', target=CONTROLLER_THING_ID,
                   detail=INBOX_SSE_URL)

        # SSE gói event là một nhóm field "event:", "data:", có thể kèm
        # metadata tùy Ditto version. Đọc bằng _iter_sse_lines để tránh
        # requests.iter_lines() giữ event nhỏ trong buffer nội bộ.
        fields = {}
        data_buf = []
        for line in _iter_sse_lines(resp, stop_event=stop_event):
            if stop_event is not None and stop_event.is_set():
                log.info('Nhận stop_event -> đóng SSE.')
                return

            if line is None:
                continue
            if line == '':
                # dòng trống = HẾT một event -> ghép buffer, xử lý, reset.
                if data_buf:
                    raw = '\n'.join(data_buf)
                    fields['data'] = raw
                    data_buf = []
                    parsed = parse_message_event(raw,
                                                 event_name=fields.get('event'),
                                                 sse_fields=fields)
                    if parsed is not None:
                        flow_event('AGENT', 'SSE_EVENT',
                                   parsed.get('correlation_id'),
                                   parsed.get('subject'),
                                   _event_target(parsed),
                                   eventName=fields.get('event'),
                                   bytes=len(raw),
                                   correlationSource=parsed.get('correlation_source'),
                                   path=parsed.get('path'),
                                   topic=parsed.get('topic'),
                                   sseFields=sorted(k for k in fields if k != 'data'))
                        try:
                            ok, code, detail = handle_command(
                                parsed, net=net, net_lock=net_lock)
                            # Phản hồi tức thì: chỉ là biên nhận, không PATCH state.
                            send_response(session,
                                          CONTROLLER_THING_ID,
                                          parsed.get('subject'),
                                          parsed.get('correlation_id'),
                                          code, detail, ok,
                                          correlation_source=parsed.get('correlation_source'),
                                          original_path=parsed.get('path'),
                                          original_topic=parsed.get('topic'))
                        except Exception as e:
                            # 1 lệnh lỗi KHÔNG được làm sập stream (defensive).
                            log.exception('Xử lý lệnh lỗi (bỏ qua event): %s', e)
                fields = {}
                data_buf = []
                continue

            if line.startswith(':'):
                continue                 # comment/heartbeat của SSE -> bỏ qua
            if ':' in line:
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.lstrip()
                if key == 'data':
                    data_buf.append(value)
                elif key:
                    fields[key] = value
            else:
                fields[line.strip()] = ''


def run(net=None, net_lock=None, stop_event=None):
    """Vòng đời Command Agent với RECONNECT tự động.

    Bản 4.2: net và net_lock nhận vào nhưng CHƯA dùng (chưa chạm mạng). Nhận
    SẴN từ bây giờ để 4.3 dùng ngay, không phải đổi chữ ký hàm.
    """
    log.info('Command Agent start (bản 4.4: nghe + thực thi + response). controller=%s',
             CONTROLLER_THING_ID)
    session = requests.Session()
    session.auth = DITTO_AUTH

    while not (stop_event is not None and stop_event.is_set()):
        try:
            _stream_once(session, stop_event, net, net_lock)
        except (requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.Timeout) as e:
            log.warning('SSE đứt (%s) -> reconnect sau %.1fs',
                        type(e).__name__, RECONNECT_DELAY)
        except Exception as e:
            log.exception('SSE lỗi bất ngờ -> reconnect sau %.1fs: %s',
                          RECONNECT_DELAY, e)

        # Ngủ trước khi mở lại (trừ khi được yêu cầu dừng).
        if stop_event is not None:
            if stop_event.wait(RECONNECT_DELAY):
                break
        else:
            time.sleep(RECONNECT_DELAY)

    log.info('Command Agent dừng.')
