#!/usr/bin/env python3
"""
diagnose.py — Kiểm tra Ditto sống & Policy đúng TRƯỚC khi bootstrap. LỚP 2.

Giải quyết 2 nỗi lo: (1) "Ditto chưa chắc chạy", (2) bẫy 403 do subject Policy
không khớp prefix nginx. Chạy cái này TRƯỚC bootstrap để khỏi mò lỗi.

CHẠY:  python3 -m bridge.diagnose
"""
import sys
import time
import requests

from bridge.ditto_common import DITTO_BASE_URL, DITTO_AUTH, POLICY_ID, HTTP_TIMEOUT

# Bỏ '/api/2' để lấy gốc, gọi /health (endpoint kiểm tra sức khỏe của Ditto)
ROOT = DITTO_BASE_URL.rsplit('/api/', 1)[0]


def step(msg):
    print('\n>>> ' + msg)


def check_alive():
    """Tầng 1: Ditto có sống không? Gọi /health (không cần auth)."""
    step('1) Ditto còn sống? (GET /health)')
    try:
        r = requests.get(ROOT + '/health', timeout=HTTP_TIMEOUT)
    except requests.exceptions.ConnectionError:
        print('  ❌ KHÔNG kết nối được %s' % ROOT)
        print('     -> Ditto chưa chạy. Vào thư mục docker-compose của Ditto và:')
        print('        docker compose up -d   (rồi đợi ~1-2 phút cho 5 service lên)')
        return False
    print('  ✅ Phản hồi HTTP %d' % r.status_code)
    try:
        data = r.json()
        status = data.get('status', '?')
        print('     status tổng: %s' % status)
        if status != 'UP':
            print('     ⚠ Có service chưa UP — đợi thêm hoặc xem `docker compose ps`')
    except Exception:
        print('     (không parse được JSON health, nhưng có phản hồi là tốt)')
    return True


def check_auth():
    """Tầng 2: basic auth qua nginx được không? (phân biệt 401)."""
    step('2) Basic auth qua được nginx? (GET /api/2/things)')
    r = requests.get(DITTO_BASE_URL + '/things', auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
    if r.status_code == 401:
        print('  ❌ 401 Unauthorized -> sai user/password hoặc nginx chưa bật auth.')
        return False
    if r.status_code >= 500:
        print('  ❌ HTTP %d -> nginx/proxy tới Ditto gateway đang lỗi hoặc trỏ nhầm port.' % r.status_code)
        print('     -> Kiểm tra DITTO_BASE_URL, docker compose ps, và port Ditto nginx.')
        return False
    print('  ✅ Không bị 401 (status %d) -> auth OK' % r.status_code)
    return True


def detect_subject_prefix():
    """Tầng 3 (quan trọng nhất): phát hiện ĐÚNG prefix subject nginx phát ra.
    Cách làm: tạo 1 Policy thử với subject ứng viên, rồi thử ghi 1 Thing dùng
    policy đó. Prefix nào cho phép GHI -> đó là prefix đúng cho máy bạn."""
    step('3) Phát hiện prefix subject đúng (chống bẫy 403)')
    candidates = ['nginx:ditto', 'nginx-basic:ditto']
    namespace = POLICY_ID.rsplit(':', 1)[0]

    working = None
    for idx, subj in enumerate(candidates):
        suffix = '__diag-%d-%d' % (int(time.time() * 1000), idx)
        test_pid = namespace + ':' + suffix + '-policy'
        test_tid = namespace + ':' + suffix + '-thing'
        pol = {
            'policyId': test_pid,
            'entries': {'owner': {
                'subjects': {subj: {'type': 'basic-auth user'}},
                'resources': {
                    'thing:/':  {'grant': ['READ', 'WRITE'], 'revoke': []},
                    'policy:/': {'grant': ['READ', 'WRITE'], 'revoke': []},
                },
            }},
        }
        rp = requests.put('%s/policies/%s' % (DITTO_BASE_URL, test_pid),
                          json=pol, auth=DITTO_AUTH, timeout=HTTP_TIMEOUT)
        rt = requests.put('%s/things/%s' % (DITTO_BASE_URL, test_tid),
                          json={'policyId': test_pid}, auth=DITTO_AUTH,
                          timeout=HTTP_TIMEOUT)
        ok = rt.status_code in (201, 204)
        print('  subject "%s": policy %d, thing %d -> %s'
              % (subj, rp.status_code, rt.status_code, 'DÙNG ĐƯỢC' if ok else 'không'))
        if rp.status_code >= 400:
            print('    policy error:', rp.text[:200])
        if rt.status_code >= 400:
            print('    thing error :', rt.text[:200])
        if ok and working is None:
            working = subj
        # dọn thing thử
        requests.delete('%s/things/%s' % (DITTO_BASE_URL, test_tid), auth=DITTO_AUTH)
        requests.delete('%s/policies/%s' % (DITTO_BASE_URL, test_pid), auth=DITTO_AUTH)
        if working:
            break

    if working:
        print('\n  ✅ Prefix ĐÚNG cho máy bạn: "%s"' % working)
        print('     -> Mở ditto/policy.json, đảm bảo subject là "%s"' % working)
    else:
        print('\n  ❌ Cả 2 ứng viên đều không ghi được Thing.')
        print('     -> Xem nginx.conf trong docker-compose Ditto để biết prefix.')
    return working


def main():
    print('=== DITTO DIAGNOSE ===')
    print('BASE_URL =', DITTO_BASE_URL)
    if not check_alive():
        sys.exit(1)
    if not check_auth():
        sys.exit(1)
    detect_subject_prefix()
    print('\n=== XONG. Nếu cả 3 tầng OK -> chạy bootstrap an toàn. ===')


if __name__ == '__main__':
    main()
