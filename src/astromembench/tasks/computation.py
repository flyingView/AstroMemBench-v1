"""Meter paid computation and accept one finite numeric answer without retrying it."""
import json
from math import isfinite

from ..environment import TaskRuntime


class ComputationRuntime(TaskRuntime):
    """Templates own input packages and correctness; this class owns the shared protocol."""
    default_scope = None
    answer_dimensions = 1

    def actions(self):
        return [] if self.done else super().actions()

    def computation_inputs(self,scope):
        raise NotImplementedError

    def answer_credit(self,value):
        raise NotImplementedError

    def valid_value(self,value):
        if self.answer_dimensions == 1:
            values = [value]
        elif isinstance(value,list) and len(value) == self.answer_dimensions:
            values = value
        else:
            return False
        return all(type(v) is int or type(v) is float and isfinite(v) for v in values)

    def submit(self,action):
        if action == {'action':'end'}:
            self.feedback = '任务已结束'
            self.end('ended')
            return
        if isinstance(action,dict) and action.get('action') == 'get_steps':
            scope = action.get('scope',self.default_scope)
            valid = action == {'action':'get_steps'} if self.default_scope is None else (
                set(action) in ({'action'},{'action','scope'}) and isinstance(scope,str) and scope in self.query_costs)
            if valid:
                cost = self.query_costs[scope]
                if self.state['energy'] < cost:
                    self.feedback = self.insufficient_feedback
                    return
                self.state['energy'] -= cost
                inputs,formula = self.computation_inputs(scope)
                self.feedback = '输入包：'+json.dumps(inputs,ensure_ascii=False)+'；求解式：'+formula+f'；本次耗电{cost}，余额{self.state["energy"]}。'
                return
        if isinstance(action,dict) and set(action) == {'action','value'} and action['action'] == 'submit' and self.valid_value(action['value']):
            credit = self.answer_credit(action['value'])
            initial = self.task.initial['energy']
            score = credit*self.state['energy']/initial
            self.facts['spent_energy'] = initial-self.state['energy']
            self.feedback = self.submitted_feedback
            self.end('completed',score=score,full_credit=score == 100)
            return
        self.feedback = '请求格式无效'
