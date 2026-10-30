"""Serial evaluation of the fixed bank through user-supplied JSONL adapters."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import shutil
from statistics import mean
import sys

from . import __version__, PROTOCOL_VERSION
from .persistence import read_json, write_json
from .protocol import JsonProcess, RunInterrupted, recover_adapter
from .runner import run_task
from .timing import StageClock


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode('utf-8')).hexdigest()


def load_adapter(path):
    """Resolve file arguments relative to the adapter JSON, never the task HOME."""
    path = Path(path).resolve()
    definition = read_json(path)
    if not isinstance(definition, dict):
        raise ValueError('Adapter configuration must be a JSON object')
    argv = definition.get('argv')
    if not isinstance(argv, list) or not argv or any(not isinstance(v, str) or not v for v in argv):
        raise ValueError('Adapter argv must be a nonempty array of strings')
    resolved = []
    for index, argument in enumerate(argv):
        argument = argument.replace('${PYTHON}', sys.executable)
        candidate = path.parent / argument
        if not argument.startswith('-') and not Path(argument).is_absolute() and candidate.exists():
            argument = str(candidate.resolve())
        if index == 0 and not Path(argument).is_absolute():
            executable = shutil.which(argument)
            if executable is None:
                raise ValueError(f'Adapter executable was not found: {argument}')
            argument = executable
        resolved.append(argument)
    name = definition.get('name', path.stem)
    if not isinstance(name, str) or not name.strip():
        raise ValueError('Adapter name must be nonempty text')
    config = definition.get('config', {})
    if not isinstance(config, dict):
        raise ValueError('Adapter config must be a JSON object')
    pass_env = definition.get('pass_env', [])
    if not isinstance(pass_env, list) or any(not isinstance(v, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', v) for v in pass_env):
        raise ValueError('pass_env must contain environment variable names')
    credential_env = definition.get('credential_env')
    if credential_env is not None and (not isinstance(credential_env, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', credential_env)):
        raise ValueError('credential_env must be an environment variable name')
    timeout = definition.get('timeout_s', 7200)
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('timeout_s must be a positive finite number')
    return {'name': name, 'argv': resolved, 'config': config,
            'pass_env': pass_env, 'credential_env': credential_env, 'timeout_s': timeout}


def _terminal(result):
    return (isinstance(result.get('outcome'), dict)
            or result.get('status') == 'unsupported')


def _case_result(output, case_id):
    """The first durable scored/unsupported result wins, even after a crash."""
    directory = output / 'cases' / case_id
    attempts = sorted((directory / 'attempts').glob('[0-9][0-9][0-9][0-9]/result.json'))
    latest = None
    for path in attempts:
        result = read_json(path)
        if result.get('case_id') != case_id:
            raise ValueError(f'Result identity differs from its directory: {case_id}')
        latest = result, path
        if _terminal(result):
            return latest
    return latest


def summarize(output, *, _known=None, _run=None):
    """Read saved results without overwriting an active evaluator's snapshot."""
    output = Path(output).resolve()
    run = _run if _run is not None else read_json(output / 'run.json')
    cases, scores = [], []
    counts = dict(finished=0, scored=0, unsupported=0, failed=0, interrupted=0, pending=0)
    full_credit = 0
    for case_id in run['case_ids']:
        found = _case_result(output, case_id) if _known is None else _known.get(case_id)
        row = {'case_id': case_id, 'status': 'pending', 'score': None,
               'result_path': None, 'attempt': None}
        if found:
            result, path = found
            row.update(status=result['status'], result_path=path.relative_to(output).as_posix(),
                       attempt=int(path.parent.name))
            outcome = result.get('outcome')
            if isinstance(outcome, dict):
                score = outcome.get('score')
                if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100:
                    raise ValueError(f'Invalid saved score for {case_id}')
                row['score'] = score
                scores.append(score)
                counts['scored'] += 1
                counts['finished'] += 1
                full_credit += outcome.get('full_credit') is True
            elif result['status'] == 'unsupported':
                counts['unsupported'] += 1
                counts['finished'] += 1
            elif result['status'] == 'interrupted':
                counts['interrupted'] += 1
            else:
                counts['failed'] += 1
        else:
            counts['pending'] += 1
        cases.append(row)
    value = {'schema': 'astromembench/summary/1', 'benchmark_version': run['benchmark_version'],
             'adapter': run['adapter']['name'], 'mode': run['mode'],
             'history_variant': run['history_variant'], 'total': len(cases), **counts,
             'mean_score': mean(scores) if scores else None, 'full_credit_count': full_credit,
             'status': 'completed' if counts['finished'] == len(cases) else 'incomplete',
             'updated_utc': utcnow(), 'cases': cases}
    return value


def _save_summary(output, known, run):
    """Persist progress only while the evaluator owns the output lock."""
    value = summarize(output, _known=known, _run=run)
    write_json(output / 'summary.json', value)
    return value


@contextmanager
def _run_lock(output):
    """Keep a stable lock file; the OS releases ownership when a process exits."""
    path = output / '.run.lock'
    with path.open('a+b') as stream:
        # Windows byte-range locking needs an existing byte. Keep this file
        # after release: unlinking it would let contenders lock different files.
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            acquire = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        try:
            acquire()
        except OSError as exc:
            raise ValueError('This output directory already has a running evaluator, or cannot be locked') from exc
        try:
            yield
        finally:
            stream.seek(0)
            release()


def _runtime_identity():
    root = Path(__file__).parent
    sources = {path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
               for path in root.rglob('*.py') if not {'webui', 'experiments'} & set(path.parts)
               and path.name not in {'catalog.py', 'cli.py'}}
    return _digest(sources)


def run_evaluation(*, data, output, adapter, case_ids=None, mode='same_session',
                   history_variant='noisy', resume=False, cancelled=None, progress=None,
                   pause_requested=None, prepared_bank=None):
    """Run serially; only explicit resume retries an unscored failed attempt.

    A result already containing a score is never recomputed, including a zero.
    Each attempt owns a fresh directory; interrupted traces are preserved.
    """
    from .benchmark import assets_path
    from .catalog import PreparedBank

    if mode not in {'same_session', 'new_session'}:
        raise ValueError('mode must be same_session or new_session')
    if history_variant != 'noisy':
        raise ValueError('This release evaluates the fixed published task bank only')
    data, output = Path(data).resolve(), Path(output).resolve()
    if prepared_bank is None:
        prepared_bank = PreparedBank(data)
    if not isinstance(prepared_bank, PreparedBank):
        raise ValueError('Expected a verified fixed dataset')
    prepared_bank.check(data)
    manifest = read_json(data / 'index.json')
    available = [row['case_id'] for row in manifest['cases']]
    selected = list(available if case_ids is None else case_ids)
    if (not selected or len(set(selected)) != len(selected)
            or any(case not in available for case in selected)):
        raise ValueError('Choose distinct case IDs present in the fixed dataset')
    # Dataset order is stable regardless of the order of --case arguments.
    wanted = set(selected)
    selected = [case for case in available if case in wanted]
    definition = {'schema': 'astromembench/run/1', 'benchmark_version': __version__,
                  'protocol': PROTOCOL_VERSION, 'data_identity': prepared_bank.identity,
                  'runtime_identity': _runtime_identity(), 'adapter': adapter,
                  'case_ids': selected, 'mode': mode, 'history_variant': history_variant}
    output.mkdir(parents=True, exist_ok=True)
    with _run_lock(output):
        existing = output / 'run.json'
        if existing.exists():
            if not resume:
                raise ValueError('Output already contains a run; choose another directory or use --resume')
            run = read_json(existing)
            if any(run.get(key) != value for key, value in definition.items()):
                raise ValueError('Resume requires the same dataset, evaluator, adapter, cases, mode and history')
        else:
            if resume:
                raise ValueError('There is no saved run to resume in this output directory')
            if any(path.name != '.run.lock' for path in output.iterdir()):
                raise ValueError('Output directory is not empty; no existing files were overwritten')
            run = {**definition, 'created_utc': utcnow()}
            write_json(existing, run)

        def emit(event, **fields):
            if progress is not None:
                progress({'event': event, 'output': str(output), 'total': len(selected), **fields})

        # Read existing results once. Subsequent progress snapshots use this
        # in-memory inventory instead of rescanning all case directories.
        # A durable score may precede adapter cleanup. Recover every prior
        # attempt without decoding the large history payload of finished cases.
        for case in selected:
            for prior in (output / 'cases' / case / 'attempts').glob('[0-9][0-9][0-9][0-9]'):
                if prior.is_dir():
                    recover_adapter(prior / 'workspace')
        known = {case: _case_result(output, case) for case in selected}
        summary = _save_summary(output, known, run)
        emit('run_started', completed=summary['finished'], summary=summary)
        pending_cases = [case for case in selected if not (known[case] and _terminal(known[case][0]))]
        for task in prepared_bank.tasks(pending_cases):
            if ((cancelled is not None and cancelled())
                    or (pause_requested is not None and pause_requested())):
                break
            directory = output / 'cases' / task.case_id
            attempts = directory / 'attempts'
            attempts.mkdir(parents=True, exist_ok=True)
            previous = sorted(path for path in attempts.iterdir() if path.is_dir() and re.fullmatch(r'\d{4}', path.name))
            number = max((int(path.name) for path in previous), default=0) + 1
            if number > 9999:
                raise ValueError('This case has reached the explicit attempt limit')
            attempt = attempts / f'{number:04d}'
            attempt.mkdir()
            write_json(attempt / 'attempt.json', {'case_id': task.case_id, 'number': number, 'started_utc': utcnow()})
            emit('case_started', case_id=task.case_id, completed=summary['finished'], attempt=number,
                 result_path=(attempt / 'result.json').relative_to(output).as_posix())
            participant = None
            timing = StageClock(mode, path=attempt / 'timing-events.jsonl', job_id=task.case_id)
            timing.start('native_startup')
            try:
                participant = JsonProcess(adapter['argv'], attempt / 'workspace', adapter.get('config', {}),
                    timeout_s=adapter.get('timeout_s', 7200), pass_env=tuple(adapter.get('pass_env', [])),
                    credential_env=adapter.get('credential_env'), cancelled=cancelled)
                timing.transition('setup', complete=True)
                result = run_task(task, participant, mode, asset_root=assets_path(data), output=attempt,
                                  cancelled=cancelled, timing=timing)
            except (Exception, KeyboardInterrupt) as exc:
                # A terminal score committed before finalization must win even
                # when later observer or process cleanup code raises.
                committed = read_json(attempt / 'result.json') if (attempt / 'result.json').exists() else None
                if committed and _terminal(committed):
                    result = committed
                else:
                    timing.finish(complete=False)
                    result = {'benchmark_version': __version__, 'protocol': PROTOCOL_VERSION,
                              'case_id': task.case_id, 'template': task.template, 'mode': mode,
                              'status': 'interrupted' if isinstance(exc, (KeyboardInterrupt, RunInterrupted)) else 'infrastructure_error',
                              'outcome': None, 'error': str(exc), 'finished_utc': utcnow(),
                              'timing': timing.snapshot()}
                    write_json(attempt / 'result.json', result)
                if isinstance(exc, KeyboardInterrupt):
                    write_json(directory / 'result.json', result)
                    known[task.case_id] = (result, attempt / 'result.json')
                    break
            finally:
                if participant is not None and not participant.closed:
                    participant.close()
            write_json(directory / 'result.json', result)
            known[task.case_id] = (result, attempt / 'result.json')
            summary = _save_summary(output, known, run)
            emit('case_finished', case_id=task.case_id, completed=summary['finished'],
                 result=result, summary=summary, attempt=number,
                 result_path=(attempt / 'result.json').relative_to(output).as_posix())
        summary = _save_summary(output, known, run)
        write_json(existing, {**run, 'updated_utc': utcnow(), 'status': summary['status']})
        emit('run_finished', completed=summary['finished'], summary=summary)
        return summary
