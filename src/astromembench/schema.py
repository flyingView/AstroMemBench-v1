"""Evaluator-owned task records. Only history and observations reach agents."""
from __future__ import annotations

from . import accepts_identifier
from dataclasses import asdict, dataclass, field
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .metadata import TEMPLATE_SPECS, INSTANCES_PER_TEMPLATE

TEMPLATES = {key: spec.name for key, spec in TEMPLATE_SPECS.items()}
MODES = ("new_session", "same_session")
SCHEMA_VERSION = "astromembench-task/5"
HISTORY_ROUNDS = 30
EMPTY_HISTORY = {"text": "本轮无新增作业记录。"}


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def story_timestamp(seconds):
    day, within = divmod(int(seconds), 86400)
    hour, within = divmod(within, 3600)
    minute, second = divmod(within, 60)
    return f"任务第{day}日{hour:02d}:{minute:02d}:{second:02d}"


@dataclass
class HistoryRecord:
    """Classification is for token accounting and audit, never for the participant."""
    data: dict
    category: str = "evidence"

    def public_inputs(self) -> list[dict]:
        """The same prose/attachment representation for every record category.

        Business identities and their chronology belong in the authored prose;
        typed author facts stay available to the evaluator, never as a second
        machine-readable copy beside that prose.
        """
        # Apply the same paragraph boundaries to core and background prose.
        # Keeping an entire background bundle in one record would disclose its
        # category through blank lines even after removing all author fields.
        if "images" in self.data:
            return [{"text": self.data["text"], "images": deepcopy(self.data["images"])}]
        return [{"text": paragraph} for paragraph in self.data["text"].split("\n\n")]


@dataclass
class HistoryEvent:
    time_s: float
    occurred_s: float
    channel: str
    step_type: str
    records: list[HistoryRecord]

    def to_dict(self) -> dict:
        return asdict(self)

    def public_input(self) -> dict:
        """Past facts only; classification and evaluator state never cross here."""
        return {
            "time_s": self.time_s, "occurred_s": self.occurred_s,
            "received_at": story_timestamp(self.time_s), "occurred_at": story_timestamp(self.occurred_s),
            "channel": self.channel, "step_type": self.step_type,
            "data": {"records": [paragraph for record in self.records for paragraph in record.public_inputs()] or [deepcopy(EMPTY_HISTORY)]},
        }

    @classmethod
    def from_dict(cls, value: dict) -> HistoryEvent:
        return cls(**{**value, "records": [HistoryRecord(**row) for row in value["records"]]})


@dataclass
class Edge:
    source: str
    target: str
    distance_m: float
    energy: float
    load_slope: float = 0.0
    duration_s: float = 20.0

    def cost(self, load: float = 1.0) -> float:
        return self.energy + self.load_slope * (load - 1.0)


@dataclass
class Task:
    case_id: str
    template: str
    difficulty: str
    history: list[HistoryEvent]
    public: dict
    initial: dict
    world: dict
    rubric: dict
    design: dict = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> Task:
        if not accepts_identifier(value.get("schema_version"), SCHEMA_VERSION):
            raise ValueError("Expected astromembench-task/5; read archived tasks with their frozen implementation")
        task = cls(**{**value, "history": [HistoryEvent.from_dict(event) for event in value["history"]]})
        task.validate()
        return task

    def validate(self) -> None:
        """Validate the file boundary, not every internal state transition."""
        if not accepts_identifier(self.schema_version, SCHEMA_VERSION):
            raise ValueError("Unsupported task schema")
        if self.template not in TEMPLATE_SPECS:
            raise ValueError("Unknown SCC template")
        if self.case_id not in {f'{self.template}-{i:03d}' for i in range(1, INSTANCES_PER_TEMPLATE + 1)}:
            raise ValueError("Instance identity must belong to its template's sixteen cases")
        if self.difficulty not in {"easy", "medium", "hard"}:
            raise ValueError("Unknown difficulty")
        instance = int(self.case_id.rsplit('-', 1)[1])
        expected_difficulty = 'easy' if instance <= 6 else 'medium' if instance <= 12 else 'hard'
        if self.difficulty != expected_difficulty:
            raise ValueError('Instance difficulty must follow the approved 6/6/4 allocation')
        if len(self.history) != HISTORY_ROUNDS:
            raise ValueError(f"Every current instance requires exactly {HISTORY_ROUNDS} history rounds")
        if self.design.get("classification") != TEMPLATE_SPECS[self.template].to_dict():
            raise ValueError("Task classification differs from the SCC catalog")
        received = float("-inf")
        record_ids = set()
        for event in self.history:
            if not all(isinstance(t, (int, float)) and not isinstance(t, bool)
                       and float("-inf") < t < float("inf") for t in (event.time_s, event.occurred_s)):
                raise ValueError("History timestamps must be finite numbers")
            if event.time_s < received or event.occurred_s > event.time_s:
                raise ValueError("History must follow reception order without future records")
            received = event.time_s
            if event.step_type != "read":
                raise ValueError("All history rounds are read-only past facts")
            if any(record.category not in {"evidence", "related", "background"} for record in event.records):
                raise ValueError("Unknown historical evidence category")
            for record in event.records:
                if not isinstance(record.data, dict):
                    raise ValueError("Historical records must be objects")
                if not isinstance(record.data.get('text'), str):
                    raise ValueError("Historical records must contain public prose")
                identifier = record.data.get("record_id")
                if identifier is not None:
                    if not isinstance(identifier, str) or not identifier or identifier in record_ids:
                        raise ValueError("Historical record identifiers must be unique nonempty strings")
                    record_ids.add(identifier)
                if record.category != 'background':
                    occurred = record.data.get('occurred_s')
                    received_at = record.data.get('received_s')
                    if (any(type(t) not in (int, float) or not float('-inf') < t < float('inf')
                            for t in (occurred, received_at))
                            or not occurred <= received_at <= event.time_s):
                        raise ValueError("Record occurrence/reception must precede its round boundary")
        now = self.public.get('time_s')
        if now is not None and received > now:
            raise ValueError("Past history cannot end after the current task begins")


def write_tasks(tasks: list[Task], path: Path) -> None:
    for task in tasks:
        task.validate()
    if len({task.case_id for task in tasks}) != len(tasks):
        raise ValueError("Duplicate case identifiers")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json_text(task.to_dict()) + "\n" for task in tasks), encoding="utf-8")


def decode_tasks(data: bytes) -> list[Task]:
    return [Task.from_dict(json.loads(line)) for line in data.decode('utf-8').splitlines() if line.strip()]


def read_tasks(path: Path) -> list[Task]:
    return decode_tasks(path.read_bytes())
