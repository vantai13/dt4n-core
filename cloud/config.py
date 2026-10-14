#!/usr/bin/env python3
"""
config.py — Cấu hình CHUNG cho mọi script AWS của DT4N (GĐ1).

VÌ SAO TÁCH RA (cùng lý do với bridge/ditto_common.py):
  tên tài nguyên, region, trần số máy được dùng ở nhiều file (infra, collector,
  actuator, controller). Gom về MỘT nơi để đổi một chỗ là đủ.

Mọi giá trị đọc từ biến môi trường, có mặc định an toàn. KHÔNG có key AWS ở
đây: boto3 tự đọc key từ ~/.aws/credentials hoặc biến môi trường.
"""

import os
from pathlib import Path

# Region: Singapore là region gần Việt Nam nhất. Đổi bằng AWS_REGION nếu cần.
REGION = (os.environ.get('AWS_REGION')
          or os.environ.get('AWS_DEFAULT_REGION')
          or 'ap-southeast-1')

# Tiền tố tên mọi tài nguyên -> dễ nhận ra, dễ dọn.
PREFIX = os.environ.get('DT4N_CLOUD_PREFIX', 'dt4n')

# Tag gắn lên MỌI tài nguyên tạo ra. Dùng để lọc chi phí và để dọn sót.
TAG_KEY = 'Project'
TAG_VALUE = PREFIX

# Loại máy. t3.micro là loại nhỏ phổ biến; đổi bằng DT4N_INSTANCE_TYPE.
INSTANCE_TYPE = os.environ.get('DT4N_INSTANCE_TYPE', 't3.micro')

# TRẦN AN TOÀN: dù ai đặt env lớn hơn, ASG không bao giờ quá 3 máy.
HARD_MAX = 3
MAX_SIZE = min(int(os.environ.get('DT4N_MAX_SIZE', str(HARD_MAX))), HARD_MAX)

# AMI Amazon Linux 2023 mới nhất, lấy qua tham số công khai của AWS (SSM).
# Nhờ vậy không phải dò AMI id theo từng region.
AMI_PARAM = '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64'

# Dải IP được phép gọi vào ALB. Rỗng = tự lấy IP công khai của máy bạn (/32).
ALLOWED_CIDR = os.environ.get('DT4N_ALLOWED_CIDR', '')

# File ghi lại tài nguyên đã tạo (chỉ để tiện xem; dọn dẹp không phụ thuộc nó).
STATE_PATH = Path(os.environ.get('DT4N_CLOUD_STATE', 'cloud/.state.json'))

# Tên tài nguyên (ALB và target group: tối đa 32 ký tự, chỉ chữ/số/gạch nối).
NAMES = {
    'alb_sg': '%s-alb-sg' % PREFIX,
    'web_sg': '%s-web-sg' % PREFIX,
    'lt':     '%s-lt' % PREFIX,
    'tg':     '%s-tg' % PREFIX,
    'alb':    '%s-alb' % PREFIX,
    'asg':    '%s-asg' % PREFIX,
}


def tag_list():
    """Tag dạng EC2/ELB: [{'Key':..., 'Value':...}]."""
    return [{'Key': TAG_KEY, 'Value': TAG_VALUE}]
