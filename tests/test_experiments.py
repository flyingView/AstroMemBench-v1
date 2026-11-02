"""Domain contracts and real detached-worker lifecycle regressions."""
from copy import deepcopy
from contextlib import contextmanager
import csv
import io
import json
from pathlib import Path
import time

import pytest

from astromembench.catalog import Catalog, select_cases
from astromembench.experiments import ExperimentService
from astromembench.experiments.store import ACTIVE, Store
from astromembench.experiments import worker
from astromembench.experiments.service import V1_RELEASE_RUNTIMES
from astromembench import evaluation
from astromembench.persistence import read_json, write_json
from astromembench.usage import UsageLedger
from astromembench.metadata import TEMPLATE_SPECS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/benchmark'
CASES = ['FM-C1-P1-001', 'FM-C1-P1-002']
requires_bank = pytest.mark.skipif(not (DATA / 'tasks.jsonl').is_file(), reason='Install the complete release dataset for worker integration tests')


@pytest.fixture
def service(tmp_path):
    return ExperimentService(tmp_path / 'workspace', DATA)


def definition(service, *, groups=1, cases=None, slow=False, concurrency=1):
    if slow:
        script = service.root / 'slow.py'
        script.write_text("import runpy, time, sys\nmodule = runpy.run_path(sys.argv[1])\n"
            "kind = module['RandomAdapter']\noriginal = kind.handle\n"
            "def handle(self, operation, payload):\n"
            "    if operation == 'history': time.sleep(.08)\n"
            "    return original(self, operation, payload)\n"
            "kind.handle = handle\nmodule['main']()\n", encoding='utf-8')
        config = service.root / 'slow.json'
        write_json(config, {'name': 'Slow offline fixture', 'argv': ['${PYTHON}', str(script), str(ROOT / 'examples/random_adapter.py')]})
    else:
        config = ROOT / 'examples/random-adapter.json'
    adapter = service.import_adapter(config, parallel_safe=True)
    return {'name': 'Independent experiment', 'concurrency': concurrency,
            'groups': [{'name': f'Group {i + 1}', 'adapter_id': adapter['id'],
                        'selection': {'case_ids': cases or CASES}, 'mode': 'same_session' if i == 0 else 'new_session'}
                       for i in range(groups)]}


def until(predicate, *, timeout=35):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError('Worker did not reach the expected state')


def idle(service, identifier):
    return until(lambda: (state if (state := service.store.state(identifier))['status'] not in ACTIVE else None))


def test_selection_is_deterministic_and_explicit_filters_cannot_silently_drop_cases():
    rows = Catalog(DATA).rows
    chosen = select_cases(rows, {'templates': ['FM-C1-P1', 'FM-C1-P2'], 'limit': 3})
    assert chosen == ['FM-C1-P1-001', 'FM-C1-P1-002', 'FM-C1-P2-001']
    assert select_cases(rows, {'case_ids': list(reversed(CASES))}) == CASES
    with pytest.raises(ValueError, match='conflict'):
        select_cases(rows, {'case_ids': CASES, 'difficulties': ['hard']})
    with pytest.raises(ValueError, match='integer'):
        select_cases(rows, {'limit': True})


def test_import_and_pair_reviewed_v1_scores_across_releases(service, tmp_path):
    new = service.save(definition(service, cases=CASES[:1]))
    new_group = new["definition"]["groups"][0]["id"]
    result = {"case_id": CASES[0], "status": "agent_error",
              "outcome": {"score": 0, "full_credit": False, "termination": "agent_failure"}}
    service.store.record(new["id"], new_group, 1, CASES[0], result=result, attempt=1)
    for name, identity, comparable in (
            ("official", V1_RELEASE_RUNTIMES["1.0.0"], True),
            ("modified", "a" * 64, False),
            ("empty", "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a", False)):
        source = tmp_path / name
        write_json(source / "run.json", {"schema": "astromembench/run/1", "benchmark_version": "1.0.0",
                   "history_variant": "noisy", "mode": "same_session", "case_ids": CASES[:1],
                   "adapter": {"name": "legacy"}, "runtime_identity": identity,
                   "data_identity": new["definition"]["data_identity"]})
        (source / ".run.lock").touch()
        write_json(source / "cases" / CASES[0] / "attempts/0001/result.json", {**result, "status": "completed"})
        old = service.import_run(source)
        assert old["definition"]["benchmark_version"] == "1.0.0"
        old_group = old["definition"]["groups"][0]["id"]
        pair = service.compare(old["id"], old_group, new["id"], new_group)
        assert pair["comparable"] is comparable
        if comparable:
            assert pair["paired"] == 1 and pair["mean_difference"] == 0
        elif name == "empty":
            assert not service.compare(old["id"], old_group, old["id"], old_group)["comparable"]
    assert service.store.results(new["id"], status="agent_error")["total"] == 1


def test_projection_keeps_zero_failure_coverage_pagination_and_comparison_honest(service):
    spec = definition(service, groups=2)
    item = service.save(spec)
    identifier, groups = item['id'], item['definition']['groups']
    for i, group in enumerate(groups):
        service.store.record(identifier, group['id'], 1, CASES[0], result={'status': 'completed',
                             'outcome': {'score': 50 * i, 'full_credit': False}}, attempt=1)
        service.store.record(identifier, group['id'], 1, CASES[1], result={'status': 'infrastructure_error', 'error': '=FAIL()'}, attempt=1)
    stats = service.store.statistics(identifier)
    assert stats['overall']['mean_score'] == 25
    assert stats['overall']['coverage'] == .5
    assert stats['overall']['failed'] == 2
    page = service.store.results(identifier, limit=1, offset=1, status='completed')
    assert page['total'] == 2 and len(page['items']) == 1
    comparison = service.compare(identifier, groups[0]['id'], identifier, groups[1]['id'])
    assert comparison['mean_difference'] == 50 and comparison['paired_coverage'] == .5
    export, _ = service.export(identifier, 'csv')
    assert '=FAIL()' not in export.decode('utf-8-sig')
    exported = json.loads(service.export(identifier)[0])
    assert all('adapter' not in group for group in exported['experiment']['definition']['groups'])
    # Neither a failure nor a later write is permitted to replace a scored zero.
    service.store.record(identifier, groups[0]['id'], 1, CASES[0], result={'status': 'infrastructure_error'})
    assert service.store.result(identifier, groups[0]['id'], 1, CASES[0])['score'] == 0


@pytest.mark.parametrize('commit_before', ['FROM results WHERE', 'FROM group_totals WHERE'])
def test_export_is_one_snapshot_while_another_connection_commits(service, monkeypatch, commit_before):
    item = service.save(definition(service))
    identifier, group = item['id'], item['definition']['groups'][0]['id']
    writer = Store(service.root)
    connect = service.store.connect
    committed = False

    def concurrent_write(statement):
        nonlocal committed
        if committed or commit_before not in statement:
            return
        committed = True
        writer.record(identifier, group, 1, CASES[0],
                      result={'status': 'completed', 'outcome': {'score': 100, 'full_credit': True}})
        with writer.connect(write=True) as db:
            db.execute("UPDATE experiments SET status='paused',name='Changed during export',"
                       "definition=json_set(definition,'$.name','Changed during export') WHERE id=?", (identifier,))
            writer.touch(db, identifier)

    @contextmanager
    def observed_connection(*, write=False):
        with connect(write=write) as db:
            db.set_trace_callback(concurrent_write)
            yield db

    with monkeypatch.context() as patch:
        patch.setattr(service.store, 'connect', observed_connection)
        exported = json.loads(service.export(identifier)[0])

    assert committed, 'The writer must commit during the export, not before or after it'
    assert service.store.statistics(identifier)['overall']['scored'] == 1
    assert service.store.get(identifier)['definition']['name'] == 'Changed during export'
    assert exported['experiment']['status'] == 'draft'
    assert exported['experiment']['definition']['name'] == item['definition']['name']
    assert all(row['status'] == 'pending' and row['score'] is None for row in exported['results'])
    assert exported['statistics']['overall']['scored'] == 0
    assert exported['statistics']['overall']['pending'] == len(exported['results'])
    assert exported['statistics']['overall']['mean_score'] is None


def test_export_omits_raw_diagnostics_but_preserves_failure_status_and_user_names(service):
    spec = definition(service)
    spec['name'] = 'User-supplied research label'
    item = service.save(spec)
    identifier, group = item['id'], item['definition']['groups'][0]['id']
    diagnostic = r'Failed at C:\Users\ExampleUser\private: SYNTHETIC_NOT_A_SECRET'
    service.store.record(identifier, group, 1, CASES[0],
                         result={'status': 'infrastructure_error', 'error': diagnostic}, attempt=1)
    with service.store.connect(write=True) as db:
        db.execute("UPDATE experiments SET status='failed',error=? WHERE id=?", (diagnostic, identifier))
    exported_json, _ = service.export(identifier)
    exported_csv, _ = service.export(identifier, 'csv')
    for output in (exported_json, exported_csv):
        assert b'ExampleUser' not in output and b'SYNTHETIC_NOT_A_SECRET' not in output
        assert b'infrastructure_error' in output
    exported = json.loads(exported_json)
    assert exported['experiment']['definition']['name'] == spec['name']
    assert {'error', 'directory'}.isdisjoint(exported['experiment'])
    assert {'data', 'source'}.isdisjoint(exported['experiment']['definition'])
    assert all('adapter' not in row for row in exported['experiment']['definition']['groups'])
    assert all('error' not in row for row in exported['results'])
    assert 'error' not in csv.DictReader(io.StringIO(exported_csv.decode('utf-8-sig'))).fieldnames
    assert service.detail(identifier)['error'] == diagnostic
    assert service.store.result(identifier, group, 1, CASES[0])['error'] == diagnostic


def test_adapter_snapshot_and_group_immutability(service):
    spec = definition(service)
    item = service.save(spec)
    identifier = item['id']
    stored = service.store.get(identifier)['definition']
    adapter_id = spec['groups'][0]['adapter_id']
    service.store.save_adapter({**stored['groups'][0]['adapter'], 'name': 'Edited adapter'}, adapter_id=adapter_id, parallel_safe=True)
    request = deepcopy(item['definition'])
    request['name'] = 'Renamed draft'
    service.save(request, identifier)
    assert service.store.get(identifier)['definition']['groups'][0] == stored['groups'][0]
    with service.store.connect(write=True) as db:
        db.execute("UPDATE experiments SET status='paused' WHERE id=?", (identifier,))
    request = deepcopy(item['definition'])
    request['groups'].append({**spec['groups'][0], 'name': 'Added group'})
    appended = service.save(request, identifier, append=True)
    assert len(appended['definition']['groups']) == 2
    preserved = service.store.get(identifier)['definition']['groups'][0]
    assert preserved == stored['groups'][0]
    request['groups'][0]['mode'] = 'new_session'
    with pytest.raises(ValueError, match='immutable'):
        service.save(request, identifier, append=True)
    with pytest.raises(RuntimeError):
        service.save(spec, identifier)


def test_usage_missing_is_unknown_and_only_reported_deltas_are_added():
    usage = UsageLedger()
    usage.observe({}, 'setup')
    assert usage.snapshot() is None
    usage.observe({'usage': {'input_tokens': 0, 'model_calls': 1}}, 'history')
    usage.observe({'usage': {'input_tokens': 12, 'output_tokens': 4}}, 'history')
    assert usage.observe({'usage': {'input_tokens': -1}}, 'current')
    value = usage.snapshot()
    assert value['totals'] == {'input_tokens': 12, 'output_tokens': 4, 'model_calls': 1}
    assert value['reported_operations'] == 2 and value['completed_operations'] == 4


def test_stop_cannot_be_downgraded_and_terminal_records_do_not_invalidate_snapshots(service):
    item = service.save(definition(service))
    identifier, group = item['id'], item['definition']['groups'][0]['id']
    service.store.request_start(identifier)
    service.store.control(identifier, 'stop')
    service.store.control(identifier, 'pause')
    assert service.store.state(identifier)['desired'] == 'stop'
    assert service.store.state(identifier)['status'] == 'stopping'
    service.store.finish_worker(identifier, service.store.state(identifier)['epoch'])
    assert service.store.state(identifier)['status'] == 'stopped'
    service.store.record(identifier, group, 1, CASES[0], result={'status': 'completed', 'outcome': {'score': 0}})
    revision = service.store.state(identifier)['revision']
    service.store.record(identifier, group, 1, CASES[0], result={'status': 'infrastructure_error'})
    assert service.store.state(identifier)['revision'] == revision
    epoch = service.store.request_start(identifier)
    service.store.record(identifier, group, 1, CASES[1])
    service.store.finish_worker(identifier, epoch, error='Injected worker failure')
    assert service.store.state(identifier)['status'] == 'failed'
    assert service.store.statistics(identifier)['overall']['running'] == 0
    assert service.store.statistics(identifier)['overall']['interrupted'] == 1


def test_group_totals_match_full_queries_after_transitions_and_migration(service):
    item = service.save(definition(service, groups=2))
    identifier = item['id']
    group = item['definition']['groups'][0]['id']
    for result in (None, {'status': 'interrupted'}, {'status': 'infrastructure_error', 'elapsed_s': 3},
                   {'status': 'completed', 'outcome': {'score': 0}, 'elapsed_s': 4}):
        service.store.record(identifier, group, 1, CASES[0], result=result)
        fast = service.store.statistics(identifier)['overall']
        scanned = service.store.statistics(identifier, axis='challenge')['overall']
        assert fast == scanned
    service.store.record(identifier, group, 1, CASES[1], result={'status': 'unsupported', 'elapsed_s': 2})
    before = service.store.statistics(identifier)
    capability = service.store.statistics(identifier, axis='capability')
    assert capability['overall'] == before['overall']
    assert {row['label'] for row in capability['items']} == set(TEMPLATE_SPECS['FM-C1-P1'].capabilities)
    assert all(row['total'] == before['overall']['total'] and row['scored'] == before['overall']['scored'] for row in capability['items'])
    with service.store.connect(write=True) as db:
        db.execute('DROP TABLE group_totals')
    reopened = ExperimentService(service.root, DATA)
    assert reopened.store.statistics(identifier) == before


def test_interrupted_schema_initialization_rolls_back_and_retries(service, monkeypatch):
    from astromembench.experiments.store import Store
    item = service.save(definition(service))
    before = service.store.statistics(item['id'])
    with service.store.connect(write=True) as db:
        db.execute('DROP TABLE group_totals')
    with monkeypatch.context() as patch:
        def interrupted(*args):
            raise RuntimeError('Injected initialization interruption')
        patch.setattr(Store, 'rebuild_totals', interrupted)
        with pytest.raises(RuntimeError, match='initialization interruption'):
            Store(service.root)
    assert Store(service.root).statistics(item['id']) == before


def test_worker_publishes_final_state_after_releasing_ownership(service, monkeypatch):
    item = service.save(definition(service))
    identifier = item['id']
    epoch = service.store.request_start(identifier)
    real_lock = worker._run_lock
    released = []
    @contextmanager
    def observed_lock(path):
        with real_lock(path):
            yield
            assert service.store.state(identifier)['status'] in ACTIVE
        released.append(True)
    def invalid_bank(*args):
        raise ValueError('Injected dataset validation failure')
    monkeypatch.setattr(worker, '_run_lock', observed_lock)
    monkeypatch.setattr(worker, 'PreparedBank', invalid_bank)
    worker.run(service.root, identifier, epoch)
    assert released and service.store.state(identifier)['status'] == 'failed'


def test_reconcile_does_not_overwrite_a_worker_that_claimed_ownership(service, monkeypatch):
    import astromembench.experiments.service as service_module
    item = service.save(definition(service))
    identifier = item['id']
    service.store.request_start(identifier)
    with service.store.connect(write=True) as db:
        db.execute("UPDATE experiments SET heartbeat='2000-01-01T00:00:00+00:00' WHERE id=?", (identifier,))
    def claimed_during_probe(pid, created):
        with service.store.connect(write=True) as db:
            db.execute("UPDATE experiments SET pid=123,process_time=456,status='running' WHERE id=?", (identifier,))
        return False
    monkeypatch.setattr(service_module, '_alive', claimed_during_probe)
    service.reconcile(force=True)
    assert service.store.state(identifier)['status'] == 'running'


def test_trace_pages_bound_damage_and_wait_for_an_active_partial_record(service):
    item = service.save(definition(service))
    identifier, group = item['id'], item['definition']['groups'][0]['id']
    relative = f'groups/{group}/0001/cases/{CASES[0]}/attempts/0001/result.json'
    trace = (service.directory(identifier) / relative).with_name('events.jsonl')
    trace.parent.mkdir(parents=True)
    content = b'{"event":"valid"}\ninvalid\n{"event":"part'
    trace.write_bytes(content)
    service.store.record(identifier, group, 1, CASES[0], result={'status': 'interrupted'}, attempt=1, result_path=relative)
    page = service.events(identifier, group, 1, CASES[0])
    assert [item['event'] for item in page['items']] == ['valid', 'invalid_record', 'truncated_record']
    assert not page['has_more'] and page['next_cursor'] == len(content)
    service.store.request_start(identifier)
    service.store.record(identifier, group, 1, CASES[0], attempt=1, result_path=relative)
    page = service.events(identifier, group, 1, CASES[0])
    assert page['waiting_for_complete_record'] and not page['has_more']
    assert page['next_cursor'] == content.index(b'{"event":"part')
    trace.write_bytes(content + b'ial"}\n')
    next_page = service.events(identifier, group, 1, CASES[0], cursor=page['next_cursor'])
    assert next_page['items'] == [{'event': 'partial'}]
    assert not next_page['has_more'] and not next_page['waiting_for_complete_record']


@requires_bank
def test_imported_cli_run_refreshes_after_resume_without_rewriting_source(service):
    spec = definition(service)
    adapter = service.adapter(spec['groups'][0]['adapter_id'])['definition']
    source = service.root / 'cli-source'
    finished = []
    first = evaluation.run_evaluation(data=DATA, output=source, adapter=adapter, case_ids=CASES,
        pause_requested=lambda: bool(finished), progress=lambda event: finished.append(True) if event['event'] == 'case_finished' else None)
    assert first['scored'] == 1
    imported = service.import_run(source)
    assert imported['definition']['read_only']
    assert service.store.statistics(imported['id'])['overall']['scored'] == 1
    with pytest.raises(ValueError, match='read-only'):
        service.start(imported['id'])
    evaluation.run_evaluation(data=DATA, output=source, adapter=adapter, case_ids=CASES, resume=True)
    saved = {p: p.read_bytes() for p in source.rglob('*.json')}
    refreshed = service.import_run(source)
    assert refreshed['id'] == imported['id'] and refreshed['status'] == 'completed'
    assert service.store.statistics(imported['id'])['overall']['scored'] == 2
    assert all(p.read_bytes() == value for p, value in saved.items())
    changed = read_json(source / 'run.json')
    changed['mode'] = 'new_session'
    write_json(source / 'run.json', changed)
    with pytest.raises(ValueError, match='definition changed'):
        service.import_run(source)


@requires_bank
def test_detached_worker_pause_resume_and_duplicate_start(service):
    item = service.save(definition(service, slow=True))
    identifier = item['id']
    service.start(identifier)
    try:
        with pytest.raises(RuntimeError, match='active worker'):
            service.start(identifier)
        until(lambda: any((row.get('runtime') or {}).get('history_processed', 0) >= 1
                          for row in service.snapshot(identifier)['active']))
        service.control(identifier, 'pause')
        assert idle(service, identifier)['status'] == 'paused'
        assert service.store.statistics(identifier)['overall']['scored'] == 1
        # The creator is gone; a new process-facing service opens the same files.
        reopened = ExperimentService(service.root, DATA)
        reopened.start(identifier)
        assert idle(reopened, identifier)['status'] == 'completed'
        results = reopened.store.results(identifier)['items']
        assert [row['attempt'] for row in results] == [1, 1]
        state = reopened.snapshot(identifier)
        assert reopened.snapshot(identifier, state['revision'])['unchanged']
        assert not service.snapshot(identifier, state['revision']).get('unchanged')
    finally:
        service.control(identifier, 'stop')
        idle(service, identifier)


@requires_bank
def test_stop_preserves_interrupted_attempt_and_resume_retries_only_that_case(service):
    item = service.save(definition(service, slow=True))
    identifier = item['id']
    service.start(identifier)
    try:
        until(lambda: any((row.get('runtime') or {}).get('history_processed', 0) >= 1
                          for row in service.snapshot(identifier)['active']))
        service.control(identifier, 'stop')
        assert idle(service, identifier)['status'] == 'stopped'
        assert service.store.statistics(identifier)['overall']['interrupted'] == 1
        service.start(identifier)
        assert idle(service, identifier)['status'] == 'completed'
        rows = service.store.results(identifier)['items']
        assert [row['attempt'] for row in rows] == [2, 1]
        detail = service.result_detail(identifier, rows[0]['group_id'], 1, CASES[0], attempt=1)
        assert detail['result']['status'] == 'interrupted' and detail['attempts'] == [1, 2]
        events = service.events(identifier, rows[0]['group_id'], 1, CASES[0], attempt=1, limit=1)
        assert len(events['items']) == 1 and events['has_more']
        with pytest.raises(ValueError, match='boundary'):
            service.events(identifier, rows[0]['group_id'], 1, CASES[0], cursor=1)
    finally:
        service.control(identifier, 'stop')
        idle(service, identifier)


@requires_bank
def test_parallel_groups_use_distinct_lanes_and_both_session_modes(service):
    item = service.save(definition(service, groups=2, cases=CASES[:1], slow=True, concurrency=2))
    identifier = item['id']
    service.start(identifier)
    try:
        until(lambda: len(service.snapshot(identifier)['active']) == 2)
        assert idle(service, identifier)['status'] == 'completed'
        rows = service.store.results(identifier)['items']
        assert len(rows) == 2 and all(row['attempt'] == 1 for row in rows)
        boundaries = []
        for row in rows:
            result = service.result_detail(identifier, row['group_id'], 1, row['case_id'])['result']
            boundaries.append(sum(event['operation'] == 'new_session' for event in result['lifecycle']))
        assert sorted(boundaries) == [1, 2]
    finally:
        service.control(identifier, 'stop')
        idle(service, identifier)
