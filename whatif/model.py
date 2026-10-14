#!/usr/bin/env python3
"""
whatif/model.py — GĐ3.1: mô hình what-if "chất lỏng" cho testbed DT4N.

CÂU HỎI: nếu làm hành động X (đổi băng thông, tắt/bật link, thêm một luồng) thì tải
và mất gói trên từng link, từng luồng sẽ ra sao? Tính trên BẢN SỐ, không chạm mạng.

BA ĐẦU VÀO
  1. Dung lượng C của mỗi link (Mbps). Mỗi CHIỀU có hàng đợi riêng (TCLink đặt tc ở
     cả hai đầu), nên s1->s2 và s2->s1 là hai "ống" khác nhau, cùng dung lượng C.
  2. Nhu cầu: các luồng (src, dst, Mbps, kind). Twin KHÔNG biết đích của luồng, nên
     bảng ai-gửi-tới-đâu lấy từ cấu hình traffic -> đây là GIẢ ĐỊNH, phải khai.
  3. Đường đi: gọi ĐÚNG hàm Ryu đang dùng, mininet.gen_routes.next_hop_table(spec,
     excluded_edges). Tắt link = loại cạnh đó khỏi đồ thị = Ryu tính lại đường.
     (ml/design.py ghi "tĩnh = không reroute": đó là chỗ sai đã biết, bài 1.2.)

MÔ HÌNH (chất lỏng, mất gói tỉ lệ ở hàng đợi drop-tail)
  tải đến link  λ = tổng tốc độ các luồng ĐI TỚI link đó (sau khi đã mất ở link trước)
  ρ = λ / C;  nếu ρ > 1, mỗi luồng qua link chỉ giữ lại C/λ tốc độ của nó -> mất 1 − 1/ρ
  Mất ở link trước làm giảm tải link sau, nên phải lặp tới điểm bất động.

VÙNG HỢP LỆ (đi kèm MỌI kết quả, không giấu)
  Mô hình coi mọi luồng là KHÔNG ĐÀN HỒI (gửi đều bất kể mất gói): đúng với UDP.
  SAI với TCP đi qua link nghẽn: TCP lùi tốc độ, có khi bị khóa ngoài (bài 1.4: flood
  h1 -> mô hình nói h3 còn ~1,8 Mbps, đo được ≈ 0). Vì vậy mọi luồng TCP đi qua link
  có ρ > 1 bị gắn cờ 'outside_validity': con số của nó KHÔNG được tin.

CÁCH CHẠY (không cần Mininet, không cần Ditto):
    python3 -m whatif.model demo      # ví dụ flood h1 với 3 lựa chọn (bài 6.1)
"""
from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from mininet.gen_routes import next_hop_table
from mininet.topology_meta import baseline_bw, canonical

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / 'ditto/topology_spec.json'
EPS = 1e-9
MAX_ITER = 100
KINDS = ('udp', 'tcp')


@dataclass(frozen=True)
class Demand:
    src: str
    dst: str
    mbps: float
    kind: str = 'udp'          # 'udp' không đàn hồi | 'tcp' đàn hồi (chỉ đúng khi không nghẽn)

    @property
    def name(self) -> str:
        return '%s->%s/%s' % (self.src, self.dst, self.kind)


# Tải bình thường của testbed (mininet/traffic.py): client thứ i gửi tới servers[i % 2],
# TCP 2 Mbps; thêm luồng nền UDP 2 Mbps srv1 -> srv2 (start_server_to_server).
# Đây là tốc độ DANH NGHĨA của iperf; bộ đếm trên link thấy nhiều hơn ~7% vì header.
NORMAL_DEMANDS = (
    Demand('h1', 'srv1', 2.0, 'tcp'),
    Demand('h2', 'srv2', 2.0, 'tcp'),
    Demand('h3', 'srv1', 2.0, 'tcp'),
    Demand('srv1', 'srv2', 2.0, 'udp'),
)


@dataclass
class State:
    spec: dict
    capacity: dict                       # {link_key: Mbps}, ví dụ {'s1-s2': 20.0}
    down: set = field(default_factory=set)
    demands: list = field(default_factory=list)


def load_spec(path=SPEC_PATH) -> dict:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def default_state(spec=None, demands=NORMAL_DEMANDS) -> State:
    spec = spec or load_spec()
    return State(spec=spec, capacity=baseline_bw(spec), down=set(), demands=list(demands))


def link_key(text: str, state: State) -> str:
    """'s2-s1' hay 's1-s2' đều thành khóa chuẩn 's1-s2'; link lạ -> lỗi."""
    parts = str(text).split('-')
    if len(parts) != 2:
        raise ValueError('tên link không hợp lệ: %r' % text)
    key = canonical(*parts)
    if key not in state.capacity:
        raise ValueError('không có link %r trong topology' % text)
    return key


# ===========================================================================
# HÀNH ĐỘNG: mỗi hành động là một dict để CLI/dashboard truyền dạng JSON được
#   {'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}
#   {'op': 'disableLink',  'link': 's1-s2'}
#   {'op': 'enableLink',   'link': 's1-s2'}
#   {'op': 'addDemand',    'src': 'h1', 'dst': 'srv1', 'mbps': 50, 'kind': 'udp'}
# ===========================================================================
def apply(state: State, action: dict) -> State:
    """Trả về State MỚI; không sửa state cũ."""
    new = State(spec=state.spec, capacity=dict(state.capacity), down=set(state.down),
                demands=list(state.demands))
    op = action.get('op')
    if op == 'setBandwidth':
        mbps = float(action['mbps'])
        if not mbps > 0:
            raise ValueError('băng thông phải > 0: %r' % action)
        new.capacity[link_key(action['link'], state)] = mbps
    elif op == 'disableLink':
        new.down.add(link_key(action['link'], state))
    elif op == 'enableLink':
        new.down.discard(link_key(action['link'], state))
    elif op == 'addDemand':
        d = Demand(action['src'], action['dst'], float(action['mbps']),
                   action.get('kind', 'udp'))
        hosts = {h['name'] for h in state.spec['hosts']}
        if d.src not in hosts or d.dst not in hosts or d.src == d.dst:
            raise ValueError('nguồn/đích không hợp lệ: %r' % action)
        if d.kind not in KINDS or not d.mbps > 0:
            raise ValueError('kind phải là udp/tcp và Mbps > 0: %r' % action)
        if any(x.name == d.name for x in new.demands):
            raise ValueError('đã có luồng %s' % d.name)
        new.demands.append(d)
    else:
        raise ValueError('hành động không biết: %r' % action)
    return new


def apply_all(state: State, actions) -> State:
    for action in actions:
        state = apply(state, action)
    return state


# ===========================================================================
# ĐỊNH TUYẾN: đi theo bảng next-hop mà Ryu sẽ cài với tập link đang tắt
# ===========================================================================
def _table(state: State) -> dict:
    excluded = [tuple(k.split('-')) for k in state.down]
    return next_hop_table(state.spec, excluded_edges=excluded)


def route(state: State, src: str, dst: str, table=None):
    """Danh sách chặng có hướng [(a, b), ...] từ src tới dst; None nếu không tới được."""
    table = table if table is not None else _table(state)
    ips = {h['name']: h['ip'] for h in state.spec['hosts']}
    switches = set(table)
    # chặng đầu: host -> switch nó gắn vào (nếu link truy nhập đang tắt thì hết đường)
    first = None
    for a, b in state.spec['links']:
        if src in (a, b) and ({a, b} - {src}) & switches:
            first = (src, b if a == src else a)
            break
    if first is None or canonical(*first) in state.down:
        return None
    hops, node = [first], first[1]
    while node != dst:
        nxt = table.get(node, {}).get(ips[dst])
        if nxt is None or len(hops) > len(state.capacity):
            return None
        hops.append((node, nxt))
        node = nxt
    return hops


# ===========================================================================
# DỰ ĐOÁN
# ===========================================================================
def _dlink(hop) -> str:
    return '%s->%s' % hop


def predict(state: State) -> dict:
    names = [d.name for d in state.demands]
    if len(set(names)) != len(names):
        raise ValueError('luồng trùng tên: %s' % names)
    table = _table(state)
    paths = {d.name: route(state, d.src, d.dst, table) for d in state.demands}
    live = [d for d in state.demands if paths[d.name]]
    cap = {hop: state.capacity[canonical(*hop)]
           for d in live for hop in paths[d.name]}

    # arrive[name][i] = tốc độ của luồng khi ĐẾN chặng thứ i
    arrive = {d.name: [d.mbps] * len(paths[d.name]) for d in live}
    for _ in range(MAX_ITER):
        load = defaultdict(float)
        for d in live:
            for hop, rate in zip(paths[d.name], arrive[d.name]):
                load[hop] += rate
        keep = {hop: (min(1.0, cap[hop] / load[hop]) if load[hop] > EPS else 1.0)
                for hop in load}
        new, delta = {}, 0.0
        for d in live:
            rate, rates = d.mbps, []
            for hop in paths[d.name]:
                rates.append(rate)
                rate *= keep[hop]
            new[d.name] = rates
            delta = max([delta] + [abs(x - y) for x, y in zip(rates, arrive[d.name])])
        arrive = new
        if delta < 1e-12:
            break
    else:
        raise RuntimeError('mô hình không hội tụ sau %d vòng' % MAX_ITER)

    load = defaultdict(float)
    users = defaultdict(list)
    for d in live:
        for hop, rate in zip(paths[d.name], arrive[d.name]):
            load[hop] += rate
            users[hop].append(d.name)

    links = {}
    for key, c in sorted(state.capacity.items()):
        if key in state.down:
            continue
        a, b = key.split('-')
        for hop in ((a, b), (b, a)):
            lam = load.get(hop, 0.0)
            rho = lam / c
            links[_dlink(hop)] = {'link': key, 'capacity': c, 'load': lam, 'rho': rho,
                                  'loss': max(0.0, 1.0 - 1.0 / rho) if rho > 1 + EPS else 0.0,
                                  'flows': sorted(users.get(hop, []))}

    flows = {}
    for d in state.demands:
        path = paths[d.name]
        if not path:
            flows[d.name] = {'offered': d.mbps, 'delivered': 0.0, 'loss': 1.0, 'path': None,
                             'reachable': False, 'bottleneck': None,
                             'outside_validity': False}
            continue
        last = path[-1]                  # tốc độ ra khỏi chặng cuối = tốc độ tới đích
        delivered = arrive[d.name][-1] * min(1.0, cap[last] / load[last])
        rhos = [links[_dlink(h)]['rho'] for h in path]
        hot = max(range(len(path)), key=lambda i: rhos[i])
        flows[d.name] = {
            'offered': d.mbps, 'delivered': delivered,
            'loss': 1.0 - delivered / d.mbps,
            'path': [_dlink(h) for h in path], 'reachable': True,
            'bottleneck': _dlink(path[hot]) if rhos[hot] > 1 + EPS else None,
            'outside_validity': d.kind == 'tcp' and max(rhos) > 1 + EPS,
        }

    hottest = max(links, key=lambda k: links[k]['rho']) if links else None
    offered = sum(d.mbps for d in state.demands)
    delivered = sum(f['delivered'] for f in flows.values())
    return {
        'links': links,
        'flows': flows,
        'summary': {
            'max_rho': links[hottest]['rho'] if hottest else 0.0,
            'hottest': hottest,
            'offered_mbps': offered,
            'delivered_mbps': delivered,
            'lost_mbps': offered - delivered,
            'unreachable': sorted(n for n, f in flows.items() if not f['reachable']),
            'outside_validity': sorted(n for n, f in flows.items() if f['outside_validity']),
        },
        'down': sorted(state.down),
    }


# ===========================================================================
# SO SÁNH nhiều lựa chọn với "không làm gì"
# ===========================================================================
def compare(state: State, options: dict) -> dict:
    """options = {'tên lựa chọn': [hành động, ...]}; luôn kèm 'không làm gì'."""
    base = predict(state)
    out = {}
    for label, actions in {'không làm gì': [], **options}.items():
        pred = predict(apply_all(state, actions))
        delta = {n: pred['flows'][n]['delivered'] - base['flows'][n]['delivered']
                 for n in base['flows'] if n in pred['flows']}
        out[label] = {'actions': actions, 'prediction': pred,
                      'delta_delivered_vs_nothing': delta,
                      'new_victims': sorted(n for n, v in delta.items() if v < -0.05)}
    return out


# ===========================================================================
# DEMO: bảng của bài 6.1, nay do máy tính
# ===========================================================================
DEMO_FLOOD = {'op': 'addDemand', 'src': 'h1', 'dst': 'srv1', 'mbps': 50, 'kind': 'udp'}
DEMO_OPTIONS = {
    'setBandwidth h1-s1 = 7': [{'op': 'setBandwidth', 'link': 'h1-s1', 'mbps': 7}],
    'disableLink s1-s2': [{'op': 'disableLink', 'link': 's1-s2'}],
}


def normal_loss(pred: dict, exclude=()) -> float:
    """Mbps mà các luồng THƯỜNG mất (bỏ luồng gây sự cố, vì nó tự mất ở link của nó)."""
    return sum(f['offered'] - f['delivered'] for n, f in pred['flows'].items()
               if n not in exclude)


def print_compare(result: dict, exclude=()) -> None:
    print('%-24s %-34s %-8s %-8s %-10s %s' % (
        'lựa chọn', 'link nóng (ρ ≥ 0.9)', 'h2 nhận', 'h3 nhận', 'thường mất',
        'ngoài vùng hợp lệ'))
    for label, r in result.items():
        p = r['prediction']
        hot = sorted(((k, v['rho']) for k, v in p['links'].items() if v['rho'] >= 0.9),
                     key=lambda kv: -kv[1])
        hot_txt = ' '.join('%s=%.2f' % kv for kv in hot[:3]) or '-'
        f = p['flows']
        print('%-24s %-34s %-8.2f %-8.2f %-10.2f %s' % (
            label, hot_txt, f['h2->srv2/tcp']['delivered'], f['h3->srv1/tcp']['delivered'],
            normal_loss(p, exclude), ', '.join(p['summary']['outside_validity']) or '-'))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ['demo']:
        print(__doc__)
        return 2
    state = apply(default_state(), DEMO_FLOOD)
    print('Kịch bản: tải bình thường + h1 flood UDP 50 Mbps tới srv1\n')
    print_compare(compare(state, copy.deepcopy(DEMO_OPTIONS)), exclude=('h1->srv1/udp',))
    print('\n"thường mất" = Mbps các luồng thường mất (không tính luồng flood).')
    print('Số của luồng TCP có tên trong cột cuối KHÔNG đáng tin (TCP lùi khi nghẽn).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
