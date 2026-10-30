"""Experiment use cases shared by the CLI and HTTP interface."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import psutil

from ..catalog import Catalog, integer, select_cases
from ..benchmark import bank_identity
from ..evaluation import load_adapter, _runtime_identity, utcnow, summarize, _run_lock
from ..persistence import read_json, write_json, json_signature
from ..schema import json_text
from .design import normalize, label
from .store import Store, ACTIVE


def _alive(pid, created):
    if not pid or not created:
        return False
    try:
        process = psutil.Process(pid)
        return abs(process.create_time() - created) < .01 and process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _inside(root, relative):
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Saved path escapes the experiment directory')
    return target


class ExperimentService:
    def __init__(self, workspace, data=None):
        self.store = Store(workspace)
        self.root = self.store.root
        self.instance = uuid4().hex
        self.catalog = Catalog(data, self.root / 'cache') if data is not None else None
        self._last_reconcile = 0

    def set_data(self, data):
        catalog = Catalog(data, self.root / 'cache')
        self.catalog = catalog
        return catalog.describe()

    def _catalog(self):
        if self.catalog is None:
            raise ValueError('Load the extracted benchmark dataset first')
        if self.root.is_relative_to(self.catalog.data) or self.catalog.data.is_relative_to(self.root):
            raise ValueError('Workspace and benchmark data must be separate directories')
        return self.catalog

    def import_adapter(self, path, *, parallel_safe=False, adapter_id=None):
        path = Path(path).expanduser().resolve()
        if not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError('Select an adapter JSON file smaller than 1 MiB')
        definition = load_adapter(path)
        definition['name'] = label(definition['name'], 'Adapter name')
        if type(parallel_safe) is not bool:
            raise ValueError('parallel_safe must be a boolean')
        if adapter_id and adapter_id not in {row['id'] for row in self.store.adapters()}:
            raise ValueError('Adapter not found')
        identifier = self.store.save_adapter(definition, source=str(path), parallel_safe=parallel_safe, adapter_id=adapter_id)
        return {'id': identifier, 'name': definition['name'], 'parallel_safe': parallel_safe}

    def adapter(self, adapter_id):
        for row in self.store.adapters(private=True):
            if row['id'] == adapter_id:
                return row
        raise ValueError('Adapter not found')

    def check_adapter(self, adapter_id):
        value = self.adapter(adapter_id)['definition']
        names = sorted(set(value.get('pass_env', [])) | ({value['credential_env']} if value.get('credential_env') else set()))
        missing = [name for name in names if not os.environ.get(name)]
        executable = Path(value['argv'][0]).is_file()
        return {'valid': executable and not missing, 'executable_available': executable,
                'missing_environment': missing, 'scope': 'configuration', 'model_calls': 0}

    def save_adapter(self, value):
        # Resolve relative arguments against an explicit user directory, not
        # against an ephemeral task HOME. The scratch file contains no env values.
        base = Path(value.get('directory') or Path.cwd()).expanduser().resolve()
        if not base.is_dir():
            raise ValueError('Adapter working directory does not exist')
        definition = value.get('definition')
        if not isinstance(definition, dict):
            raise ValueError('Adapter definition must be an object')
        scratch = self.root / 'cache' / f'adapter-{uuid4().hex}.json'
        converted = dict(definition)
        argv = converted.get('argv')
        if isinstance(argv, list):
            converted['argv'] = [str((base / arg).resolve()) if isinstance(arg, str) and arg and not arg.startswith('-')
                                 and '${PYTHON}' not in arg and not Path(arg).is_absolute() and (base / arg).exists()
                                 else arg for arg in argv]
        try:
            write_json(scratch, converted)
            return self.import_adapter(scratch, parallel_safe=value.get('parallel_safe', False), adapter_id=value.get('id'))
        finally:
            scratch.unlink(missing_ok=True)

    def save(self, request, experiment_id=None, *, append=False):
        catalog = self._catalog()
        adapters = {row['id']: row for row in self.store.adapters(private=True)}
        old = self.store.get(experiment_id)['definition'] if experiment_id else None
        if old and old.get('read_only'):
            raise ValueError('Imported runs are read-only; create a new experiment to evaluate again')
        definition = normalize(request, catalog, adapters, existing=old, immutable=append)
        definition.update(data_identity=bank_identity(catalog.data), runtime_identity=_runtime_identity())
        if experiment_id:
            self.store.update(experiment_id, definition, catalog.rows, append=append)
        else:
            experiment_id = self.store.create(definition, catalog.rows)
        directory = self.directory(experiment_id)
        directory.mkdir(parents=True, exist_ok=True)
        write_json(directory / 'experiment.json', {'id': experiment_id, **definition})
        return self.detail(experiment_id)

    def directory(self, experiment_id):
        # IDs originate in the store; reject arbitrary paths at every entry.
        if not isinstance(experiment_id, str) or len(experiment_id) != 32 or any(c not in '0123456789abcdef' for c in experiment_id):
            raise ValueError('Invalid experiment identifier')
        return _inside(self.root, f'experiments/{experiment_id}')

    @staticmethod
    def _describe(record):
        definition = {**record['definition'], 'groups': [
            {**{key: value for key, value in group.items() if key != 'adapter'},
             'adapter_name': group['adapter']['name']} for group in record['definition']['groups']]}
        return {'id': record['id'], 'status': record['status'], 'created': record['created'],
                'updated': record['updated'], 'definition': definition, 'error': record['error']}

    def detail(self, experiment_id):
        self.reconcile()
        record = self.store.get(experiment_id)
        definition = record['definition']
        directory = Path(definition['source']).resolve() if definition.get('read_only') else self.directory(experiment_id)
        return {**self._describe(record), 'directory': str(directory)}

    def read_directory(self, experiment_id):
        definition = self.store.get(experiment_id)['definition']
        return Path(definition['source']).resolve() if definition.get('read_only') else self.directory(experiment_id)

    def import_run(self, path):
        """Register an inactive CLI run for inspection; never copy its adapter HOME."""
        source = Path(path).expanduser().resolve()
        metadata = source / 'run.json'
        if not metadata.is_file() or metadata.stat().st_size > 4 * 1024 * 1024:
            raise ValueError('Select a saved CLI run directory containing run.json')
        if not (source / '.run.lock').exists():
            raise ValueError('Saved run ownership metadata is missing')
        with _run_lock(source):
            run = read_json(metadata)
            if (run.get('schema') != 'astromembench/run/1' or run.get('benchmark_version') != '1.0.0'
                    or run.get('history_variant') != 'noisy' or run.get('mode') not in {'same_session', 'new_session'}):
                raise ValueError('This directory is not a supported AstroMemBench 1.0.0 CLI run')
            catalog = self._catalog()
            cases = select_cases(catalog.rows, {'case_ids': run['case_ids']})
            if run.get('data_identity') != bank_identity(catalog.data):
                raise ValueError('The saved run uses a different dataset')
            # Bind the immutable definition and creation identity; completion
            # metadata changes on resume. Canonical ordering ignores JSON layout.
            fixed = {key: value for key, value in run.items() if key not in {'status', 'updated_utc'}}
            identity = sha256(json.dumps(fixed, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            with self.store.connect() as db:
                found = db.execute("SELECT id FROM experiments WHERE json_extract(definition,'$.source')=?", (str(source),)).fetchone()
            previous = self.store.get(found['id'])['definition'] if found else None
            if previous and previous.get('source_identity') != identity:
                raise ValueError('Imported run definition changed; choose a new run directory')
            summary = summarize(source)
            group_id = previous['groups'][0]['id'] if previous else uuid4().hex[:12]
            name = label(run['adapter']['name'], 'Adapter name')
            definition = {'schema': 'astromembench/experiment/1', 'benchmark_version': '1.0.0',
                          'name': label(source.name, 'Run name'), 'data': str(catalog.data),
                          'data_identity': run['data_identity'], 'runtime_identity': run['runtime_identity'],
                          'read_only': True, 'source': str(source), 'source_identity': identity, 'total': len(cases), 'concurrency': 1,
                          'groups': [{'id': group_id, 'name': name, 'adapter_id': 'imported', 'adapter': {'name': name},
                                      'parallel_safe': False, 'mode': run['mode'], 'selection': {'case_ids': cases},
                                      'case_ids': cases, 'repetitions': 1}]}
            identifier = found['id'] if found else self.store.create(definition, catalog.rows)
            for row in summary['cases']:
                if row['result_path']:
                    result_path = _inside(source, row['result_path'])
                    self.store.record(identifier, group_id, 1, row['case_id'], result=read_json(result_path),
                                      attempt=row['attempt'], result_path=row['result_path'])
            with self.store.connect(write=True) as db:
                db.execute('UPDATE experiments SET status=? WHERE id=?', (summary['status'], identifier))
                self.store.touch(db, identifier)
        return self.detail(identifier)

    def start(self, experiment_id):
        self.reconcile(force=True)
        record = self.store.get(experiment_id)
        if record['definition'].get('read_only'):
            raise ValueError('Imported runs are read-only; resume them with the original CLI run command')
        if record['definition']['runtime_identity'] != _runtime_identity():
            raise ValueError('The evaluator changed; copy this experiment before starting a new evaluation')
        epoch = self.store.request_start(experiment_id)
        directory = self.directory(experiment_id)
        directory.mkdir(parents=True, exist_ok=True)
        arguments = [sys.executable, '-m', 'astromembench.experiments.worker', '--workspace', str(self.root),
                     '--experiment', experiment_id, '--epoch', epoch]
        options = {'stdin': subprocess.DEVNULL, 'close_fds': True, 'cwd': str(self.root)}
        if os.name == 'nt':
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            options['start_new_session'] = True
        # Also supports running an uninstalled source checkout. Only this
        # package's source root is added; user adapters retain isolated envs.
        env = dict(os.environ)
        package_root = str(Path(__file__).resolve().parents[2])
        env['PYTHONPATH'] = os.pathsep.join(filter(None, [package_root, env.get('PYTHONPATH')]))
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        try:
            with (directory / 'worker.log').open('ab', buffering=0) as log:
                process = subprocess.Popen(arguments, stdout=log, stderr=log, env=env, **options)
            created = psutil.Process(process.pid).create_time()
            with self.store.connect(write=True) as db:
                db.execute('UPDATE experiments SET pid=?,process_time=? WHERE id=? AND epoch=? AND pid IS NULL',
                           (process.pid, created, experiment_id, epoch))
        except psutil.NoSuchProcess:
            # A very early validation failure may finish before the launcher
            # records its PID. Preserve the worker's more useful saved status.
            pass
        except Exception as exc:
            with self.store.connect(write=True) as db:
                db.execute("UPDATE experiments SET status='failed',error=? WHERE id=? AND epoch=?", (str(exc), experiment_id, epoch))
                self.store.touch(db, experiment_id)
            raise
        return self.snapshot(experiment_id)

    def reconcile(self, *, force=False):
        if not force and time.monotonic() - self._last_reconcile < 2:
            return
        self._last_reconcile = time.monotonic()
        with self.store.connect() as db:
            candidates = [dict(row) for row in db.execute("SELECT id,status,pid,process_time,heartbeat,epoch FROM experiments WHERE status IN ('starting','running','pausing','stopping')")]
        for row in candidates:
            if _alive(row['pid'], row['process_time']):
                continue
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(row['heartbeat'])).total_seconds() if row['heartbeat'] else 0
            if not row['pid'] and age < 20:
                continue
            self.store.worker_exited(row)

    def snapshot(self, experiment_id, since=None):
        self.reconcile()
        record = self.store.state(experiment_id)
        with self.store.connect() as db:
            active = [dict(row) for row in db.execute("SELECT group_id,repetition,case_id,result_path FROM results WHERE experiment_id=? AND status='running' LIMIT 8", (experiment_id,))]
        signatures = []
        for row in active:
            path = _inside(self.directory(experiment_id), row.pop('result_path') or '').with_name('runtime.json')
            try:
                signatures.append(json_signature(path))
                row['runtime'] = read_json(path) if path.stat().st_size < 128 * 1024 else None
            except (OSError, ValueError):
                signatures.append(None)
                row['runtime'] = None
        revision = f'{self.instance}:{record["revision"]}:' + sha256(json_text(signatures).encode()).hexdigest()[:12]
        if since == revision:
            return {'revision': revision, 'unchanged': True}
        stats = self.store.statistics(experiment_id)
        return {'id': experiment_id, 'revision': revision, 'record_revision': record['revision'],
                'status': record['status'], 'error': record['error'],
                'summary': stats['overall'], 'groups': stats['items'], 'active': active}

    def control(self, experiment_id, action):
        self.store.control(experiment_id, action)
        return self.snapshot(experiment_id)

    def result_detail(self, experiment_id, group_id, repetition, case_id, *, attempt=None):
        row = self.store.result(experiment_id, group_id, repetition, case_id)
        result_path = row['result_path']
        if not result_path:
            return {'row': row, 'result': None, 'attempts': []}
        root = self.read_directory(experiment_id)
        path = _inside(root, result_path)
        attempts_root = path.parent.parent
        attempts = [int(item.name) for item in attempts_root.iterdir() if item.is_dir() and len(item.name) == 4 and item.name.isdecimal()]
        if attempt is not None:
            integer(attempt, 'Attempt', 1, 9999)
            if attempt not in attempts:
                raise ValueError('Attempt not found')
            path = _inside(root, str(attempts_root / f'{attempt:04d}' / 'result.json'))
        result = read_json(path) if path.is_file() else None
        return {'row': row, 'result': result, 'attempts': sorted(attempts), 'attempt': int(path.parent.name)}

    def events(self, experiment_id, group_id, repetition, case_id, *, attempt=None, cursor=0, limit=20):
        integer(cursor, 'Event cursor', 0, 2**53 - 1)
        integer(limit, 'Event page size', 1, 50)
        row = self.store.result(experiment_id, group_id, repetition, case_id)
        if not row['result_path']:
            return {'items': [], 'next_cursor': cursor, 'has_more': False}
        root = self.read_directory(experiment_id)
        path = _inside(root, row['result_path'])
        if attempt is not None:
            integer(attempt, 'Attempt', 1, 9999)
            path = _inside(root, str(path.parent.parent / f'{attempt:04d}' / 'result.json'))
        path = path.with_name('events.jsonl')
        if not path.exists():
            return {'items': [], 'next_cursor': cursor, 'has_more': False}
        size = path.stat().st_size
        if cursor > size:
            raise ValueError('Event cursor is past the end of the trace')
        active = (row['status'] == 'running' and (attempt is None or attempt == row['attempt'])
                  and self.store.state(experiment_id)['status'] in ACTIVE)
        items, consumed, waiting = [], 0, False
        with path.open('rb') as stream:
            if cursor:
                stream.seek(cursor - 1)
                if stream.read(1) != b'\n':
                    raise ValueError('Event cursor must point to a complete record boundary')
            stream.seek(cursor)
            while len(items) < limit and consumed < 512 * 1024:
                start = stream.tell()
                line = stream.readline(512 * 1024 + 1)
                if not line:
                    break
                if not line.endswith(b'\n'):
                    if len(line) > 512 * 1024:
                        # Skip one oversized payload using bounded memory. The
                        # original trace stays available in the experiment folder.
                        while line and not line.endswith(b'\n'):
                            line = stream.readline(64 * 1024)
                        if line.endswith(b'\n'):
                            items.append({'event': 'large_record', 'bytes': stream.tell() - start,
                                          'message': 'Open events.jsonl in the experiment folder for this payload.'})
                            cursor = stream.tell()
                            break
                    if active:
                        waiting = True
                    else:
                        items.append({'event': 'truncated_record', 'bytes': stream.tell() - start,
                                      'message': 'The attempt ended with an incomplete trace record.'})
                        cursor = stream.tell()
                    break
                if consumed + len(line) > 512 * 1024 and items:
                    break
                try:
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError('Trace records must be objects')
                except (ValueError, UnicodeError):
                    value = {'event': 'invalid_record', 'bytes': len(line),
                             'message': 'This trace record is damaged; the original file has been preserved.'}
                items.append(value)
                consumed += len(line)
                cursor = stream.tell()
        return {'items': items, 'next_cursor': cursor, 'has_more': cursor < size and not waiting,
                'waiting_for_complete_record': waiting}

    def compare(self, left_experiment, left_group, right_experiment, right_group):
        left, right = self.store.get(left_experiment)['definition'], self.store.get(right_experiment)['definition']
        a = next((g for g in left['groups'] if g['id'] == left_group), None)
        b = next((g for g in right['groups'] if g['id'] == right_group), None)
        if a is None or b is None:
            raise ValueError('Comparison group not found')
        reasons = []
        for key in ('data_identity', 'runtime_identity'):
            if left.get(key) != right.get(key):
                reasons.append(f'Different {key}')
        if set(a['case_ids']) != set(b['case_ids']) or a['repetitions'] != b['repetitions']:
            reasons.append('Groups must select the same cases and repetition count')
        if reasons:
            return {'comparable': False, 'reasons': reasons}
        with self.store.connect() as db:
            paired = dict(db.execute('''SELECT count(*) AS paired, avg(b.score-a.score) AS mean_difference,
                sum(b.score>a.score) AS right_wins, sum(b.score<a.score) AS left_wins, sum(b.score=a.score) AS ties
                FROM results a JOIN results b ON a.case_id=b.case_id AND a.repetition=b.repetition
                WHERE a.experiment_id=? AND a.group_id=? AND b.experiment_id=? AND b.group_id=?
                  AND a.score IS NOT NULL AND b.score IS NOT NULL''',
                (left_experiment, left_group, right_experiment, right_group)).fetchone())
        total = len(a['case_ids']) * a['repetitions']
        return {'comparable': True, 'direction': 'right_minus_left', 'total': total, **paired,
                'paired_coverage': paired['paired'] / total, 'left': self.store.statistics(left_experiment, group_id=left_group)['overall'],
                'right': self.store.statistics(right_experiment, group_id=right_group)['overall']}

    def export(self, experiment_id, format='json'):
        """Export one snapshot, excluding configuration and raw diagnostics."""
        if format not in {'json', 'csv'}:
            raise ValueError('Export format must be json or csv')
        self.reconcile()
        snapshot = self.store.export_snapshot(experiment_id)
        record = self._describe(snapshot['experiment'])
        del record['error']
        record['definition'].pop('data', None)
        record['definition'].pop('source', None)
        rows = snapshot['results']
        if format == 'json':
            return json_text({'schema': 'astromembench/export/1', 'experiment': record,
                              'statistics': snapshot['statistics'], 'results': rows}).encode('utf-8'), 'application/json'
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, fieldnames=list(rows[0]) if rows else ['case_id'])
        writer.writeheader()
        for row in rows:
            # Keep text literal when opened in spreadsheet software.
            writer.writerow({k: "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v
                             for k, v in row.items()})
        return ('\ufeff' + output.getvalue()).encode('utf-8'), 'text/csv; charset=utf-8'
