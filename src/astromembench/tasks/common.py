"""Direct thirty-round history authoring and neutral action presentation."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from random import Random
import json

from ..metadata import TEMPLATE_SPECS
from ..schema import HISTORY_ROUNDS, HistoryEvent, HistoryRecord, Task, story_timestamp, json_text

SEED = 1729
DEFAULT_DAY = 120


def story_time(day=DEFAULT_DAY, hour=8, minute=0, second=0):
    return day * 86400 + hour * 3600 + minute * 60 + second


def clock(text, day=DEFAULT_DAY):
    parts = [int(n) for n in text.split(':')]
    if len(parts) not in (2, 3) or not 0 <= parts[0] < 24 or not 0 <= parts[1] < 60 or (len(parts) == 3 and not 0 <= parts[2] < 60):
        raise ValueError('Expected HH:MM or HH:MM:SS story clock')
    return story_time(day, parts[0], parts[1], parts[2] if len(parts) > 2 else 0)


def difficulty(index):
    if type(index) is not int or not 0 <= index < 16:
        raise ValueError('Instance index must be in 0..15')
    return 'easy' if index < 6 else 'medium' if index < 12 else 'hard'


def round_times(anchors):
    """Native R01–R30 clocks; fill intervening rounds to whole seconds."""
    points = sorted(anchors.items())
    if points[0][0] != 1 or points[-1][0] != HISTORY_ROUNDS:
        raise ValueError('Specify the first and last native round clocks')
    result = [None] * HISTORY_ROUNDS
    for (first, start), (last, end) in zip(points, points[1:]):
        if not 1 <= first < last <= HISTORY_ROUNDS or start > end:
            raise ValueError('Native round clocks must be ordered')
        for at in range(first, last + 1):
            result[at - 1] = start + (end - start) * (at - first) // (last - first)
    return result


def task_shell(template, index, *, group=None, background_group=None, current_input_group=None):
    level = difficulty(index)
    spec = TEMPLATE_SPECS[template]
    identity = f'{template}-{index + 1:03d}'
    design = {'group': group or identity, 'classification': spec.to_dict(),
              'scoring_version': f'{template.lower()}/5',
              'source': f'src/astromembench/tasks/{spec.subchallenge.lower()}/{spec.mission.lower()}.py'}
    if background_group is not None:
        design['background_group'] = background_group
    if current_input_group is not None:
        design['current_input_group'] = current_input_group
    return Task(identity, template, level, [], {}, {}, {}, {}, design)


class History:
    """Write R01–R30 directly, preserving explicit record occurrence/reception."""
    def __init__(self, *, times=None):
        times = list(times) if times is not None else [story_time(minute=r, second=59) for r in range(1, HISTORY_ROUNDS + 1)]
        if len(times) != HISTORY_ROUNDS or times != sorted(times):
            raise ValueError('History requires exactly thirty ordered round boundaries')
        self.events = [HistoryEvent(t, t, 'archive', 'read', []) for t in times]

    def add(self, round_number, text, *, record_id=None, category='evidence', occurred=None, received=None, **facts):
        if type(round_number) is not int or not 1 <= round_number <= HISTORY_ROUNDS:
            raise ValueError('Historical round must be in 1..30')
        event = self.events[round_number - 1]
        received = event.time_s - event.time_s % 60 + len(event.records) if received is None else received
        occurred = received if occurred is None else occurred
        if not occurred <= received <= event.time_s:
            raise ValueError('Record occurrence/reception must precede its round boundary')
        identifier = record_id or f'R{round_number:02d}-{len(event.records) + 1:02d}'
        record = {**json.loads(json_text(facts)), 'record_id': identifier, 'text': text,
                  'occurred_s': occurred, 'occurred_at': story_timestamp(occurred),
                  'received_s': received, 'received_at': story_timestamp(received)}
        event.records.append(HistoryRecord(record, category))

    def finish(self, task):
        # Each case owns all mutable inputs, including menus/catalog constants.
        # Mutating a case must not mutate another case or its reviewed builder.
        snapshot = deepcopy(task)
        snapshot.history = deepcopy(self.events)
        snapshot.validate()
        return snapshot


class ArchiveHistory(History):
    """Thirty archived batches before now; every record in a batch shares receipt time."""
    def __init__(self,now,*,spacing_s=1):
        super().__init__(times=[now-(HISTORY_ROUNDS+1-r)*spacing_s for r in range(1,HISTORY_ROUNDS+1)])

    def add(self,round_number,text,*,occurred=None,**facts):
        received = self.events[round_number-1].time_s
        super().add(round_number,text,occurred=received if occurred is None else occurred,received=received,**facts)


def ordered_options(entries, group, *, step=0, seed=SEED):
    """Presentation randomness reads an explicit identity, never the answer."""
    identity = f'{seed}:options:{group}:{step}'.encode()
    rng = Random(int.from_bytes(sha256(identity).digest()[:8], 'big'))
    entries = deepcopy(list(entries))
    rng.shuffle(entries)
    return [{'action': 'select', 'option': str(i + 1), **entry} for i, entry in enumerate(entries)]


def selected_option(actions, submitted):
    if not isinstance(submitted, dict) or set(submitted) != {'action', 'option'}:
        return None
    if submitted['action'] != 'select' or not isinstance(submitted['option'], str):
        return None
    return next((row for row in actions if row.get('option') == submitted['option']), None)


def fixed_options(entries):
    """Number an explicitly frozen menu without deriving a new presentation order."""
    return [{'action':'select','option':str(i+1),**deepcopy(entry)} for i,entry in enumerate(entries)]
