#!/usr/bin/env python3
"""
pusher.py — Gửi PATCH lên Ditto, CÓ resilience (Lesson 2.4). LỚP 2 (Bridge).

NÂNG CẤP so với 2.3: thêm retry + exponential backoff + jitter, phân loại lỗi
transient/permanent. Retry nằm Ở ĐÂY (tầng vi mô - lo cho 1 request), KHÔNG ở
sync_agent (tầng vĩ mô - lo cả vòng lặp). Đây là Single Responsibility.

NGUYÊN TẮC (Lesson 2.4 Phần 2):
  - Transient (5xx, timeout, ConnectionError) -> RETRY với backoff.
  - Permanent (400/401/403) -> log + bỏ, KHÔNG retry (retry vô nghĩa, còn dội
    bom server). Đây là bài học "bằng máu của ngành".
  - MAX_RETRIES giới hạn -> không kẹt vô hạn khi Ditto chết hẳn.
  - Timeout BẮT BUỘC mọi request (default của requests là CHỜ VÔ HẠN - bẫy).
"""

import json
import logging
import os
import random
import time

import requests

from bridge.ditto_common import DITTO_BASE_URL, DITTO_AUTH, HTTP_TIMEOUT

log = logging.getLogger('pusher')

MERGE_PATCH_HEADERS = {'Content-Type': 'application/merge-patch+json'}

# ---- Cấu hình retry (Lesson 2.4 Phần 2.3-2.4) ----
MAX_RETRIES  = 3       # số lần thử LẠI sau lần đầu (tổng tối đa 4 lần gọi)
BASE_BACKOFF = 1.0     # giây — thời gian chờ gốc
MAX_BACKOFF  = 8.0     # giây — trần chờ (không để backoff phình vô hạn)
JITTER       = 0.3     # ±30% nhiễu ngẫu nhiên — chống thundering herd
PUSH_TRACE_PATH = os.environ.get('DT4N_PUSH_TRACE', '')

# ---- Chế độ fast-fail cho RL training/diagnostic ----
# Production ưu tiên bền: retry kiên nhẫn để không mất update.
# Training ưu tiên nhịp ổn định: Ditto treo thì bỏ nhanh, cycle sau bù lại.
FAST_PUSH = os.environ.get('DT4N_FAST_PUSH', '0') == '1'
if FAST_PUSH:
    MAX_RETRIES = 0
FAST_PUSH_TIMEOUT = float(os.environ.get('DT4N_FAST_PUSH_TIMEOUT', '1.0'))

# Status code coi là TẠM THỜI -> đáng retry. 4xx KHÔNG nằm đây (vĩnh viễn).
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
PERMANENT_STATUSES = {400, 401, 403, 404}


def compute_backoff(attempt):
    """Exponential backoff + jitter. attempt=0 -> ~1s, 1 -> ~2s, 2 -> ~4s...
    jitter ngẫu nhiên để nhiều client KHÔNG retry đồng loạt (thundering herd)."""
    base = min(MAX_BACKOFF, BASE_BACKOFF * (2 ** attempt))
    noise = base * JITTER * random.uniform(-1, 1)
    return max(0.1, base + noise)


def _do_patch(thing_id, features_patch, session=None):
    """PATCH 1 Thing, retry exponential backoff khi lỗi tạm thời.
    Trả True nếu thành công (kể cả sau retry), False nếu hết retry/lỗi vĩnh viễn."""
    if not features_patch:
        return True

    body = features_patch if 'features' in features_patch \
        else {'features': features_patch}
    url = '%s/things/%s' % (DITTO_BASE_URL, thing_id)
    http = session or requests
    timeout = FAST_PUSH_TIMEOUT if FAST_PUSH else HTTP_TIMEOUT

    # range(MAX_RETRIES+1): lần đầu (attempt=0) + MAX_RETRIES lần thử lại
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = http.patch(url, json=body, headers=MERGE_PATCH_HEADERS,
                           auth=DITTO_AUTH, timeout=timeout)

            # --- THÀNH CÔNG ---
            if r.status_code in (200, 204):
                if attempt > 0:
                    log.info('PATCH %s OK ở lần thử %d', thing_id, attempt + 1)
                return True

            # --- LỖI VĨNH VIỄN -> không retry, log để sửa code/config ---
            if r.status_code in PERMANENT_STATUSES:
                log.error('PATCH %s lỗi vĩnh viễn %d: %s',
                          thing_id, r.status_code, r.text[:200])
                return False

            # --- LỖI TẠM THỜI -> backoff rồi thử lại (nếu còn lượt) ---
            if r.status_code in RETRY_STATUSES and attempt < MAX_RETRIES:
                wait = compute_backoff(attempt)
                log.warning('PATCH %s -> %d, thử lại sau %.1fs (lần %d/%d)',
                            thing_id, r.status_code, wait, attempt + 1, MAX_RETRIES)
                time.sleep(wait)
                continue

            # hết lượt hoặc status lạ
            log.error('PATCH %s thất bại: %d', thing_id, r.status_code)
            return False

        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            # lỗi mạng = tạm thời -> retry
            if attempt < MAX_RETRIES:
                wait = compute_backoff(attempt)
                log.warning('PATCH %s lỗi mạng (%s), thử lại sau %.1fs',
                            thing_id, type(e).__name__, wait)
                time.sleep(wait)
                continue
            log.error('PATCH %s bỏ cuộc sau %d lần: %s', thing_id, attempt + 1, e)
            return False

        except Exception as e:
            # lỗi KHÔNG lường -> không retry, log đầy đủ traceback để điều tra,
            # nhưng KHÔNG để nó ném ra ngoài làm sập agent (catch-all có chủ đích)
            log.exception('PATCH %s lỗi bất ngờ: %s', thing_id, e)
            return False

    return False


def _trace_t_source(features_patch):
    """Extract meta.tSource from either accepted PATCH body shape."""
    body = features_patch if isinstance(features_patch, dict) else {}
    features = body.get('features', body)
    try:
        return features['meta']['properties']['tSource']
    except (KeyError, TypeError):
        return None


def patch_thing(thing_id, features_patch, session=None):
    """PATCH one Thing and optionally trace source/send/ack timestamps.

    A0 keeps the original retry semantics in ``_do_patch``. Tracing is disabled
    unless ``DT4N_PUSH_TRACE`` is set before this module is imported.
    """
    t_send = time.time()
    ok = _do_patch(thing_id, features_patch, session=session)
    t_ack = time.time()
    if PUSH_TRACE_PATH:
        parent = os.path.dirname(os.path.abspath(PUSH_TRACE_PATH))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(PUSH_TRACE_PATH, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps({
                'thing_id': thing_id,
                't_source': _trace_t_source(features_patch),
                't_send': t_send,
                't_ack': t_ack,
                'push_ms': (t_ack - t_send) * 1000.0,
                'ok': bool(ok),
            }, sort_keys=True) + '\n')
    return ok


def push_changes(changes, session=None):
    """Gửi (tuần tự) mọi Thing đổi. Trả (n_ok, n_total).
    Mỗi patch_thing tự xử lý retry -> đây chỉ gom kết quả."""
    n_ok = 0
    for tid, patch in changes.items():
        if patch_thing(tid, patch, session=session):
            n_ok += 1
    return n_ok, len(changes)


def make_session():
    s = requests.Session()
    s.auth = DITTO_AUTH
    return s
