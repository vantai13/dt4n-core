import pytest
from ml import campaign as C
from scripts import generate_ml_dataset as runner


def test_event_labels_after_write():
    labels=C.labels_from_events(60,[{'kind':'inject','tick':20},{'kind':'revert','tick':40}])
    assert sum(labels)==20
    assert labels[20]==0 and labels[21]==1 and labels[40]==1 and labels[41]==0
    assert C.labels_from_events(60,[])==[0]*60


@pytest.mark.parametrize('events',[[{'kind':'inject','tick':20}],[{'kind':'inject','tick':40},{'kind':'revert','tick':20}]])
def test_invalid_events(events):
    with pytest.raises(ValueError): C.labels_from_events(60,events)


def test_resume_preserves_corrupted_raw(tmp_path,monkeypatch):
    record={'run_id':'test-run'};paths=C.run_paths(record['run_id'],tmp_path)
    monkeypatch.setattr(C,'run_paths',lambda rid:paths)
    paths['final'].parent.mkdir(parents=True);paths['final'].write_text('{}\n')
    C.atomic_json(paths['meta'],{'record':record,'design_content_sha256':'abc','sha256':C.sha256_file(paths['final']),'checks':{'passed':True}})
    assert runner.already_done(record,'abc')
    with pytest.raises(RuntimeError):runner.already_done(record,'changed')
    paths['final'].write_text('corrupted')
    with pytest.raises(RuntimeError):runner.already_done(record,'abc')
    assert paths['final'].read_text()=='corrupted'


def test_retry_preserves_failed_attempts(tmp_path):
    paths=C.run_paths('test-run',tmp_path);paths['quarantine'].parent.mkdir(parents=True)
    paths['quarantine'].write_text('failed observations');paths['quarantine_meta'].write_text('{}')
    runner.archive_attempt(paths)
    archives=list(paths['quarantine'].parent.glob('*attempt*'))
    assert len(archives)==2
    assert any(p.read_text()=='failed observations' for p in archives)


@pytest.mark.parametrize('rid',['../escape','bad\nname','bad/name'])
def test_unsafe_filename(rid):
    with pytest.raises(ValueError):C.run_paths(rid)


def test_health_uses_custom_namespace(monkeypatch):
    from mininet.env_runner import EnvRunner
    from bridge import ditto_reader,ditto_common
    monkeypatch.setattr(ditto_common,'NAMESPACE','org.dt4n.ml')
    things={ditto_common.make_thing_id_host(n):{'features':{'traffic':{'properties':{'rxRate':500000}}}} for n in ('srv1','srv2')}
    monkeypatch.setattr(ditto_reader,'fetch_snapshot',lambda *a:(things,{}))
    env=EnvRunner();env.session=object();env.thing_ids=list(things)
    assert env._read_throughput_norm()==pytest.approx(.4)
    things.clear()
    with pytest.raises(RuntimeError,match='Incomplete'):env._read_throughput_norm()
