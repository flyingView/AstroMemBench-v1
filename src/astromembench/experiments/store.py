"""Transactional experiment state and indexed, bounded result projections.

Attempt files remain the authoritative scientific record. SQLite contains only
the small fields needed by lists and charts, never prompts or image payloads.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from ..catalog import integer
from ..evaluation import utcnow
from ..metadata import TEMPLATE_SPECS
from ..schema import json_text

ACTIVE = {'starting', 'running', 'pausing', 'stopping'}
AXES = {'group_id', 'template', 'difficulty', 'challenge', 'subchallenge', 'craft', 'mission'}
TOTAL_FIELDS = ('scored', 'score_total', 'full_credit_count', 'unsupported', 'pending', 'running',
                'interrupted', 'failed', 'elapsed_count', 'elapsed_total')


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / 'workbench.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('BEGIN IMMEDIATE')
            initialize_totals = not db.execute("SELECT 1 FROM sqlite_master WHERE name='group_totals'").fetchone()
            schema = '''
                CREATE TABLE IF NOT EXISTS adapters (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, definition TEXT NOT NULL,
                    parallel_safe INTEGER NOT NULL, source TEXT, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, definition TEXT NOT NULL,
                    created TEXT NOT NULL, updated TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
                    desired TEXT NOT NULL DEFAULT 'pause', epoch TEXT, pid INTEGER, process_time REAL,
                    heartbeat TEXT, revision INTEGER NOT NULL DEFAULT 0, error TEXT);
                CREATE TABLE IF NOT EXISTS results (
                    experiment_id TEXT NOT NULL REFERENCES experiments(id), group_id TEXT NOT NULL,
                    repetition INTEGER NOT NULL, case_id TEXT NOT NULL, template TEXT NOT NULL,
                    difficulty TEXT NOT NULL, challenge TEXT, subchallenge TEXT, craft TEXT, mission TEXT,
                    status TEXT NOT NULL DEFAULT 'pending', score REAL,
                    full_credit INTEGER NOT NULL DEFAULT 0, elapsed_s REAL, stages TEXT, usage TEXT,
                    error TEXT, attempt INTEGER, result_path TEXT,
                    PRIMARY KEY (experiment_id, group_id, repetition, case_id));
                CREATE INDEX IF NOT EXISTS results_status ON results(experiment_id, status, group_id);
                CREATE INDEX IF NOT EXISTS results_template ON results(experiment_id, template, difficulty);
                CREATE INDEX IF NOT EXISTS results_analytics ON results(experiment_id,challenge,group_id,
                    status,score,full_credit,elapsed_s,template,difficulty,subchallenge,craft,mission);
                CREATE INDEX IF NOT EXISTS experiments_recent ON experiments(updated DESC,id);
                CREATE INDEX IF NOT EXISTS experiments_name ON experiments(name);
                CREATE INDEX IF NOT EXISTS experiments_status ON experiments(status);
                CREATE TABLE IF NOT EXISTS group_totals (
                    experiment_id TEXT NOT NULL, group_id TEXT NOT NULL,
                    total INTEGER NOT NULL DEFAULT 0, scored INTEGER NOT NULL DEFAULT 0,
                    score_total REAL NOT NULL DEFAULT 0, full_credit_count INTEGER NOT NULL DEFAULT 0,
                    unsupported INTEGER NOT NULL DEFAULT 0, pending INTEGER NOT NULL DEFAULT 0,
                    running INTEGER NOT NULL DEFAULT 0, interrupted INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0, elapsed_count INTEGER NOT NULL DEFAULT 0,
                    elapsed_total REAL NOT NULL DEFAULT 0, PRIMARY KEY(experiment_id,group_id));
            '''
            for statement in schema.split(';'):
                if statement.strip():
                    db.execute(statement)
            if initialize_totals:
                self.rebuild_totals(db)

    @contextmanager
    def connect(self, *, write=False):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def touch(db, experiment_id):
        db.execute('UPDATE experiments SET revision=revision+1, updated=? WHERE id=?', (utcnow(), experiment_id))

    @staticmethod
    def rebuild_totals(db, experiment_id=None):
        """Repair projections after bulk recovery; ordinary events use deltas."""
        if experiment_id is not None:
            db.execute('DELETE FROM group_totals WHERE experiment_id=?', (experiment_id,))
        where, args = ('WHERE experiment_id=?', [experiment_id]) if experiment_id else ('', [])
        db.execute(f'''INSERT OR IGNORE INTO group_totals SELECT experiment_id,group_id,count(*),count(score),
            coalesce(sum(score),0),sum(full_credit),sum(status='unsupported'),sum(status='pending'),sum(status='running'),
            sum(status='interrupted'),sum(score IS NULL AND status NOT IN ('pending','running','unsupported','interrupted')),
            count(elapsed_s),coalesce(sum(elapsed_s),0) FROM results {where} GROUP BY experiment_id,group_id''', args)

    @staticmethod
    def _contribution(row):
        status, score, elapsed = row['status'], row['score'], row['elapsed_s']
        return (int(score is not None), score or 0, row['full_credit'], int(status == 'unsupported'), int(status == 'pending'),
                int(status == 'running'), int(status == 'interrupted'),
                int(score is None and status not in {'pending', 'running', 'unsupported', 'interrupted'}),
                int(elapsed is not None), elapsed or 0)

    @staticmethod
    def _public_total(row):
        value = dict(row)
        score = value.pop('score_total')
        value['mean_score'] = score / value['scored'] if value['scored'] else None
        count, elapsed = value.pop('elapsed_count'), value.pop('elapsed_total')
        value['mean_elapsed_s'] = elapsed / count if count else None
        value['finished'] = value['scored'] + value['unsupported']
        value['coverage'] = value['scored'] / value['total'] if value['total'] else 0
        value.pop('experiment_id', None)
        if 'group_id' in value:
            value['label'] = value.pop('group_id')
        return value

    def adapters(self, *, private=False):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM adapters ORDER BY name, id')]
        for row in rows:
            row['parallel_safe'] = bool(row['parallel_safe'])
            if private:
                row['definition'] = json.loads(row['definition'])
            else:
                del row['definition']
                row.pop('source', None)
        return rows

    def save_adapter(self, definition, *, source=None, parallel_safe=False, adapter_id=None):
        adapter_id = adapter_id or uuid4().hex
        with self.connect(write=True) as db:
            db.execute('''INSERT INTO adapters VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, definition=excluded.definition, parallel_safe=excluded.parallel_safe,
                source=excluded.source, updated=excluded.updated''',
                (adapter_id, definition['name'], json_text(definition), int(parallel_safe), source, utcnow()))
        return adapter_id

    @staticmethod
    def seed(db, experiment_id, definition, rows):
        by_id = {row['case_id']: row for row in rows}
        values = []
        for group in definition['groups']:
            for repetition in range(1, group['repetitions'] + 1):
                for case_id in group['case_ids']:
                    row = by_id[case_id]
                    spec = TEMPLATE_SPECS[row['template']]
                    values.append((experiment_id, group['id'], repetition, case_id, row['template'], row['difficulty'],
                                   spec.challenge, spec.subchallenge, spec.craft, spec.mission))
        db.executemany('''INSERT OR IGNORE INTO results
            (experiment_id,group_id,repetition,case_id,template,difficulty,challenge,subchallenge,craft,mission)
            VALUES (?,?,?,?,?,?,?,?,?,?)''', values)
        db.executemany('INSERT OR IGNORE INTO group_totals (experiment_id,group_id,total,pending) VALUES (?,?,?,?)',
            [(experiment_id, group['id'], len(group['case_ids']) * group['repetitions'],
              len(group['case_ids']) * group['repetitions']) for group in definition['groups']])

    def create(self, definition, rows):
        experiment_id, now = uuid4().hex, utcnow()
        with self.connect(write=True) as db:
            db.execute('INSERT INTO experiments (id,name,definition,created,updated) VALUES (?,?,?,?,?)',
                       (experiment_id, definition['name'], json_text(definition), now, now))
            self.seed(db, experiment_id, definition, rows)
        return experiment_id

    def get(self, experiment_id):
        with self.connect() as db:
            return self._get(db, experiment_id)

    @staticmethod
    def _get(db, experiment_id):
        row = db.execute('SELECT * FROM experiments WHERE id=?', (experiment_id,)).fetchone()
        if row is None:
            raise ValueError('Experiment not found')
        value = dict(row)
        value['definition'] = json.loads(value['definition'])
        return value

    def state(self, experiment_id):
        with self.connect() as db:
            row = db.execute('SELECT id,status,desired,epoch,pid,process_time,heartbeat,revision,error FROM experiments WHERE id=?',
                             (experiment_id,)).fetchone()
        if row is None:
            raise ValueError('Experiment not found')
        return dict(row)

    def list(self, *, offset=0, limit=30, search=''):
        integer(offset, 'Offset', 0, 100000)
        integer(limit, 'Page size', 1, 100)
        # instr treats percent/underscore literally, unlike LIKE.
        where, arguments = ('WHERE instr(lower(name),lower(?))', [search]) if search else ('', [])
        with self.connect() as db:
            count = db.execute(f'SELECT count(*) FROM experiments {where}', arguments).fetchone()[0]
            rows = [dict(row) for row in db.execute(f'''SELECT id,name,created,updated,status,revision,error,
                (SELECT sum(total) FROM group_totals g WHERE g.experiment_id=experiments.id) AS total,
                (SELECT sum(scored+unsupported) FROM group_totals g WHERE g.experiment_id=experiments.id) AS finished
                FROM experiments {where} ORDER BY updated DESC,id LIMIT ? OFFSET ?''',
                [*arguments, limit, offset])]
        return {'total': count, 'offset': offset, 'limit': limit, 'items': rows}

    def update(self, experiment_id, definition, rows, *, append=False):
        with self.connect(write=True) as db:
            current = db.execute('SELECT * FROM experiments WHERE id=?', (experiment_id,)).fetchone()
            if current is None:
                raise ValueError('Experiment not found')
            if current['status'] in ACTIVE or (not append and current['status'] != 'draft'):
                raise RuntimeError('Only drafts can be edited; stop or pause before appending groups')
            if append:
                old = json.loads(current['definition'])
                new_groups = {g['id']: g for g in definition['groups']}
                if any(new_groups.get(g['id']) != g for g in old['groups']):
                    raise ValueError('Existing groups cannot change when appending')
                if any(definition.get(k) != old.get(k) for k in ('data', 'data_identity', 'runtime_identity', 'concurrency')):
                    raise ValueError('An appended experiment must keep its dataset, evaluator and concurrency')
            else:
                db.execute('DELETE FROM results WHERE experiment_id=?', (experiment_id,))
                db.execute('DELETE FROM group_totals WHERE experiment_id=?', (experiment_id,))
            self.seed(db, experiment_id, definition, rows)
            db.execute('UPDATE experiments SET name=?,definition=?,status=? WHERE id=?',
                       (definition['name'], json_text(definition), 'paused' if append else 'draft', experiment_id))
            self.touch(db, experiment_id)

    def request_start(self, experiment_id):
        epoch = uuid4().hex
        with self.connect(write=True) as db:
            row = db.execute('SELECT status,definition FROM experiments WHERE id=?', (experiment_id,)).fetchone()
            if row is None:
                raise ValueError('Experiment not found')
            if row['status'] in ACTIVE:
                raise RuntimeError('This experiment already has an active worker')
            definition = json.loads(row['definition'])
            active = [json.loads(item[0]) for item in db.execute("SELECT definition FROM experiments WHERE status IN ('starting','running','pausing','stopping')")]
            if sum(item['concurrency'] for item in active) + definition['concurrency'] > 8:
                raise RuntimeError('This workspace allows at most eight active evaluation lanes; pause another experiment first')
            for group in definition['groups']:
                for other in (group for item in active for group in item['groups']):
                    if (group['adapter']['argv'] == other['adapter']['argv']
                            and not (group['parallel_safe'] and other['parallel_safe'])):
                        raise RuntimeError('This adapter is already in use; isolated external state is required for parallel experiments')
            db.execute("UPDATE experiments SET status='starting',desired='run',epoch=?,pid=NULL,process_time=NULL,error=NULL,heartbeat=? WHERE id=?",
                       (epoch, utcnow(), experiment_id))
            self.touch(db, experiment_id)
        return epoch

    def control(self, experiment_id, action):
        if action not in {'pause', 'stop'}:
            raise ValueError('Unknown worker command')
        with self.connect(write=True) as db:
            row = db.execute('SELECT status,desired FROM experiments WHERE id=?', (experiment_id,)).fetchone()
            if row is None:
                raise ValueError('Experiment not found')
            if row['status'] in ACTIVE and not (action == 'pause' and row['desired'] == 'stop'):
                db.execute('UPDATE experiments SET desired=?,status=? WHERE id=?',
                           (action, 'pausing' if action == 'pause' else 'stopping', experiment_id))
                self.touch(db, experiment_id)

    @staticmethod
    def _interrupt_running(db, experiment_id):
        groups = db.execute("SELECT group_id,count(*) FROM results WHERE experiment_id=? AND status='running' GROUP BY group_id",
                            (experiment_id,)).fetchall()
        db.execute("UPDATE results SET status='interrupted' WHERE experiment_id=? AND status='running'", (experiment_id,))
        db.executemany('UPDATE group_totals SET running=running-?,interrupted=interrupted+? WHERE experiment_id=? AND group_id=?',
                       [(count, count, experiment_id, group) for group, count in groups])

    def claim_worker(self, experiment_id, epoch, pid, created):
        with self.connect(write=True) as db:
            changed = db.execute("""UPDATE experiments SET status=CASE desired WHEN 'run' THEN 'running'
                WHEN 'stop' THEN 'stopping' ELSE 'pausing' END, pid=?,process_time=?,heartbeat=? WHERE id=? AND epoch=?""",
                (pid, created, utcnow(), experiment_id, epoch)).rowcount
            if changed:
                self._interrupt_running(db, experiment_id)
                self.touch(db, experiment_id)
            return bool(changed)

    def worker_exited(self, observed):
        """A liveness observation may only retire the exact owner it observed."""
        with self.connect(write=True) as db:
            changed = db.execute("""UPDATE experiments SET status='interrupted',desired='pause',error=?
                WHERE id=? AND epoch=? AND status IN ('starting','running','pausing','stopping')
                AND pid IS ? AND process_time IS ? AND heartbeat IS ?""",
                ('Worker exited. Resume to recover saved results and retry unfinished cases.', observed['id'], observed['epoch'],
                 observed['pid'], observed['process_time'], observed['heartbeat'])).rowcount
            if changed:
                self._interrupt_running(db, observed['id'])
                self.touch(db, observed['id'])

    def finish_worker(self, experiment_id, epoch, *, error=None):
        """Publish completion after releasing the worker lock, using current intent."""
        with self.connect(write=True) as db:
            state = db.execute('SELECT desired FROM experiments WHERE id=? AND epoch=?', (experiment_id, epoch)).fetchone()
            if state is None:
                return
            self._interrupt_running(db, experiment_id)
            total, finished = db.execute('SELECT sum(total),sum(scored+unsupported) FROM group_totals WHERE experiment_id=?',
                                        (experiment_id,)).fetchone()
            status = ('failed' if error else 'completed' if total == finished else
                      'stopped' if state['desired'] == 'stop' else 'paused' if state['desired'] == 'pause' else 'incomplete')
            db.execute('UPDATE experiments SET status=?,error=?,heartbeat=? WHERE id=? AND epoch=?',
                       (status, error, utcnow(), experiment_id, epoch))
            self.touch(db, experiment_id)

    def record(self, experiment_id, group_id, repetition, case_id, *, result=None, attempt=None, result_path=None):
        status = result.get('status', 'infrastructure_error') if result else 'running'
        outcome = result.get('outcome') or {} if result else {}
        timing = (result or {}).get('timing', {})
        stages = {name: value.get('elapsed_s') for name, value in timing.get('stages', {}).items()}
        with self.connect(write=True) as db:
            identity = (experiment_id, group_id, repetition, case_id)
            previous = db.execute('SELECT status,score,full_credit,elapsed_s FROM results WHERE experiment_id=? AND group_id=? AND repetition=? AND case_id=?', identity).fetchone()
            if previous is None:
                raise ValueError('Result identity is not part of this experiment')
            if previous['score'] is not None or previous['status'] == 'unsupported':
                return
            db.execute('''UPDATE results SET status=?,score=?,full_credit=?,elapsed_s=?,stages=?,usage=?,error=?,attempt=?,result_path=?
                WHERE experiment_id=? AND group_id=? AND repetition=? AND case_id=? ''',
                (status, outcome.get('score'), int(outcome.get('full_credit') is True), (result or {}).get('elapsed_s'),
                 json_text(stages), json_text((result or {}).get('usage')), str((result or {}).get('error') or '')[:2000] or None,
                 attempt, result_path, experiment_id, group_id, repetition, case_id))
            updated = {'status': status, 'score': outcome.get('score'), 'full_credit': int(outcome.get('full_credit') is True),
                       'elapsed_s': (result or {}).get('elapsed_s')}
            delta = [new - old for new, old in zip(self._contribution(updated), self._contribution(previous), strict=True)]
            db.execute('UPDATE group_totals SET ' + ','.join(f'{field}={field}+?' for field in TOTAL_FIELDS)
                       + ' WHERE experiment_id=? AND group_id=?', [*delta, experiment_id, group_id])
            self.touch(db, experiment_id)

    @staticmethod
    def filters(experiment_id, filters):
        clauses, arguments = ['experiment_id=?'], [experiment_id]
        for name in ('group_id', 'status', 'template', 'difficulty', 'challenge', 'subchallenge', 'craft', 'mission'):
            if filters.get(name):
                clauses.append(f'{name}=?')
                arguments.append(filters[name])
        if filters.get('search'):
            clauses.append('instr(lower(case_id),lower(?))')
            arguments.append(filters['search'])
        return ' AND '.join(clauses), arguments

    def results(self, experiment_id, *, offset=0, limit=50, **filters):
        integer(offset, 'Offset', 0, 100000)
        integer(limit, 'Page size', 1, 100)
        where, arguments = self.filters(experiment_id, filters)
        with self.connect() as db:
            total = db.execute(f'SELECT count(*) FROM results WHERE {where}', arguments).fetchone()[0]
            rows = [dict(row) for row in db.execute(f'''SELECT group_id,repetition,case_id,template,difficulty,
                status,score,full_credit,elapsed_s,error,attempt FROM results WHERE {where}
                ORDER BY group_id,repetition,case_id LIMIT ? OFFSET ?''', [*arguments, limit, offset])]
        return {'total': total, 'offset': offset, 'limit': limit, 'items': rows}

    def statistics(self, experiment_id, *, axis='group_id', **filters):
        with self.connect() as db:
            return self._statistics(db, experiment_id, axis=axis, **filters)

    def _statistics(self, db, experiment_id, *, axis='group_id', **filters):
        if axis not in AXES | {'capability'}:
            raise ValueError('Unknown breakdown axis')
        if axis == 'group_id' and not any(value for key, value in filters.items() if key != 'group_id'):
            groups = [dict(row) for row in db.execute('SELECT * FROM group_totals WHERE experiment_id=?'
                + (' AND group_id=?' if filters.get('group_id') else '') + ' ORDER BY group_id',
                [experiment_id, *([filters['group_id']] if filters.get('group_id') else [])])]
            totals = {field: sum(row[field] for row in groups) for field in ('total', *TOTAL_FIELDS)}
            return {'overall': self._public_total(totals), 'axis': axis, 'items': [self._public_total(row) for row in groups]}
        where, arguments = self.filters(experiment_id, filters)
        columns = """count(*) AS total, count(score) AS scored, coalesce(sum(score),0) AS score_total,
            coalesce(sum(full_credit),0) AS full_credit_count, coalesce(sum(status='unsupported'),0) AS unsupported,
            coalesce(sum(status='pending'),0) AS pending, coalesce(sum(status='running'),0) AS running,
            coalesce(sum(status='interrupted'),0) AS interrupted,
            coalesce(sum(score IS NULL AND status NOT IN ('pending','running','unsupported','interrupted')),0) AS failed,
            count(elapsed_s) AS elapsed_count, coalesce(sum(elapsed_s),0) AS elapsed_total"""
        group = 'template' if axis == 'capability' else axis
        rows = [dict(row) for row in db.execute(f'SELECT {group} AS label, {columns} FROM results WHERE {where} GROUP BY {group} ORDER BY {group}', arguments)]
        fields = ('total', *TOTAL_FIELDS)
        overall = {field: sum(row[field] for row in rows) for field in fields}
        if axis == 'capability':
            # Capability membership belongs to the fixed template catalog.
            # Aggregate at most 140 templates, then fan out their small totals;
            # do not decode identical capability JSON for every repetition.
            capabilities = {}
            for row in rows:
                for capability in TEMPLATE_SPECS[row['label']].capabilities:
                    totals = capabilities.setdefault(capability, {'label': capability, **dict.fromkeys(fields, 0)})
                    for field in fields:
                        totals[field] += row[field]
            rows = [capabilities[key] for key in sorted(capabilities)]
        return {'overall': self._public_total(overall), 'axis': axis, 'items': [self._public_total(row) for row in rows]}

    def export_snapshot(self, experiment_id):
        """Read metadata, result rows and totals at one committed WAL revision."""
        with self.connect() as db:
            db.execute('BEGIN')
            record = self._get(db, experiment_id)
            rows = [dict(row) for row in db.execute('''SELECT group_id,repetition,case_id,template,difficulty,challenge,
                subchallenge,craft,mission,status,score,full_credit,elapsed_s,attempt
                FROM results WHERE experiment_id=? ORDER BY group_id,repetition,case_id''', (experiment_id,))]
            statistics = self._statistics(db, experiment_id)
        return {'experiment': record, 'results': rows, 'statistics': statistics}

    def result(self, experiment_id, group_id, repetition, case_id):
        with self.connect() as db:
            row = db.execute('SELECT * FROM results WHERE experiment_id=? AND group_id=? AND repetition=? AND case_id=?',
                             (experiment_id, group_id, repetition, case_id)).fetchone()
        if row is None:
            raise ValueError('Result not found')
        return dict(row)

    def measurements(self, experiment_id, **filters):
        where, arguments = self.filters(experiment_id, filters)
        with self.connect() as db:
            stages = [dict(row) for row in db.execute(f'''SELECT stage.key AS stage, count(stage.value) AS measured,
                avg(stage.value) AS mean_s, sum(stage.value) AS total_s FROM results, json_each(results.stages) stage
                WHERE {where} AND stage.value IS NOT NULL GROUP BY stage.key''', arguments)]
            usage = [dict(row) for row in db.execute(f'''SELECT metric.key AS metric, count(metric.value) AS reported_cases,
                sum(metric.value) AS reported_total FROM results, json_each(results.usage,'$.totals') metric
                WHERE {where} GROUP BY metric.key''', arguments)]
            total = db.execute(f'SELECT count(*) FROM results WHERE {where}', arguments).fetchone()[0]
        return {'total': total, 'stages': stages, 'usage': usage, 'usage_source': 'adapter_reported_deltas'}
