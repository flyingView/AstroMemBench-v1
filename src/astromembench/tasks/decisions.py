"""One irreversible menu decision, with physical time owned by the template."""
from copy import deepcopy

from .common import selected_option
from ..environment import TaskRuntime
from ..schema import story_timestamp


class DecisionRuntime(TaskRuntime):
    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        result = super().observation()
        result.update(time_s=self.state['time_s'],current_time=story_timestamp(self.state['time_s']))
        return result

    def execute(self,operation):
        raise NotImplementedError

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        option = selected_option(self.actions(),action)
        if option is None:
            self.invalid()
            return
        operation = deepcopy(option['operation'])
        self.facts['executed_operation'] = operation
        score = self.execute(operation)
        self.end('completed',score=score,full_credit=score == 100)


def decision_command(current,operation):
    return next(deepcopy(row['arguments']) for row in current['actions'] if row['details']['operation'] == operation)


def decision_cases(task,solution,score):
    return [([{'action':'select','option':row['option']}],score(row['operation'])) for row in task.public['actions']] + [
        ([{},{}]+solution,100),([{}]*3,0)]
