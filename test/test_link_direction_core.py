from bridge.collector import canonical_link_key
from twin.link_direction import (UPSTREAM_OF_CORE, alphabetical_side_a_is_correct,
                                 upstream_node)

CORE_LINKS = ['link-h1-s1', 'link-h2-s1', 'link-h3-s1', 'link-s1-s2',
              'link-s1-s3', 'link-s2-s3', 'link-s2-srv1', 'link-s3-srv2']


def test_moi_link_dt4n_core_nam_trong_ban_do_huong():
    """Sau khi thêm map, không link nào còn rơi vào alphabetical_fallback."""
    for key in CORE_LINKS:
        assert upstream_node(key) is not None, f'{key} thiếu trong UPSTREAM_OF'


def test_ban_do_khop_voi_ten_canonical():
    for name, (up, down) in UPSTREAM_OF_CORE.items():
        assert canonical_link_key(up, down) == 'link-' + name


def test_bang_chu_cai_tinh_co_dung_cho_ca_8_link_dt4n_core():
    """Ghim phát hiện của Lesson 5.1 bằng một biểu thức CHẠY ĐƯỢC.

    Dataset v2 dùng nhánh alphabetical_fallback. Test kiểm tra thứ tự
    bảng chữ cái khớp hướng tham chiếu trong map cho cả 8 link; không
    suy ra tỷ lệ tx/rx thực tế hoặc hướng mọi luồng từ tên node.

    Nếu ai đổi tên node (ví dụ s1 -> "core") test sẽ đỏ và chỉ thẳng vào
    cơ chế, thay vì để chiều đo đảo ngược âm thầm.
    """
    sai = [n for n in UPSTREAM_OF_CORE if not alphabetical_side_a_is_correct(n)]
    assert sai == [], f'bảng chữ cái sai chiều ở: {sai}'
