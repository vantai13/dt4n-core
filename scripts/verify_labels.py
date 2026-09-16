#!/usr/bin/env python3
"""Lesson 5.5 — KIỂM CHỨNG nhãn ground truth, và ĐO độ trễ khởi phát.

Usage: python -m scripts.verify_labels [--root .]

BA CÂU HỎI FILE NÀY TRẢ LỜI BẰNG SỐ:

  1. Nhãn có KHỚP THỜI GIAN với dữ liệu không?
     Không kiểm bằng "sai số nhỏ". Kiểm bằng ĐẲNG THỨC: event t_rel trong
     sidecar phải BẰNG CHÍNH XÁC snapshot[tick].t_rel, vì cả hai là
     round(t_rel, 6) của cùng một biến trong vòng lặp collector. Nếu đẳng
     thức này vỡ, kiến trúc một-gốc-đồng-hồ đã bị phá ở đâu đó.

  2. Tín hiệu có THẬT SỰ xuất hiện trong vùng nhãn không?
     Với mỗi run fault, chọn feature chứng nhân (witness) = cặp (link, thuộc
     tính) tách biệt nhất, rồi tìm tick ĐẦU TIÊN vượt ngưỡng z. So với
     inject_tick+1 -> onset delay ĐO ĐƯỢC.
     Đây là phép kiểm mà `inject_on_time` KHÔNG làm: inject_on_time nói
     "lệnh của tôi chạy đúng giờ", còn cái này nói "mạng thật sự đổi trạng
     thái đúng lúc nhãn nói có".

  3. grace=2 có ĐỦ không?
     Nếu mọi run có onset delay <= 2 -> con số 2 được dữ liệu biện minh.
     Nếu có run 4 -> con số 2 SAI, gate fail, và bạn vừa phát hiện một điều
     thật về hệ của mình. Cả hai kết quả đều tốt. Chỉ "giả định mà không đo"
     là không tốt.

DÙNG LẠI, KHÔNG VIẾT LẠI: SEPARATION_FLOOR và _probe_series lấy từ
ml/campaign.py — cùng định nghĩa "mẫu hợp lệ" với gate chấp nhận ở 5.4. Viết
lại = có hai định nghĩa, và số ở hai lesson sẽ lệch nhau không hiểu vì sao.
"""
import argparse
import json
import math
import statistics
from pathlib import Path

from ml import campaign as C
from ml import labels as L

# Diagnostic threshold only: short correlated baseline and scale floors do not
# justify a Gaussian 5-sigma significance interpretation. Never tuned down to pass.
Z_ONSET = 5.0


def _probe_tick(snapshot, link_id):
    """Giá trị 4 kênh tại MỘT tick. None = không đo được (KHÔNG phải 0)."""
    series = C._probe_series([snapshot], link_id)
    return {k: (v[0] if v else None) for k, v in series.items()}


def channel_scan(snapshots, expected_links, warmup, inject, revert):
    """Scan all eligible channels: strongest illustrates; earliest diagnoses onset.

    A first crossing is not a causal physical latency bound or a guarantee
    that a detector will flag the point. Keep both measurements and channels.
    """
    witness = None
    per_channel = []
    for link_id in ('link-%s' % x for x in expected_links):
        per_tick = [_probe_tick(s, link_id) for s in snapshots]
        for channel, floor in C.SEPARATION_FLOOR.items():
            values = [row[channel] for row in per_tick]
            baseline = [v for v in values[warmup:inject + 1]
                        if v is not None and math.isfinite(v)]
            if len(baseline) < 3:
                continue
            mu = statistics.fmean(baseline)
            sigma = statistics.pstdev(baseline)
            scale = max(sigma, floor)
            z = [None if v is None or not math.isfinite(v)
                 else abs(v - mu) / scale for v in values]
            during = [x for x in z[inject + 1:revert + 1] if x is not None]
            if not during:
                continue
            onset, recovery = onset_recovery_delay(z, inject, revert)
            entry = {
                'link': link_id, 'channel': channel,
                'baseline_mean': round(mu, 4), 'baseline_std': round(sigma, 6),
                'scale_used': round(scale, 6),
                'mean_z_in_window': round(statistics.fmean(during), 3),
                'max_z_in_window': round(max(during), 3),
                'onset_delay_ticks': onset, 'recovery_delay_ticks': recovery,
            }
            per_channel.append(entry)
            if witness is None or entry['mean_z_in_window'] > witness['mean_z_in_window']:
                witness = dict(entry, values=values, z=z)
    if witness is None:
        return None
    # SỚM NHẤT: min trên các kênh CÓ vượt ngưỡng. None = không kênh nào vượt.
    crossed = [c for c in per_channel if c['onset_delay_ticks'] is not None]
    earliest = min(crossed, key=lambda c: c['onset_delay_ticks']) if crossed else None
    return {'witness': witness, 'earliest': earliest, 'per_channel': per_channel}

def onset_recovery_delay(z, inject, revert):
    """onset = trễ tới lúc tín hiệu XUẤT HIỆN; recovery = tới lúc nó TẮT.

    Mốc 0 của onset là inject_tick+1, tức tick ĐẦU TIÊN mà nhãn nói fault.
    onset_delay = 0 nghĩa là tín hiệu lộ ra ngay tick đầu — không có trễ vật
    lý. onset_delay = 3 nghĩa là 3 tick đầu của vùng nhãn KHÔNG có dấu vết
    đo được, và grace=2 không đủ để che chúng.
    """
    onset = None
    for t in range(inject + 1, revert + 1):
        if z[t] is not None and z[t] >= Z_ONSET:
            onset = t - (inject + 1)
            break
    recovery = None
    for t in range(revert + 1, len(z)):
        if z[t] is not None and z[t] < Z_ONSET:
            recovery = t - (revert + 1)
            break
    return onset, recovery


def build_ground_truth(root: Path):
    contract = C.load_contract(root / 'results/report/experiment_matrix.json')
    integrity = C.check_contract_integrity(contract)
    manifest = json.loads((root / 'results/report/ml_dataset_manifest.json').read_text())
    if not manifest['complete']:
        raise ValueError('can chien dich hoan tat truoc khi kiem chung nhan')
    sources = {'manifest_sha256': C.sha256_file(root / 'results/report/ml_dataset_manifest.json'), 'runs': {}}
    warmup = int(contract['constants']['warmup_ticks'])

    tables, alignment, timing = [], {}, {}
    for record in contract['runs']:
        rid = record['run_id']
        paths = C.run_paths(rid, root)
        side = json.loads(paths['meta'].read_text())

        # --- hàng rào provenance: y phải sinh từ ĐÚNG dữ liệu đã nghiệm thu --
        if side['design_content_sha256'] != integrity['stored']:
            raise ValueError('sidecar lech design SHA: ' + rid)
        if C.sha256_file(paths['final']) != side['sha256']:
            raise ValueError('raw lech sha256 sidecar: ' + rid)
        if manifest['runs'][rid]['sha256'] != side['sha256']:
            raise ValueError('manifest lech sha256 sidecar: ' + rid)

        if side['record'] != record or side['constants'] != contract['constants'] or not side['checks']['passed']:
            raise ValueError('sidecar record/constants/checks mismatch: ' + rid)
        if side['label_convention'] != L.LABEL_CONVENTION_COLLECTED or side['collection_provenance']['source_dirty']:
            raise ValueError('collection convention/source mismatch: ' + rid)
        sources['runs'][rid] = {'raw_sha256': side['sha256'], 'metadata_sha256': C.sha256_file(paths['meta']), 'events_sha256': C.sha256_bytes(C.canonical_json(side['events']).encode())}
        snapshots = C.read_snapshots(paths['final'])
        events = side['events']
        n = len(snapshots)
        L.event_ticks(n, events)
        if bool(events) != bool(record.get('fault')):
            raise ValueError('events disagree with fault record: ' + rid)
        if [x.get('tick') for x in snapshots] != list(range(n)) or any((x.get('run', {}).get('run_id') != rid or x['run'].get('design_content_sha256') != integrity['stored'] or x['run'].get('git_hash') != side['collection_provenance']['git_hash'] or x['run'].get('source_dirty') is not False) for x in snapshots):
            raise ValueError('raw tick/run identity mismatch: ' + rid)
        times = [x.get('t_rel') for x in snapshots]
        if any(not isinstance(t, (int, float)) or not math.isfinite(t) for t in times) or any(a >= b for a,b in zip(times,times[1:])):
            raise ValueError('invalid monotonic timeline: ' + rid)

        # --- GATE 1: số nhãn == số snapshot ---------------------------------
        y = L.labels_from_events(n, events)
        if len(y) != n:
            raise ValueError('so nhan != so snapshot: ' + rid)

        # --- GATE 2: CHỨNG MINH khớp đồng hồ (đẳng thức, không phải sai số) --
        # event t_rel LÀ round(t_rel,6) của chính biến mà collector đã ghi vào
        # snapshot cùng tick. Nếu không bằng nhau chính xác, kiến trúc
        # một-gốc-đồng-hồ đã bị phá.
        clock = []
        for ev in events:
            tick = ev['tick']
            snap_t = snapshots[tick].get('t_rel')
            clock.append({'kind': ev['kind'], 'tick': tick,
                          'event_t_rel': ev['t_rel'], 'snapshot_t_rel': snap_t,
                          'identical': snap_t == ev['t_rel']})
        if not all(c['identical'] for c in clock):
            raise ValueError('event t_rel KHONG bang snapshot t_rel -> '
                             'da co hai goc dong ho: ' + rid)
        alignment[rid] = clock

        # --- GATE 3: ĐO onset / recovery delay trên run fault ---------------
        if record.get('fault'):
            inject, revert = L.event_ticks(n, events)
            scan = channel_scan(snapshots, record['expected_links'],
                                warmup, inject, revert)
            if scan is None:
                raise ValueError('khong chon duoc kenh chung nhan: ' + rid)
            w, e = scan['witness'], scan['earliest']
            timing[rid] = {
                # --- minh hoạ: kênh mạnh nhất (giữ nguyên nghĩa bản cũ) ----
                'witness': '%s.%s' % (w['link'], w['channel']),
                'witness_onset_delay_ticks': w['onset_delay_ticks'],
                'witness_recovery_delay_ticks': w['recovery_delay_ticks'],
                'mean_z_in_fault_window': w['mean_z_in_window'],
                'baseline_mean': w['baseline_mean'],
                'baseline_std': w['baseline_std'],
                'scale_used': w['scale_used'],
                # --- BIỆN MINH GRACE: kênh sớm nhất ------------------------
                'earliest_channel': (None if e is None else
                                     '%s.%s' % (e['link'], e['channel'])),
                'onset_delay_ticks': None if e is None else e['onset_delay_ticks'],
                'recovery_delay_ticks': w['recovery_delay_ticks'],
                'earliest_mean_z': None if e is None else e['mean_z_in_window'],
                # --- bằng chứng đầy đủ để bảo vệ trước hội đồng ------------
                'per_channel': scan['per_channel'],
                'z_threshold': Z_ONSET,
                'inject_tick': inject, 'revert_tick': revert,
                'z_series': [None if v is None else round(v, 3) for v in w['z']],
                'witness_values': [None if v is None or not math.isfinite(v)
                                   else round(v, 4) for v in w['values']],
            }

        tables.append(L.label_table(
            run_id=rid, n_snapshots=n, events=events, warmup_ticks=warmup,
            split=record['split'], group=record['group'],
            fault=record.get('fault'), fault_target=record.get('fault_target'),
            seed=record.get('seed'),
            max_separation=side['checks'].get('max_separation')))

    # --- base rate: hai mặt nạ, và theo từng loại fault ---------------------
    br_primary = L.base_rate(tables, 'eval_primary')
    br_sensitivity = L.base_rate(tables, 'eval_sensitivity')

    # --- GATE 4: HỒI QUY. base rate mới PHẢI trùng manifest Lesson 5.4 ------
    # Nếu lệch: hoặc tôi vừa đổi công thức nhãn (phải biết NGAY), hoặc dữ liệu
    # đã đổi. Cả hai đều là chuyện lớn, không được trôi qua im lặng.
    expected = manifest['base_rate']['base_rate_measured']
    if any(br_primary[k] != manifest['base_rate'][k] for k in ('usable_test_ticks', 'anomalous_test_ticks', 'base_rate_measured')):
        raise ValueError('base rate lech manifest 5.4: %r != %r'
                         % (br_primary['base_rate_measured'], expected))

    faults = [t for t in tables if t['fault']]
    onsets = [timing[t['run_id']]['onset_delay_ticks'] for t in faults]
    recoveries = [timing[t['run_id']]['recovery_delay_ticks'] for t in faults]

    gates = {
        'source_provenance_verified': len(sources['runs']) == len(contract['runs']),
        'labels_length_matches_snapshots': True,   # đã raise nếu sai
        'clock_identity_proven': all(c['identical'] for cl in alignment.values() for c in cl),
        'normal_runs_all_zero': all(sum(t['y']) == 0 for t in tables if not t['fault']),
        'fault_runs_window_exact': all(
            sum(t['y']) == t['revert_tick'] - t['inject_tick'] for t in faults),
        'every_fault_run_has_witness': len(timing) == len(faults),
        'onset_measured_on_every_fault_run': all(o is not None for o in onsets),
        # ĐÂY là gate biện minh cho grace=2. Không đạt -> grace phải đổi.
        'onset_within_declared_grace': all(
            o is not None and o <= L.GRACE_ONSET_TICKS for o in onsets),
        'recovery_within_declared_grace': all(
            r is not None and r <= L.GRACE_RECOVERY_TICKS for r in recoveries),
        'base_rate_matches_manifest': True,        # đã raise nếu sai
        'base_rate_in_10_to_40pct': 0.1 <= br_primary['base_rate_measured'] <= 0.4,
        'test_has_control_runs': sum(
            t['split'] == 'test' and t['group'] == 'C' and not t['fault'] for t in tables) == 2,
        'y_formula_unchanged_since_collection': (
            L.labels_from_events(60, [{'kind': 'inject', 'tick': 20},
                                      {'kind': 'revert', 'tick': 40}])
            == [0] * 21 + [1] * 20 + [0] * 19),
    }

    receipt = {
        'lesson': '5.5-ground-truth',
        'convention_id': L.LABEL_CONVENTION_ID,
        'convention': L.LABEL_CONVENTION,
        'convention_stamped_at_collection': L.LABEL_CONVENTION_COLLECTED,
        'clock_source': ('collector t0_mono (time.monotonic tai luc bat dau ghi); '
                         'event t_rel LA CHINH bien t_rel cua snapshot cung tick, '
                         'duoc dong dau trong on_tick SAU khi snapshot da flush'),
        'design_content_sha256': integrity['stored'],
        'contract_integrity': integrity,
        'source_fingerprints': sources,
        'n_runs': len(tables),
        'base_rate_primary': br_primary,
        'base_rate_sensitivity': br_sensitivity,
        'onset_delay_ticks': {r: timing[r]['onset_delay_ticks'] for r in timing},
        'recovery_delay_ticks': {r: timing[r]['recovery_delay_ticks'] for r in timing},
        'onset_delay_max': max([o for o in onsets if o is not None], default=None),
        'grace_onset_declared': L.GRACE_ONSET_TICKS,
        'grace_recovery_declared': L.GRACE_RECOVERY_TICKS,
        'clock_alignment': alignment,
        'signal_timing': timing,
        'gates': gates,
        'passed': all(gates.values()),
        'interpretation': (
            'Nhan la INTERVENTION LABEL: "toi da gay loi trong khoang nay". '
            'No KHONG bao dam loi gay hau qua do duoc — xem max_separation '
            'tung run de phan tich loi o Phase 6. Base rate ~27% la DO THIET KE; '
            'Precision phu thuoc base rate khi giu TPR/FPR co dinh; domain shift co the doi TPR/FPR. z=5 la nguong chan doan, khong phai kiem dinh 5-sigma.'),
    }

    return {'receipt': receipt, 'tables': tables}


def verify(root: Path):
    artifact = build_ground_truth(root)
    C.atomic_json(root / 'results/report/ground_truth.json', artifact)
    receipt = artifact['receipt']
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('clock_alignment','signal_timing','source_fingerprints')}, ensure_ascii=False, indent=2))
    return 0 if receipt['passed'] else 1

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--root', type=Path, default=C.ROOT)
    return verify(p.parse_args().root.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
