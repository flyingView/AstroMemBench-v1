"""Evaluation stages shared by the runner and timing recorder."""

STAGES = ("setup", "history", "session_boundary", "current", "finalization")


class UsageLedger:
    """Add only explicit per-operation deltas; absent usage remains unknown."""
    FIELDS = {'input_tokens', 'output_tokens', 'cached_input_tokens', 'model_calls'}

    def __init__(self):
        self.calls = 0
        self.reported = 0
        self.totals = {}
        self.stages = {}

    def observe(self, reply, stage):
        self.calls += 1
        usage = reply.get('usage')
        if usage is None:
            return None
        if (not isinstance(usage, dict) or not usage or set(usage) - self.FIELDS
                or any(type(value) is not int or not 0 <= value <= 2**53 - 1 for value in usage.values())):
            return 'Invalid usage metadata ignored; report nonnegative per-operation integer deltas'
        self.reported += 1
        bucket = self.stages.setdefault(stage, {'reported_operations': 0, 'totals': {}})
        bucket['reported_operations'] += 1
        for key, value in usage.items():
            self.totals[key] = self.totals.get(key, 0) + value
            bucket['totals'][key] = bucket['totals'].get(key, 0) + value
        return None

    def snapshot(self):
        if not self.reported:
            return None
        from copy import deepcopy
        return {'source': 'adapter_reported_deltas', 'completed_operations': self.calls,
                'reported_operations': self.reported, 'totals': dict(self.totals), 'stages': deepcopy(self.stages)}
