#!/usr/bin/env python3
"""
ditto_common.py — Hằng số + quy ước đặt tên dùng CHUNG cho mọi script nói chuyện
với Ditto (bootstrap, sync_agent, verify, dashboard...). LỚP 2 (Bridge).

VÌ SAO TÁCH FILE NÀY RA (Lesson 2.2 Phần 3.2 - DRY / single source of truth):
  thingId được sinh ở RẤT NHIỀU nơi. Nếu mỗi nơi tự ghép chuỗi, đổi quy ước
  (vd đổi namespace) phải sửa N chỗ -> dễ sót -> link 'h1-s1' chỗ này, 's1-h1'
  chỗ kia -> 2 Thing cho 1 link. Gom về MỘT nơi = một nguồn sự thật.
"""

import os

# ---------------------------------------------------------------------------
# HẰNG SỐ KẾT NỐI — đọc từ biến môi trường, fallback mặc định localhost.
# Đọc từ env để KHÔNG hardcode -> đổi host/cổng/mật khẩu không phải sửa code
# (cũng tránh commit mật khẩu - nhớ .gitignore .env ở buổi trước).
# ---------------------------------------------------------------------------
DITTO_BASE_URL = os.environ.get('DITTO_BASE_URL', 'http://localhost:8080/api/2')
DITTO_USER     = os.environ.get('DITTO_USER', 'ditto')
DITTO_PASSWORD = os.environ.get('DITTO_PASSWORD', 'ditto')
DITTO_AUTH     = (DITTO_USER, DITTO_PASSWORD)

NAMESPACE = os.environ.get('DT4N_NAMESPACE', 'org.dt4n')
POLICY_ID = '%s:default-policy' % NAMESPACE

HTTP_TIMEOUT = 5   # giây — tránh treo vô hạn nếu Ditto không phản hồi


# ---------------------------------------------------------------------------
# CHUẨN HÓA TÊN — chặn bẫy ký tự (Lesson 2.2 Phần 2.5).
# Ditto cấm khoảng trắng, '/', và ký tự lạ trong name. Mininet hiếm khi tạo
# tên xấu, nhưng chuẩn hóa cho chắc -> không bao giờ ăn 400 vì thingId.
# ---------------------------------------------------------------------------
def _sanitize(name):
    """Giữ chữ/số và -_; thay phần còn lại bằng '_'."""
    out = []
    for ch in str(name):
        if ch.isalnum() or ch in '-_':
            out.append(ch)
        else:
            out.append('_')
    return ''.join(out)


# ---------------------------------------------------------------------------
# QUY ƯỚC thingId — MỘT nơi duy nhất sinh ra (DRY).
# ---------------------------------------------------------------------------
def make_thing_id_host(name):
    return '%s:host-%s' % (NAMESPACE, _sanitize(name))

def make_thing_id_switch(name):
    return '%s:switch-%s' % (NAMESPACE, _sanitize(name))

def make_thing_id_link(name_a, name_b):
    """CANONICAL: sort 2 đầu theo alphabet -> 'h1-s1' và 's1-h1' ra CÙNG id.
    Chống bẫy 'link trùng' (Lesson 2.2 Phần 8, dòng cuối bảng)."""
    lo, hi = sorted([_sanitize(name_a), _sanitize(name_b)])
    return '%s:link-%s-%s' % (NAMESPACE, lo, hi)


def make_thing_id_path(src, dst):
    """Directed path Thing id: h1->srv1 and srv1->h1 are different paths."""
    return '%s:path-%s-%s' % (NAMESPACE, _sanitize(src), _sanitize(dst))
