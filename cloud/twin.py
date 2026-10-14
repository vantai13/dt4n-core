#!/usr/bin/env python3
"""
twin.py — Hình dạng của Thing 'cloud-pool' trong Ditto (GĐ1.2).

Thing này là BẢN SAO SỐ của nhóm máy AWS (Auto Scaling Group + ALB).
Nó đứng cạnh các Thing host/switch/link của Mininet, cùng namespace, cùng policy.

    org.dt4n:cloud-pool
      attributes : type='cloud-pool', provider, region, asg, maxSize  (ít đổi)
      features   :
        capacity  : desired, min, max          (ASG được YÊU CẦU bao nhiêu máy)
        pool      : total, pending, inService, healthy, terminating
                                               (THỰC TẾ đang có bao nhiêu máy)
        instances : list = [{id, az, lifecycle, asgHealth, albHealth}, ...]
        meta      : tSource, pollOk, lastError, tAttempt  (độ tươi của dữ liệu)

Dashboard hiện tại bỏ qua Thing có type lạ (dashboard/src/lib/translate.js),
nên thêm Thing này không làm vỡ đồ thị Mininet.
"""

from bridge.ditto_common import NAMESPACE, POLICY_ID
from cloud import config as C

THING_ID = '%s:cloud-pool' % NAMESPACE


def thing_body():
    """Khung Thing rỗng để PUT một lần (giá trị 0 = chờ dữ liệu, như bootstrap.py)."""
    return {
        'policyId': POLICY_ID,
        'attributes': {
            'type': 'cloud-pool',
            'provider': 'aws',
            'region': C.REGION,
            'asg': C.NAMES['asg'],
            'maxSize': C.MAX_SIZE,
        },
        'features': {
            'capacity': {'properties': {'desired': 0, 'min': 0, 'max': 0}},
            'pool': {'properties': {'total': 0, 'pending': 0, 'inService': 0,
                                    'healthy': 0, 'terminating': 0}},
            'instances': {'properties': {'list': []}},
            'meta': {'properties': {'tSource': 0, 'pollOk': False,
                                    'lastError': '', 'tAttempt': 0}},
        },
    }


def snapshot_to_features(snap):
    """Ảnh chụp đọc từ AWS -> phần 'features' để merge-patch vào Thing.

    Gửi ĐẦY ĐỦ mọi feature mỗi chu kỳ (không chỉ phần đổi):
      - mất một lần đẩy thì lần sau tự sửa lại (reconcile theo mức);
      - tSource mới mỗi chu kỳ -> người đọc phân biệt được
        "không có gì đổi" với "không ai cập nhật".
    'instances.list' là MẢNG: merge-patch thay nguyên mảng, nên máy đã bị xóa
    biến mất khỏi twin. Nếu dùng object {instanceId: ...}, merge-patch sẽ giữ
    lại key của máy cũ mãi mãi (trừ khi gửi null cho từng key).
    """
    return {
        'capacity': {'properties': {
            'desired': snap['desired'], 'min': snap['min'], 'max': snap['max']}},
        'pool': {'properties': {
            'total': snap['total'], 'pending': snap['pending'],
            'inService': snap['inService'], 'healthy': snap['healthy'],
            'terminating': snap['terminating']}},
        'instances': {'properties': {'list': snap['instances']}},
        'meta': {'properties': {
            'tSource': snap['t_source'], 'pollOk': True,
            'lastError': '', 'tAttempt': snap['t_source']}},
    }


def error_features(err, t_attempt):
    """Khi đọc AWS lỗi: CHỈ báo lỗi, KHÔNG ghi tSource mới.

    tSource giữ nguyên = thời điểm đọc thành công gần nhất, nên tuổi dữ liệu
    (now - tSource) tăng dần. Người đọc (controller GĐ1.4) thấy dữ liệu cũ và
    không hành động dựa trên nó (gác theo độ tươi, như bài P6).
    """
    return {'meta': {'properties': {
        'pollOk': False, 'lastError': str(err)[:200], 'tAttempt': t_attempt}}}
