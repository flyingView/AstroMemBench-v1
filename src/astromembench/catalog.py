"""Small catalog queries and lazy reads of the fixed dataset; no HTTP dependency."""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock

from .benchmark import load_index, validate_bank, bank_identity, _safe_path
from .metadata import TEMPLATE_SPECS, coverage_targets
from .persistence import read_json, write_json, json_signature
from .schema import Task


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer from {minimum} to {maximum}')
    return value


def select_cases(rows, selection):
    """Resolve one selection contract for CLI, HTTP and saved experiments.

    Explicit IDs must satisfy any supplied filters. A limit samples templates
    round-robin, deterministically, before restoring published dataset order.
    """
    if not isinstance(selection, dict) or set(selection) - {'case_ids', 'templates', 'difficulties', 'limit'}:
        raise ValueError('Unknown case selection field')
    known = {row['case_id'] for row in rows}
    filters = {}
    for key, column in (('case_ids', 'case_id'), ('templates', 'template'), ('difficulties', 'difficulty')):
        values = selection.get(key, [])
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values) or len(values) != len(set(values)):
            raise ValueError(f'{key} must contain distinct strings')
        available = {row[column] for row in rows}
        if set(values) - available:
            raise ValueError(f'Unknown {key}: ' + ', '.join(sorted(set(values) - available)))
        filters[column] = set(values)
    candidates = [row for row in rows if all(not values or row[column] in values for column, values in filters.items())]
    if filters['case_id'] - {row['case_id'] for row in candidates}:
        raise ValueError('Explicit case IDs conflict with the selected filters')
    limit = selection.get('limit')
    if limit is not None:
        integer(limit, 'Case limit', 1, len(known))
        buckets = defaultdict(list)
        for row in candidates:
            buckets[row['template']].append(row['case_id'])
        ordered = list(buckets.values())
        sampled = [bucket[i] for i in range(max(map(len, ordered), default=0)) for bucket in ordered if i < len(bucket)][:limit]
        wanted = set(sampled)
        candidates = [row for row in candidates if row['case_id'] in wanted]
    if not candidates:
        raise ValueError('The selection contains no cases')
    return [row['case_id'] for row in candidates]


class Catalog:
    def __init__(self, data, cache=None):
        self.data = Path(data).expanduser().resolve()
        self.index = load_index(self.data)
        self.rows = self.index['cases']
        self.by_id = {row['case_id']: row for row in self.rows}
        self.cache = Path(cache) if cache else None
        self._lock = Lock()
        self._offsets = None
        self._signature = None

    def describe(self):
        return {'data': str(self.data), 'version': '1.0.0', 'task_count': len(self.rows),
                'template_count': len(self.index['templates']), 'history_rounds': 30,
                'templates': [{'id': key, **spec.to_dict()} for key, spec in TEMPLATE_SPECS.items()],
                'classification': coverage_targets()}

    def query(self, *, search='', template='', difficulty='', offset=0, limit=50):
        integer(offset, 'Offset', 0, 100000)
        integer(limit, 'Page size', 1, 100)
        search = search.casefold()
        rows = [row for row in self.rows if (not template or row['template'] == template)
                and (not difficulty or row['difficulty'] == difficulty)
                and (not search or search in (row['case_id'] + ' ' + TEMPLATE_SPECS[row['template']].name
                                             + ' ' + TEMPLATE_SPECS[row['template']].english).casefold())]
        return {'total': len(rows), 'offset': offset, 'limit': limit, 'items': rows[offset:offset + limit]}

    def _index_offsets(self):
        source = self.data / 'tasks.jsonl'
        signature = list(json_signature(source))
        with self._lock:
            if self._offsets is not None and signature == self._signature:
                return self._offsets
            key = sha256(str(self.data).encode()).hexdigest()[:24]
            cache = self.cache / f'offsets-{key}.json' if self.cache else None
            if cache and cache.is_file():
                try:
                    saved = read_json(cache)
                    offsets = saved['offsets']
                    if (saved['signature'] == signature and len(offsets) == len(self.rows)
                            and all(type(n) is int and 0 <= n < signature[2] for n in offsets)
                            and offsets == sorted(set(offsets))):
                        self._signature, self._offsets = signature, offsets
                        return offsets
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            offsets = []
            with source.open('rb') as stream:
                while True:
                    position = stream.tell()
                    line = stream.readline()
                    if not line:
                        break
                    if line.strip():
                        offsets.append(position)
            if len(offsets) != len(self.rows) or list(json_signature(source)) != signature:
                raise ValueError('Dataset changed or differs from its index; validate the dataset')
            self._signature, self._offsets = signature, offsets
            if cache:
                write_json(cache, {'signature': signature, 'offsets': offsets})
            return offsets

    def tasks(self, case_ids):
        wanted = set(case_ids)
        if not wanted:
            return
        if wanted - self.by_id.keys():
            raise ValueError('Unknown case identifier')
        offsets = self._index_offsets()
        with (self.data / 'tasks.jsonl').open('rb') as stream:
            for i, row in enumerate(self.rows):
                if row['case_id'] not in wanted:
                    continue
                stream.seek(offsets[i])
                # A corrupt cache must never change which task is evaluated.
                task = Task.from_dict(json.loads(stream.readline()))
                if (task.case_id, task.template, task.difficulty) != tuple(row[k] for k in ('case_id', 'template', 'difficulty')):
                    self._offsets = None
                    raise ValueError('Task index does not match the dataset; remove the offset cache and validate')
                yield task

    def preview(self, case_id, round_number=None):
        task = next(self.tasks([case_id]))
        if round_number is not None:
            integer(round_number, 'History round', 1, len(task.history))
            return {'case_id': case_id, 'round': round_number, 'input': task.history[round_number - 1].public_input()}
        return {'case_id': case_id, 'template': task.template, 'difficulty': task.difficulty,
                'public': task.public, 'history_rounds': len(task.history),
                'classification': TEMPLATE_SPECS[task.template].to_dict()}

    def asset(self, relative):
        from .benchmark import EXPECTED_ASSETS
        if relative not in EXPECTED_ASSETS:
            raise ValueError('Unknown benchmark image')
        return _safe_path(self.data / 'assets', relative)


class PreparedBank(Catalog):
    """One validated immutable input shared by an experiment's evaluation lanes."""
    def __init__(self, data, cache=None):
        super().__init__(data, cache)
        validate_bank(self.data)
        self.identity = bank_identity(self.data)
        files = read_json(self.data / 'manifest.json')['files']
        self._files = [_safe_path(self.data, name) for name in [*files, 'manifest.json']]
        self._verified = [json_signature(path) for path in self._files]

    def check(self, data):
        if Path(data).resolve() != self.data or self._verified != [json_signature(path) for path in self._files]:
            raise ValueError('Dataset changed after verification; restart the experiment')
