"""Lesson 5.5 — ghim quy ước nhãn. Khong can du lieu, khong can Mininet."""
import pytest

from ml import campaign as C
from ml import labels as L

EV = [{'kind': 'inject', 'tick': 20}, {'kind': 'revert', 'tick': 40}]


# --- 1. CONG THUC y: ghim doi 1 tick la fail ------------------------------
def test_y_formula_is_exclusive_at_inject_inclusive_at_revert():
    """Neu ai doi thanh <= inject hoac < revert, test nay fail NGAY.

    Day la test quan trong nhat file: no ghim NGU NGHIA CUA SO DO.
    rate[t] do khoang (t-1, t], va inject chay SAU khi snapshot tick 20 da
    flush -> tick 20 sach, tick 21 la tick fault dau tien.
    """
    y = L.labels_from_events(60, EV)
    assert len(y) == 60
    assert sum(y) == 20
    assert y[19] == 0 and y[20] == 0      # tick 20 do khoang TRUOC inject
    assert y[21] == 1                     # tick fault dau tien
    assert y[40] == 1                     # khoang (39,40] van duoi fault
    assert y[41] == 0                     # da revert


def test_normal_run_has_no_positive_label():
    assert L.labels_from_events(60, []) == [0] * 60
    assert L.labels_from_events(60, None) == [0] * 60


# --- 2. y KHONG duoc chua grace ------------------------------------------
def test_grace_is_not_baked_into_labels():
    """Grace la quy uoc DANH GIA, khong phai su that vat ly.

    Nhoi grace vao y = noi "loi khong ton tai o tick 21", trong khi su that
    la "loi ton tai nhung chua do duoc hau qua". Do dung la kieu nham lan ma
    ca Phase 5 sinh ra de chong.
    """
    y = L.labels_from_events(60, EV)
    assert y[21] == 1 and y[22] == 1      # trong dai onset nhung VAN la fault


# --- 3. MAT NA: doi xung, va dung cho HAI chi so khac nhau ---------------
def test_transition_mask_is_symmetric_and_excludes_both_edges():
    m = L.transition_mask(60, EV, onset=2, recovery=2)
    assert m[21] == L.IGNORE and m[22] == L.IGNORE   # onset
    assert m[23] == L.EVAL                            # het onset
    assert m[41] == L.IGNORE and m[42] == L.IGNORE   # recovery
    assert m[43] == L.EVAL
    assert m[20] == L.EVAL                            # tick truoc inject: giu


def test_primary_mask_only_drops_warmup():
    """Chi so CHINH khong loai tick chuyen tiep — day la diem chong bi che
    'chon quy uoc co loi'."""
    tb = L.label_table('F-x', 60, EV, warmup_ticks=1)
    assert tb['eval_primary'][0] == L.IGNORE          # warmup
    assert tb['eval_primary'][21] == L.EVAL           # chuyen tiep VAN tinh
    assert tb['eval_sensitivity'][21] == L.IGNORE     # chi so phu thi loai
    assert tb['counts']['ticks_dropped_warmup'] == 1
    assert tb['counts']['ticks_dropped_transition'] == 12


def test_normal_run_transition_mask_is_all_eval():
    assert L.transition_mask(60, []) == [L.EVAL] * 60


# --- 4. SU KIEN HONG phai NO, khong duoc tra "tam duoc" ------------------
@pytest.mark.parametrize('events', [
    [{'kind': 'inject', 'tick': 20}],                              # thieu revert
    [{'kind': 'revert', 'tick': 40}, {'kind': 'inject', 'tick': 20}],  # sai thu tu
    [{'kind': 'inject', 'tick': 40}, {'kind': 'revert', 'tick': 20}],  # nguoc
    [{'kind': 'inject', 'tick': 20}, {'kind': 'revert', 'tick': 80}],  # ngoai day
    [{'kind': 'inject', 'tick': True}, {'kind': 'revert', 'tick': 40}],  # bool!
    [{'kind': 'inject', 'tick': 20.0}, {'kind': 'revert', 'tick': 40}],  # float
])
def test_broken_events_raise(events):
    with pytest.raises(ValueError):
        L.labels_from_events(60, events)


# --- 5. BASE RATE: tai hien con so 5.4, va tach theo loai fault ----------
def test_base_rate_reproduces_lesson_54_number():
    """18 run: 8 train N + 2 test C (khong fault) + 8 test F.
    Manifest 5.4 noi 160/590 = 0.2712. Cong thuc phai tai hien CHINH XAC.
    Lech -> hoac toi vua doi cong thuc nhan, hoac du lieu doi. Ca hai deu
    phai biet NGAY."""
    tables = (
        [L.label_table('N-%d' % i, 60, [], 1, split='train', group='N')
         for i in range(8)]
        + [L.label_table('C-%d' % i, 60, [], 1, split='test', group='C')
           for i in range(2)]
        + [L.label_table('F-%d' % i, 60, EV, 1, split='test', group='F',
                         fault='admin_down')
           for i in range(8)])
    br = L.base_rate(tables, 'eval_primary')
    assert br['usable_test_ticks'] == 590        # 10 run test x 59 tick
    assert br['anomalous_test_ticks'] == 160     # 8 run x 20 tick
    assert br['base_rate_measured'] == 0.2712
    assert br['dumb_always_normal_accuracy'] == 0.7288


def test_base_rate_splits_by_fault_type():
    tables = [L.label_table('F-a', 60, EV, 1, split='test', fault='admin_down'),
              L.label_table('F-d', 60, EV, 1, split='test', fault='degrade')]
    br = L.base_rate(tables, 'eval_primary')
    assert set(br['by_fault']) == {'admin_down', 'degrade'}
    assert br['by_fault']['degrade']['anomalous'] == 20


def test_sensitivity_mask_lowers_base_rate_by_known_amount():
    """Loai 2 tick fault (onset) + 2 tick normal (recovery) moi run fault."""
    tables = [L.label_table('F-%d' % i, 60, EV, 1, split='test', fault='f')
              for i in range(8)]
    p = L.base_rate(tables, 'eval_primary')
    s = L.base_rate(tables, 'eval_sensitivity')
    assert p['anomalous_test_ticks'] - s['anomalous_test_ticks'] == 80
    assert p['usable_test_ticks'] - s['usable_test_ticks'] == 96


# --- 6. GHEP NHAN: theo KHOA, khong theo thu tu dong --------------------
def test_attach_labels_joins_on_keys_not_row_order():
    """Dong bi DAO NGUOC van phai duoc nhan dung. Neu gan theo vi tri,
    test nay fail — va do chinh la loi im lang ma ta dang chan."""
    pd = pytest.importorskip('pandas')
    tb = L.label_table('F-x', 4, [{'kind': 'inject', 'tick': 1},
                                  {'kind': 'revert', 'tick': 2}], 1)
    df = pd.DataFrame({'run_id': ['F-x'] * 4, 'tick': [3, 2, 1, 0],
                       'x': [9, 8, 7, 6]})
    out = L.attach_labels(df, [tb])
    assert out.loc[out.tick == 2, 'is_fault'].iloc[0] == 1
    assert out.loc[out.tick == 1, 'is_fault'].iloc[0] == 0
    assert out.loc[out.tick == 3, 'is_fault'].iloc[0] == 0


def test_attach_labels_raises_on_missing_or_duplicate_keys():
    pd = pytest.importorskip('pandas')
    tb = L.label_table('F-x', 3, [], 0)
    with pytest.raises(ValueError):    # run_id khong co bang nhan
        L.attach_labels(pd.DataFrame({'run_id': ['other'], 'tick': [0]}), [tb])
    with pytest.raises(ValueError):    # (run_id, tick) trung
        L.attach_labels(pd.DataFrame({'run_id': ['F-x'] * 2, 'tick': [0, 0]}), [tb])


# --- 7. PROVENANCE: khong duoc sua chuoi da dong dau vao 18 sidecar -----
def test_collected_convention_string_is_frozen():
    """18 sidecar tren dia dang mang CHINH chuoi nay. Sua no = lam sidecar
    noi khac code = tu pha bang chung Lesson 5.4."""
    assert L.LABEL_CONVENTION_COLLECTED == (
        'point-wise; label[t]=1 iff inject_tick < t <= revert_tick; grace=2 ticks')
    assert C.LABEL_CONVENTION == L.LABEL_CONVENTION_COLLECTED


def test_campaign_reexports_the_same_single_definition():
    """Mot khai niem -> mot cho dinh nghia. Neu campaign co ban sao rieng,
    hai ban se troi lech nhau va khong ai biet ben nao dung."""
    assert C.labels_from_events is L.labels_from_events
    assert C.GRACE_TICKS == 2  # Frozen collection gate; evaluation grace is separate.

@pytest.mark.parametrize('n', [-1, True, 2.0])
def test_invalid_snapshot_counts_rejected_before_allocation(n):
    for fn in (lambda: L.labels_from_events(n, []), lambda: L.warmup_mask(n, 0), lambda: L.transition_mask(n, [])):
        with pytest.raises(ValueError):
            fn()


def test_malformed_table_cannot_silently_truncate_labels():
    tb = L.label_table('x', 3, [], 0, split='test')
    tb['y'].pop()
    with pytest.raises(ValueError):
        L.base_rate([tb])


def test_attach_rejects_existing_labels_and_float_tick_keys():
    pd = pytest.importorskip('pandas')
    tb = L.label_table('x', 3, [], 0)
    for df in (pd.DataFrame({'run_id':['x'], 'tick':[1.0]}), pd.DataFrame({'run_id':['x'], 'tick':[1], 'is_fault':[0]})):
        with pytest.raises(ValueError):
            L.attach_labels(df, [tb])


def test_nonrecovering_witness_has_no_recovery_delay():
    from scripts.verify_labels import onset_recovery_delay
    assert onset_recovery_delay([0, 0, 8, 8, 8, None], 1, 3) == (0, None)


def test_live_artifact_regenerates_bit_for_bit_and_detects_changed_event(tmp_path):
    import json
    from scripts.verify_labels import build_ground_truth
    if not (C.ROOT/'data/phase5/raw/N-load1M-s1001-r1.jsonl').exists():
        pytest.skip('Ignored raw archive must be restored for live reproducibility check')
    artifact = build_ground_truth(C.ROOT)
    target = tmp_path/'ground_truth.json'
    C.atomic_json(target, artifact)
    assert target.read_bytes() == (C.ROOT/'results/report/ground_truth.json').read_bytes()
    contract = C.load_contract()
    fault = next(r for r in contract['runs'] if r.get('fault'))
    side = json.loads(C.run_paths(fault['run_id'])['meta'].read_text())
    events = [dict(e) for e in side['events']]
    events[0]['tick'] += 1
    assert L.labels_from_events(60, events) != L.labels_from_events(60, side['events'])
    assert C.sha256_bytes(C.canonical_json(events).encode()) != artifact['receipt']['source_fingerprints']['runs'][fault['run_id']]['events_sha256']
