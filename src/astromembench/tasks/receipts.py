"""Shared delivery plumbing; each template owns receipt validity and scoring."""
from copy import deepcopy

from ..environment import TaskRuntime


class ReceiptRuntime(TaskRuntime):
    format_error_limit = 3

    def __init__(self,task):
        super().__init__(task)
        self.feedback_events = []

    def observation(self):
        result = super().observation()
        if self.feedback_events:
            result['feedback_events'] = deepcopy(self.feedback_events)
        return result

    def _emit(self,*args,**kwargs):
        self.feedback_events.append(self.event_builder(*args,**kwargs))
        self.feedback = '\n'.join(event['text'] for event in self.feedback_events)

    def invalid(self):
        super().invalid()
        if self.format_error_limit is not None:
            self.state['format_errors'] += 1
            if self.state['format_errors'] == self.format_error_limit:
                self.end('format_limit')

    def grade(self):
        raise NotImplementedError

    def end(self,reason,*,score=None,full_credit=None):
        score = self.grade() if score is None else score
        super().end(reason,score=score,full_credit=(score == 100) if full_credit is None else full_credit)
