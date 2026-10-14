#!/usr/bin/env python3
"""
whatif/server.py — GĐ3.4: trang "thử trước khi làm" (what-if), chạy CỤC BỘ.

VÌ SAO LÀ TRANG RIÊNG, KHÔNG CHÈN VÀO DASHBOARD
  Mọi file trong dashboard/src nằm trong bộ đóng băng runtime của Phase 7/8
  (scripts/phase7_freeze_set.dashboard_src). Sửa hay thêm file ở đó = trôi bộ đóng băng,
  giống chuyện sổ ghim ở GĐ2. Trang riêng ở whatif/static/ không đụng gì đã niêm phong.

HAI NGUYÊN TẮC AN TOÀN
  1. CHỈ ĐỌC: server không có đường nào gửi lệnh xuống mạng (không gọi hộp thư controller,
     không import command_agent). Mọi "hành động" chỉ được áp lên BẢN SỐ.
  2. CHỈ NGHE 127.0.0.1: bài học từ Mongo/gateway Ditto mở ra mọi giao diện mạng (rổ B).

API
  GET  /                  trang whatif.html
  GET  /api/snapshots     các run Phase 5 tập test (thử không cần Ditto)
  POST /api/ask           {"source": "twin"|"snapshot", "run": "...", "tick": 30,
                           "restore_nominal": false, "allow_stale": false, "actions": [...]}
       200 {report, result, topology} | 400 yêu cầu/hành động sai | 409 twin không đủ tươi
       413 thân yêu cầu quá lớn | 503 không đọc được Ditto
  Mỗi câu hỏi ghi một dòng vào logs/whatif_queries.jsonl (hỏi gì, trả lời tóm tắt).

CÁCH CHẠY
    python3 -m whatif.server              # rồi mở http://127.0.0.1:8091
    python3 -m whatif.server --port 8092
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ml import campaign as C
from whatif import live as L
from whatif import model as M

HOST = '127.0.0.1'
PORT = 8091
MAX_BODY = 16 * 1024
MAX_ACTIONS = 10
OPS = ('setBandwidth', 'disableLink', 'enableLink', 'addDemand')
STATIC = Path(__file__).resolve().parent / 'static' / 'whatif.html'
QUERY_LOG = C.ROOT / 'logs' / 'whatif_queries.jsonl'
RUN_RE = re.compile(r'^[A-Za-z0-9_-]+$')


class AskError(Exception):
    def __init__(self, status: int, message: str, extra=None):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra or {}


def snapshot_runs() -> list:
    contract = C.load_contract(C.ROOT / 'results/report/experiment_matrix.json')
    return list(contract['split']['test'])


def topology() -> dict:
    spec = M.load_spec()
    return {'nodes': [h['name'] for h in spec['hosts']] + [s['name'] for s in spec['switches']],
            'links': [{'key': M.canonical(a, b), 'a': a, 'b': b} for a, b in spec['links']]}


def _check_actions(actions) -> list:
    if not isinstance(actions, list) or len(actions) > MAX_ACTIONS:
        raise AskError(400, 'actions phải là danh sách tối đa %d hành động' % MAX_ACTIONS)
    for a in actions:
        if not isinstance(a, dict) or a.get('op') not in OPS:
            raise AskError(400, 'hành động không hợp lệ: %r' % (a,))
    return actions


def handle_ask(payload: dict, read_twin=None) -> dict:
    """Hàm thuần (không HTTP) để test được. Ném AskError khi phải trả mã lỗi."""
    if not isinstance(payload, dict):
        raise AskError(400, 'thân yêu cầu phải là một JSON object')
    actions = _check_actions(payload.get('actions', []))
    source = payload.get('source', 'twin')
    if source == 'snapshot':
        run, tick = payload.get('run'), payload.get('tick', 30)
        if not isinstance(run, str) or not RUN_RE.match(run) or run not in snapshot_runs():
            raise AskError(400, 'run không thuộc tập test Phase 5: %r' % (run,))
        if not isinstance(tick, int) or not 0 <= tick < 60:
            raise AskError(400, 'tick phải là số nguyên 0..59')
        things, ages, meta = L.read_snapshot(run, tick)
    elif source == 'twin':
        things, ages, meta = (read_twin or L.read_twin)()
    else:
        raise AskError(400, 'source phải là "twin" hoặc "snapshot"')
    if not things:
        raise AskError(503, 'không đọc được Thing nào từ Ditto (Ditto có đang chạy không?)')
    state, report = L.state_from_things(things, ages,
                                        restore_nominal=bool(payload.get('restore_nominal')))
    report['source'] = meta['source']
    if not report['ok'] and not payload.get('allow_stale'):
        raise AskError(409, 'dữ liệu twin không đủ tươi hoặc thiếu Thing', {'report': report})
    try:
        result = L.ask(state, actions, label='sau hành động')
    except ValueError as exc:
        raise AskError(400, str(exc))
    return {'report': report, 'result': result, 'topology': topology(),
            'note': 'Dự đoán trên bản số. Không lệnh nào được gửi xuống mạng.'}


def log_query(payload, status, body) -> None:
    try:
        result = (body or {}).get('result') or {}
        row = {'t': time.time(), 'status': status,
               'source': payload.get('source') if isinstance(payload, dict) else None,
               'run': payload.get('run') if isinstance(payload, dict) else None,
               'tick': payload.get('tick') if isinstance(payload, dict) else None,
               'actions': payload.get('actions') if isinstance(payload, dict) else None,
               'max_rho': {k: v['prediction']['summary']['max_rho'] for k, v in result.items()},
               'error': (body or {}).get('error')}
        QUERY_LOG.parent.mkdir(exist_ok=True)
        with open(QUERY_LOG, 'a', encoding='utf-8') as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
    except OSError:
        pass                                            # nhật ký không được làm hỏng câu trả lời


class Handler(BaseHTTPRequestHandler):
    server_version = 'dt4n-whatif/1'

    def _send(self, status: int, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else \
            json.dumps(body, ensure_ascii=False, default=list).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self._send(200, STATIC.read_bytes(), 'text/html; charset=utf-8')
        elif self.path == '/api/snapshots':
            self._send(200, {'runs': snapshot_runs(), 'default_tick': 30})
        else:
            self._send(404, {'error': 'không có đường dẫn này'})

    def do_POST(self):
        if self.path != '/api/ask':
            return self._send(404, {'error': 'không có đường dẫn này'})
        payload = None
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_BODY:
                raise AskError(413, 'thân yêu cầu quá lớn')
            try:
                payload = json.loads(self.rfile.read(length) or b'{}')
            except json.JSONDecodeError:
                raise AskError(400, 'thân yêu cầu không phải JSON')
            status, body = 200, handle_ask(payload)
        except AskError as exc:
            status, body = exc.status, dict({'error': exc.message}, **exc.extra)
        log_query(payload, status, body)
        self._send(status, body)

    def log_message(self, fmt, *args):            # bớt ồn: chỉ in lỗi
        if args and str(args[1]).startswith(('4', '5')):
            super().log_message(fmt, *args)


def make_server(port=PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((HOST, port), Handler)


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m whatif.server')
    ap.add_argument('--port', type=int, default=PORT)
    ns = ap.parse_args(argv)
    srv = make_server(ns.port)
    print('What-if đang chạy: http://%s:%d   (Ctrl+C để dừng)' % (HOST, ns.port))
    print('Chỉ đọc twin và dự đoán; không gửi lệnh nào xuống mạng.')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
