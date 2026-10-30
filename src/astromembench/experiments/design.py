"""Validated, reproducible experiment definitions."""
from copy import deepcopy
from uuid import uuid4

from ..catalog import integer, select_cases

MAX_INSTANCES = 100000
MODES = {'same_session', 'new_session'}


def label(value, name):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 160:
        raise ValueError(f'{name} must contain 1–160 characters')
    return value.strip()


def normalize(request, catalog, adapters, *, existing=None, immutable=False):
    if not isinstance(request, dict):
        raise ValueError('An experiment must be an object')
    groups = request.get('groups')
    if not isinstance(groups, list) or not 1 <= len(groups) <= 64:
        raise ValueError('An experiment requires 1–64 groups')
    concurrency = integer(request.get('concurrency', 1), 'Group concurrency', 1, 8)
    normalized, seen, identifiers = [], set(), set()
    previous = {group['id']: group for group in (existing or {}).get('groups', [])}
    for raw in groups:
        if not isinstance(raw, dict):
            raise ValueError('Each group must be an object')
        name = label(raw.get('name'), 'Group name')
        if name.casefold() in seen:
            raise ValueError('Group names must be distinct')
        seen.add(name.casefold())
        mode = raw.get('mode', 'same_session')
        if mode not in MODES:
            raise ValueError('Unknown session mode')
        adapter_id = raw.get('adapter_id')
        if not isinstance(adapter_id, str) or adapter_id not in adapters:
            raise ValueError(f'Choose a saved adapter for {name}')
        old = previous.get(raw.get('id'))
        adapter = ({'definition': old['adapter'], 'parallel_safe': old['parallel_safe']}
                   if old and adapter_id == old['adapter_id'] else adapters[adapter_id])
        if concurrency > 1 and not adapter.get('parallel_safe', False):
            raise ValueError(f'{name}: parallel runs require an adapter with isolated remote state')
        selection = deepcopy(raw.get('selection', {}))
        cases = select_cases(catalog.rows, selection)
        repetitions = integer(raw.get('repetitions', 1), 'Repetitions', 1, 100)
        group = {'id': old['id'] if old else uuid4().hex[:12], 'name': name,
                 'adapter_id': adapter_id, 'adapter': deepcopy(adapter['definition']),
                 'parallel_safe': adapter.get('parallel_safe', False), 'mode': mode,
                 'selection': selection, 'case_ids': cases, 'repetitions': repetitions}
        if group['id'] in identifiers:
            raise ValueError('Group identifiers must be distinct')
        identifiers.add(group['id'])
        if old and immutable and group != old:
            raise ValueError('Started groups are immutable; copy the experiment to change them')
        normalized.append(group)
    total = sum(len(group['case_ids']) * group['repetitions'] for group in normalized)
    if total > MAX_INSTANCES:
        raise ValueError(f'An experiment may contain at most {MAX_INSTANCES:,} case instances')
    return {'schema': 'astromembench/experiment/1', 'benchmark_version': '1.0.0',
            'name': label(request.get('name'), 'Experiment name'), 'data': str(catalog.data),
            'concurrency': concurrency, 'groups': normalized, 'total': total}
