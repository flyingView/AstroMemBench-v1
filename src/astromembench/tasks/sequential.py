"""Protocol mechanics for a visible fixed sequence of one-shot operations."""
from ..environment import TaskRuntime
from .common import selected_option


class SequentialRuntime(TaskRuntime):
    """A valid operation advances once; three malformed requests skip one item.

    Subclasses own effects, irreversible consequences, observations and scores.
    """
    def actions(self):
        if self.done:
            return []
        from copy import deepcopy
        return deepcopy(self.task.public['options_by_step'][self.state['index']]) + [
            {'action': 'end', 'description': '结束本轮作业'}]

    def operate(self, option, index):
        raise NotImplementedError

    def _advance(self):
        self.state['index'] += 1
        self.state['format_attempts'] = 0
        if self.state['index'] == len(self.task.public['sequence']):
            self.end('completed', full_credit=self.score == 100)

    def submit(self, action):
        if action == {'action': 'end'}:
            self.end('ended', full_credit=self.score == 100)
            return
        option = selected_option(self.actions(), action)
        if option is None:
            self.invalid()
            self.state['format_attempts'] += 1
            if self.state['format_attempts'] == 3:
                self.feedback = '本项格式交互额度已用尽，未执行操作，转入下一项。'
                self._advance()
            return
        self.operate(option, self.state['index'])
        self.state['executed'] += 1
        self._advance()
