"""Protocol, lifecycle and resume checks without model or network calls."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from astromembench import evaluation
from astromembench.persistence import read_json, write_json
from astromembench.protocol import InfrastructureError, JsonProcess, RunInterrupted, UnsupportedCapability
from astromembench.runner import run_task
from astromembench.schema import Task


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def task():
    path = ROOT / 'data/benchmark/tasks.jsonl'
    if not path.is_file():
        path = ROOT / 'tests/fixtures/task.json'
    with path.open(encoding='utf-8') as stream:
        return Task.from_dict(json.loads(next(stream)))


class Participant:
    """A protocol-only witness that always ends the task with a zero score."""
    def __init__(self, *args, **kwargs):
        self.calls = []
        self.session = 0
        self.closed = False

    def call(self, operation, payload):
        self.calls.append((operation, deepcopy(payload)))
        if operation == 'reset':
            return {'cleared': True}
        if operation == 'new_session':
            self.session += 1
            return {'conversation_id': str(self.session)}
        if operation == 'history':
            return {'processed': True, 'assistant_text': '收到'}
        if operation == 'observe':
            return {'action_submitted': True, 'action': {'action': 'end'}}
        return {'processed': True}

    def close(self):
        self.closed = True


@pytest.mark.parametrize('mode, sessions', [('same_session', 1), ('new_session', 2)])
def test_fixed_task_lifecycle_preserves_thirty_rounds(task, tmp_path, mode, sessions):
    participant = Participant()
    result = run_task(task, participant, mode, asset_root=ROOT / 'data/benchmark/assets', output=tmp_path)
    assert participant.closed
    assert result['outcome']['score'] == 0
    operations = [operation for operation, _ in participant.calls]
    assert operations.count('history') == 30
    assert operations.count('new_session') == sessions
    assert operations.index('observe') > max(i for i, op in enumerate(operations) if op == 'history')
    assert operations[-2:] == ['feedback', 'end']
    for operation, payload in participant.calls:
        if operation in {'history', 'observe'}:
            assert not {'world', 'rubric', 'design'} & payload.keys()


def test_finalization_failure_cannot_replace_a_durable_zero(task, tmp_path):
    class FailingFeedback(Participant):
        def call(self, operation, payload):
            if operation in {'feedback', 'end'}:
                raise InfrastructureError('Example finalization failure')
            return super().call(operation, payload)
    result = run_task(task, FailingFeedback(), 'same_session', asset_root=tmp_path, output=tmp_path)
    assert result['outcome']['score'] == 0
    assert [warning['operation'] for warning in result['warnings']] == ['feedback', 'end']
    assert read_json(tmp_path / 'result.json')['outcome']['score'] == 0


def test_cross_session_requires_a_distinct_conversation(task, tmp_path):
    class ReusedConversation(Participant):
        def call(self, operation, payload):
            result = super().call(operation, payload)
            if operation == 'new_session':
                result['conversation_id'] = 'unchanged'
            return result
    result = run_task(task, ReusedConversation(), 'new_session', asset_root=tmp_path)
    assert result['status'] == 'infrastructure_error'
    assert result['outcome'] is None


@pytest.fixture
def tiny_bank(task, tmp_path, monkeypatch):
    """Isolate run bookkeeping while using one unchanged released task."""
    import astromembench.benchmark as benchmark
    import astromembench.catalog as catalog
    data = tmp_path / 'data'
    data.mkdir()
    write_json(data / 'index.json', {'cases': [{'case_id': task.case_id}]})
    class TinyBank(catalog.PreparedBank):
        def __init__(self, data):
            self.identity = 'fixed-task-test-identity'
        def check(self, data):
            pass
        def tasks(self, selected):
            return iter([deepcopy(task)] if task.case_id in selected else [])
    monkeypatch.setattr(catalog, 'PreparedBank', TinyBank)
    monkeypatch.setattr(benchmark, 'assets_path', lambda data: ROOT / 'data/benchmark/assets')
    return data


def test_resume_never_repeats_a_scored_zero(tiny_bank, tmp_path, monkeypatch):
    created = []
    class CountedParticipant(Participant):
        def __init__(self, *args, **kwargs):
            super().__init__()
            created.append(self)
    monkeypatch.setattr(evaluation, 'JsonProcess', CountedParticipant)
    output = tmp_path / 'run'
    adapter = {'name': 'witness', 'argv': ['unused'], 'config': {}}
    first = evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter)
    assert first['scored'] == 1 and first['mean_score'] == 0
    result_path = output / first['cases'][0]['result_path']
    before = result_path.read_bytes()
    timing = read_json(result_path)['timing']
    assert timing['stages']['native_startup']['started'] is True
    assert timing['stages']['native_startup']['complete'] is True
    assert timing['end_to_end']['timing_complete'] is True
    assert timing['end_to_end']['raw_s'] >= timing['stages']['native_startup']['raw_s'] >= 0
    recovered = []
    monkeypatch.setattr(evaluation, 'recover_adapter', lambda path: recovered.append(path))
    second = evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter, resume=True)
    assert second['scored'] == 1 and len(created) == 1
    assert recovered == [result_path.parent / 'workspace']
    assert result_path.read_bytes() == before
    with pytest.raises(ValueError, match='same dataset'):
        evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter, mode='new_session', resume=True)


def test_resume_preserves_failed_attempt_and_counts_only_real_scores(tiny_bank, tmp_path, monkeypatch):
    class Disconnected(Participant):
        def call(self, operation, payload):
            raise InfrastructureError('Disconnected before history')
    monkeypatch.setattr(evaluation, 'JsonProcess', Disconnected)
    output = tmp_path / 'run'
    adapter = {'name': 'witness', 'argv': ['unused']}
    first = evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter)
    assert first['failed'] == 1 and first['mean_score'] is None
    failed_path = output / first['cases'][0]['result_path']
    original = failed_path.read_bytes()
    monkeypatch.setattr(evaluation, 'JsonProcess', Participant)
    second = evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter, resume=True)
    assert second['scored'] == 1 and second['cases'][0]['attempt'] == 2
    assert failed_path.read_bytes() == original


def test_unsupported_is_unscored_and_not_retried_on_resume(tiny_bank, tmp_path, monkeypatch):
    calls = []
    class Unsupported(Participant):
        def call(self, operation, payload):
            calls.append(operation)
            raise UnsupportedCapability('This example subject cannot process the required input')
    monkeypatch.setattr(evaluation, 'JsonProcess', Unsupported)
    output = tmp_path / 'unsupported'
    adapter = {'name': 'unsupported-witness', 'argv': ['unused']}
    summary = evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter)
    assert summary['unsupported'] == 1 and summary['finished'] == 1
    assert summary['scored'] == 0 and summary['mean_score'] is None
    evaluation.run_evaluation(data=tiny_bank, output=output, adapter=adapter, resume=True)
    assert calls == ['reset']


def test_process_adapter_receives_only_declared_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('ASTROMEMBENCH_TEST_ALLOWED', 'visible')
    monkeypatch.setenv('ASTROMEMBENCH_TEST_HIDDEN', 'not inherited')
    code = ('import json,os,sys\n'
            'for line in sys.stdin:\n'
            ' m=json.loads(line); print(json.dumps({"id":m["id"],"result":'
            '{"allowed":os.environ.get("ASTROMEMBENCH_TEST_ALLOWED"),'
            '"hidden":os.environ.get("ASTROMEMBENCH_TEST_HIDDEN"),'
            '"home":os.environ["HOME"]}}),flush=True)\n')
    process = JsonProcess([sys.executable, '-c', code], tmp_path / 'workspace', {},
                          pass_env=('ASTROMEMBENCH_TEST_ALLOWED',), timeout_s=5)
    try:
        result = process.call('reset', {})
        assert result['allowed'] == 'visible' and result['hidden'] is None
        assert Path(result['home']) == tmp_path / 'workspace/home'
    finally:
        process.close()
    assert read_json(tmp_path / 'workspace/process.json')['closed'] is True


def test_cancel_stops_waiting_for_adapter(tmp_path):
    started = time.monotonic()
    process = JsonProcess([sys.executable, '-c', 'import time; time.sleep(60)'],
                          tmp_path / 'workspace', {}, cancelled=lambda: True)
    try:
        with pytest.raises(RunInterrupted):
            process.call('reset', {})
    finally:
        process.close()
    assert time.monotonic() - started < 10


@pytest.mark.skipif(sys.platform != 'linux', reason='POSIX detached pipe regression runs on Linux CI')
def test_cancel_does_not_wait_for_a_detached_stdout_holder(tmp_path):
    import signal
    workspace = tmp_path / 'workspace'
    pidfile = workspace / 'detached.pid'
    code = '''
import os, subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
Path(os.environ['ASTROMEMBENCH_WORKSPACE'], 'detached.pid').write_text(str(child.pid))
time.sleep(60)
'''
    def deadline(*_):
        raise TimeoutError('Adapter cancellation waited for detached stdout')
    previous_handler = signal.signal(signal.SIGALRM, deadline)
    signal.setitimer(signal.ITIMER_REAL, 10)
    process = None
    started = time.monotonic()
    try:
        process = JsonProcess([sys.executable, '-c', code], workspace, {}, cancelled=pidfile.exists)
        try:
            with pytest.raises(RunInterrupted):
                process.call('history', {'text': 'x' * 1_000_000})
        finally:
            process.close()
        assert process.closed and time.monotonic() - started < 5
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        # The test owns this detached process. The production transport does
        # not claim to sandbox or own arbitrary daemon sessions.
        if pidfile.exists():
            try:
                os.killpg(int(pidfile.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process is not None and not process.closed:
            process.close()


def test_adapter_paths_resolve_from_configuration_directory(tmp_path):
    script = tmp_path / 'adapter.py'
    script.write_text('# example', encoding='utf-8')
    path = tmp_path / 'adapter.json'
    write_json(path, {'argv': ['${PYTHON}', 'adapter.py']})
    definition = evaluation.load_adapter(path)
    assert definition['argv'] == [sys.executable, str(script)]


def test_run_lock_excludes_another_process_and_survives_owner_exit(tmp_path):
    code = '''
import os, sys
from pathlib import Path
from astromembench.evaluation import _run_lock
try:
    with _run_lock(Path(sys.argv[1])):
        print('acquired', flush=True)
        if sys.argv[2] == 'exit':
            os._exit(0)
except ValueError:
    print('blocked', flush=True)
'''
    # Child processes must exercise the same installation as the parent test.
    env = {**os.environ, 'PYTHONPATH': str(Path(evaluation.__file__).resolve().parents[1]),
           'PYTHONDONTWRITEBYTECODE': '1'}
    def child(action='normal'):
        return subprocess.run([sys.executable, '-c', code, str(tmp_path), action],
            env=env, text=True, capture_output=True, timeout=10, check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0).stdout.strip()
    with evaluation._run_lock(tmp_path):
        assert child() == 'blocked'
    assert child('exit') == 'acquired'
    # No PID parsing, stale-file deletion, or manual lock cleanup is needed.
    with evaluation._run_lock(tmp_path):
        assert child() == 'blocked'
    assert (tmp_path / '.run.lock').is_file()


def test_concurrent_summary_cannot_overwrite_newer_evaluator_progress(tmp_path, monkeypatch):
    run = {'benchmark_version': '1.0.0', 'adapter': {'name': 'witness'},
           'mode': 'same_session', 'history_variant': 'noisy', 'case_ids': ['case-one']}
    write_json(tmp_path / 'run.json', run)
    observed, proceed = threading.Event(), threading.Event()
    original = evaluation._case_result

    def slow_read(*args):
        result = original(*args)
        observed.set()
        assert proceed.wait(5), 'Timed out waiting for the evaluator snapshot'
        return result

    monkeypatch.setattr(evaluation, '_case_result', slow_read)
    with ThreadPoolExecutor(max_workers=1) as reader:
        snapshot = reader.submit(evaluation.summarize, tmp_path)
        try:
            assert observed.wait(5), 'Summary did not read the pending case'
            result = {'case_id': 'case-one', 'status': 'completed',
                      'outcome': {'score': 100, 'full_credit': True}}
            result_path = tmp_path / 'cases/case-one/attempts/0001/result.json'
            write_json(result_path, result)
            with evaluation._run_lock(tmp_path):
                evaluation._save_summary(tmp_path, {'case-one': (result, result_path)}, run)
            expected = (tmp_path / 'summary.json').read_bytes()
        finally:
            proceed.set()
        # A reader can observe a case before completion. It must never replace
        # the newer on-disk summary after the evaluator has completed it.
        assert snapshot.result(timeout=5)['pending'] == 1
    assert (tmp_path / 'summary.json').read_bytes() == expected
    assert read_json(tmp_path / 'summary.json')['mean_score'] == 100
