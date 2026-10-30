"""One preparation, then one decision; arrivals are delivered by the real step."""
from copy import deepcopy

from ..environment import SingleChoiceRuntime
from ..schema import story_timestamp
from .common import selected_option


def audit_decision_cases(task,facts,solution):
    """Exercise every alternative business choice and both retry positions."""
    cases = [([{}]*3,0),([{},{}]+solution,100),([solution[0],{}, {},solution[1]],100)]
    for option in task.public['actions']:
        if option.get('action') == 'select' and option['operation'] != facts['decision']:
            cases.append(([solution[0],{'action':'select','option':option['option']}],0))
    return cases


class PreparedChoiceRuntime(SingleChoiceRuntime):
    def __init__(self,task):
        super().__init__(task)
        self.received_messages = []

    def actions(self):
        if self.done:
            return []
        if not self.state['prepared']:
            return [{'action':'prepare','description':'完成作业前准备'},
                    {'action':'end','description':'放弃本次任务'}]
        return super().actions()

    def observation(self):
        result = super().observation()
        result.update(time_s=self.state['time_s'],current_time=story_timestamp(self.state['time_s']))
        if self.received_messages:
            result['received_messages'] = deepcopy(self.received_messages)
        return result

    def step(self,action):
        self.received_messages = []
        return super().step(action)

    def invalid(self):
        super().invalid()
        self.state['format_errors'] += 1
        if self.state['format_errors'] == 3:
            self.end('format_limit')

    def submit(self,action):
        if action == {'action':'end'}:
            return super().submit(action)
        if not self.state['prepared']:
            if action != {'action':'prepare'}:
                self.invalid()
                return
            self.state['prepared'] = True
            self.state['time_s'] = self.task.world['arrival_time_s']
            self.received_messages = deepcopy(self.task.world['arrivals'])
            self.feedback = '作业前准备完成，收到转发指示。'
            return
        option = selected_option(self.actions(),action)
        super().submit(action)
        if option is not None:
            self.feedback = option['description'] + '请求已完成。'
