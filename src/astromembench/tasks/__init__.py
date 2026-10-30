"""Reviewed SCC templates, each authored as sixteen native thirty-round cases."""
from importlib import import_module

from ..metadata import TEMPLATE_SPECS


def template_module(template):
    if template not in TEMPLATE_SPECS:
        raise ValueError(f"Unknown template: {template}")
    spec = TEMPLATE_SPECS[template]
    return import_module(f".{spec.subchallenge.lower()}.{spec.mission.lower()}", __name__)
