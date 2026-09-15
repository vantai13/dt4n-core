import copy
import json
import math
import sys
from pathlib import Path

import pytest
from ml import campaign as C
from ml.flatten import load_jsonl, flatten_snapshot
from ml.schema import column_kind


def frame(record, constants, fault=False):
    rows=[]
    for tick in range(60):
        things={}
        for tid in C.CORE_LINK_IDS:
            active=fault and 21 <= tick <= 40
            things[tid]={'features':{'status':{'state':'down' if active else 'up'},
                'traffic':{'rateValid':tick>0,'qdiscValid':tick>0,
                           'rxRate':100000 if active else 1000,'txRate':100000 if active else 1000,
                           'lossPct':50 if active else 0}}}
        rows.append({'tick':tick,'t_rel':tick+.05,'run':{'run_id':record['run_id'],
                     'collector_version':constants['collector_version']},'things':things})
    return rows


@pytest.fixture
def contract():
    return C.load_contract()


def test_integrity_checks_actual_json_content(contract):
    assert C.check_contract_integrity(contract)['match']
    bad=copy.deepcopy(contract)
    bad['runs'][-1]['fault_parameters']['factor']+=.001
    with pytest.raises(RuntimeError):
        C.check_contract_integrity(bad)


def test_contract_hash_ignores_presentation(contract):
    assert C.contract_hash(json.loads(json.dumps(contract,indent=4)))==contract['design_content_sha256']


@pytest.mark.parametrize('run_index',range(18))
def test_traffic_plan_runs_longer_than_recording(contract,run_index):
    p=C.traffic_plan(contract['runs'][run_index],contract['constants'])
    assert p['iperf_seconds']==75


def test_preroll_nominal_schedule_covers_end():
    from mininet.traffic import schedule_segments,schedule_with_preroll
    from ml.design import SCHEDULE_A
    segments=schedule_segments(schedule_with_preroll(SCHEDULE_A,5),75)
    assert sum(d for _,d in segments)==75
    assert segments[:2]==((1.,5),(1.,10))
    assert segments[-1]==(4.,20)  # t_rel=50..70, not 50..75


def test_runner_scenario_does_not_import_numpy(contract,monkeypatch):
    import builtins
    original=builtins.__import__
    def guarded(name,*args,**kwargs):
        if name.split('.')[0] in ('numpy','pandas'):
            pytest.fail('runner dependency on '+name)
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',guarded)
    for r in contract['runs']:
        scenario=C.scenario_from_record(r)
        assert (scenario is None)==(r['fault'] is None)


def test_missing_flag_is_counted_as_invalid():
    frac,total,invalid=C._invalid_fraction([{'things':{}}],'rateValid')
    assert (frac,total,invalid)==(1.,8,8)


def test_nonfinite_probe_is_excluded():
    snap={'things':{'link-h1-s1':{'features':{'traffic':{'rateValid':True,'rxRate':math.inf}}}}}
    assert C._probe_series([snap],'link-h1-s1')['rxRate']==[]


def test_separation_has_physical_floor():
    assert C.separation([100]*5,[101]*5,100)==.01
    assert C.separation([0]*5,[100]*5,10)==10


@pytest.mark.parametrize('broken', ['flag','timestamp','tick','version','missing_link'])
def test_verify_rejects_broken_baseline(contract,broken):
    record=next(r for r in contract['runs'] if r['group']=='N')
    rows=frame(record,contract['constants'])
    for i in range(1,60):
        if broken=='flag':rows[i]['things']['link-h1-s1']['features']['traffic'].pop('rateValid')
        if broken=='timestamp':rows[i]['t_rel']=math.nan
        if broken=='tick':rows[i]['tick']=i+1
        if broken=='version':rows[i]['run']['collector_version']='v1'
        if broken=='missing_link':rows[i]['things'].pop('link-h1-s1')
    assert C.verify_run(record,contract['constants'],rows,[])['passed'] is False


def test_after_write_event_windows_and_fault_missing_are_not_quality_gates(contract):
    record=next(r for r in contract['runs'] if r['fault']=='admin_down')
    rows=frame(record,contract['constants'],fault=True)
    for i in range(21,41):
        for t in rows[i]['things'].values():t['features']['traffic']['qdiscValid']=False
    events=[{'kind':'inject','tick':20,'t_rel':20.1},{'kind':'revert','tick':40,'t_rel':40.1}]
    report=C.verify_run(record,contract['constants'],rows,events)
    assert report['passed'] and report['admin_down_observed']
    assert report['qdisc_invalid_fraction_fault']==1.
    assert report['qdisc_invalid_fraction_baseline']==0.


def test_duplicate_events_do_not_pass(contract):
    record=next(r for r in contract['runs'] if r['fault'])
    rows=frame(record,contract['constants'],fault=True)
    ev=[{'kind':'inject','tick':20,'t_rel':20.1},{'kind':'revert','tick':40,'t_rel':40.1}]
    assert not C.verify_run(record,contract['constants'],rows,ev+[ev[0]])['passed']


def test_embedded_run_metadata_is_never_a_feature():
    metadata={'run_id':'r','split':'test','fault':'degrade','fault_target':'s1-s2',
              't_inject':20,'t_revert':40,'git_dirty':False,'exec_index':1}
    row=flatten_snapshot({'run':metadata,'tick':0,'t_rel':.05})
    assert all(column_kind(k)=='meta' for k in metadata)
    assert row['split']=='test'


def test_cut_file_tick_invariant_fails(tmp_path):
    p=tmp_path/'cut.jsonl';p.write_text(json.dumps({'tick':5,'things':{}})+'\n')
    with pytest.raises(ValueError):load_jsonl(p)


def test_collector_hook_runs_after_write_and_preserves_default(tmp_path,monkeypatch):
    from bridge import collector
    col=collector.Collector(None,interval=.01,log_path=str(tmp_path/'raw.jsonl'),
        pretty_log_path=None,run_meta={'run_id':'r'})
    monkeypatch.setattr(col,'collect_all',lambda:{'things':{}})
    def hook(tick,snap,t_rel):
        data=[json.loads(l) for l in Path(col.log_path).read_text().splitlines()]
        assert data[-1]['tick']==tick and data[-1]['run']['run_id']=='r'
        assert t_rel>=0
    assert col.run(duration=.035,on_tick=hook)>=1


def test_measured_base_rate_counts_post_callback_ticks(contract):
    record=next(r for r in contract['runs'] if r['fault'])
    result=C.measured_base_rate(contract,{record['run_id']:{'status':'ok',
        'checks':{'passed':True,'n_snapshots':60},'events':[
        {'kind':'inject','tick':20},{'kind':'revert','tick':40}]}})
    assert result['usable_test_ticks']==59 and result['anomalous_test_ticks']==20
