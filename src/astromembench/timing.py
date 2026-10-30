"""One evaluator clock from participant construction to a durable score.

The journal records elapsed intervals, not inferred external blocking. Native
producer clocks have separate domains and are linked only by causal span IDs.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from .schema import json_text
from .usage import STAGES


TIMING_STAGES = ('native_startup', *STAGES)


class StageClock:
    def __init__(self, mode, clock=None, *, path=None, job_id=None, attempt_id=None):
        self.clock = clock or time.monotonic
        self.path = Path(path) if path is not None else None
        self.identity = {'job_id': job_id, 'attempt_id': attempt_id or uuid4().hex,
                         'clock_domain': 'evaluator/' + uuid4().hex, 'clock_segment': uuid4().hex}
        self.sequence = 0
        self.journal_errors = []
        self.stages = {name: {'applicable': name != 'session_boundary' or mode == 'new_session',
                              'started': False, 'complete': False, 'timing_complete': False,
                              'elapsed_s': None, 'raw_s': None} for name in TIMING_STAGES}
        self.active = self.started = self.terminal = None
        self.operations = {}

    def _event(self, event, at, **fields):
        self.sequence += 1
        value = {**self.identity, 'event_id': f'{self.identity["clock_segment"]}/{self.sequence}',
                 'sequence': self.sequence, 'event': event, 'monotonic_s': at,
                 'utc': datetime.now(timezone.utc).isoformat(), **fields}
        try:
            self._append(value)
        except OSError as exc:
            # Observation persistence must never discard an actual decision or
            # turn a scored terminal into a fresh, retryable model attempt.
            self.journal_errors.append({'event_id': value['event_id'], 'event': event, 'error': str(exc)})
            if self.active is not None:
                self.stages[self.active]['journal_complete'] = False
        return value

    def _append(self, value):
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open('a', encoding='utf-8') as stream:
                stream.write(json_text(value) + '\n')

    def start(self, stage, *, at=None):
        if self.active is not None or self.stages[stage]['started'] or not self.stages[stage]['applicable']:
            raise RuntimeError('Observation stages must be applicable and start once, in sequence')
        self.active, self.started = stage, self.clock() if at is None else at
        span = uuid4().hex
        self.stages[stage].update(started=True, start_s=self.started, span_id=span, journal_complete=True)
        self._event('stage_start', self.started, stage=stage, span_id=span, parent_span_id=None)

    def finish(self, *, complete, at=None):
        if self.active is not None:
            end = self.clock() if at is None else at
            value = self.stages[self.active]
            value.update(end_s=end, elapsed_s=end-self.started, raw_s=end-self.started,
                         complete=complete, timing_complete=value['journal_complete'] and not any(
                             op['stage'] == self.active for op in self.operations.values()))
            self._event('stage_end', end, stage=self.active, span_id=value['span_id'],
                        parent_span_id=None, complete=complete, timing_complete=value['timing_complete'])
            value['timing_complete'] &= value['journal_complete']
            self.active = self.started = None

    def transition(self, stage, *, complete, terminal_phase=None):
        at, previous_stage = self.clock(), self.active
        self.finish(complete=complete, at=at)
        if terminal_phase is not None and self.terminal is None:
            event = self._event('scored_terminal', at, stage=previous_stage, phase=terminal_phase,
                                history_complete=self.stages['history']['complete'])
            self.terminal = {key: event[key] for key in
                             ('event_id', 'monotonic_s', 'stage', 'phase', 'history_complete')}
            self.terminal['journal_complete'] = not self.journal_errors
        self.start(stage, at=at)

    def begin_operation(self, operation, operation_id):
        context = {key: self.identity[key] for key in ('job_id', 'attempt_id')}
        context.update(operation_id=operation_id, stage=self.active, span_id=uuid4().hex,
                       parent_span_id=self.stages[self.active]['span_id'])
        self.operations[context['span_id']] = {**context, 'operation': operation}
        self._event('operation_start', self.clock(), **self.operations[context['span_id']])
        return context

    def end_operation(self, context, *, status='completed', failure=None):
        operation = self.operations.pop(context['span_id'])
        self._event('operation_end', self.clock(), **operation, status=status, failure=deepcopy(failure))

    def snapshot(self):
        stages = deepcopy(self.stages)
        if self.active is not None:
            seconds = self.clock()-self.started
            stages[self.active].update(elapsed_s=seconds, raw_s=seconds)
        start, terminal = stages['native_startup'].get('start_s'), self.terminal
        reached = TIMING_STAGES[:TIMING_STAGES.index(terminal['stage'])+1] if terminal else ()
        applicable = [stages[key] for key in reached if stages[key]['applicable']]
        measured = (terminal is not None and start is not None and terminal['journal_complete']
                    and all(value['timing_complete'] for value in applicable))
        completion = {'raw_s': terminal['monotonic_s']-start if terminal is not None and start is not None else None,
                      'timing_complete': measured,
                      'coverage': 'raw_only' if measured else 'partial' if terminal is not None else 'unavailable'}
        return {'schema': 'astromembench/timing/1', 'source': 'evaluator_monotonic', **self.identity,
                'stages': stages, 'terminal': deepcopy(terminal), 'end_to_end': completion,
                'open_spans': list(self.operations), 'journal_complete': not self.journal_errors,
                'journal_errors': deepcopy(self.journal_errors)}
