"""Shared energy navigation; each mission owns its arrival consequences."""
from copy import deepcopy

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp


def edge_between(topology,source,target):
    return next((edge for edge in topology if source != target and set(edge['nodes']) == {source,target}),None)


class EnergyNavigation(TaskRuntime):
    """Exact adjacent moves, irreversible costs, lock/finish, and one call budget.

    Missions provide physical_edge(id), arrive(target), penalty weights and
    finish text. Edges supply energy/status, optionally extra private trace facts.
    arrive owns any payload operation and sets closed on actual mission completion.
    """
    action_contract = ActionContract(fields=('action','to'))
    move_seconds = 0

    def physical_edge(self,edge):
        raise NotImplementedError

    def arrive(self,target):
        raise NotImplementedError

    def neighbors(self):
        return sorted(next(n for n in edge['nodes'] if n != self.state['location'])
                      for edge in self.task.public['topology'] if self.state['location'] in edge['nodes'])

    def public_state(self):
        return {**super().public_state(),'neighbors':self.neighbors()}

    def observation(self):
        result = super().observation()
        if 'time_s' in self.state:
            result.update(time_s=self.state['time_s'],current_time=story_timestamp(self.state['time_s']))
        return result

    def actions(self):
        if self.done:
            return []
        moves = [] if self.state['closed'] else [{'action':'move','to':n,'description':f'沿相邻测线前往{n}。'} for n in self.neighbors()]
        return moves+[{'action':'finish','description':self.finish_description},{'action':'end','description':'结束本次任务。'}]


    def energy_efficiency(self):
        return 100*min(1,self.task.world['minimum_safe_energy']/(self.task.initial['battery']-self.state['battery']))

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if action == {'action':'finish'}:
            self.feedback = self.finish_feedback[int(self.state['closed'])]
            if self.state['closed']:
                self.end('completed')
            return
        if not isinstance(action,dict) or set(action) != {'action','to'} or action['action'] != 'move' or not isinstance(action['to'],str) or action['to'] not in self.neighbors() or self.state['closed']:
            self.invalid()
            return
        source,target = self.state['location'],action['to']
        edge = edge_between(self.task.public['topology'],source,target)
        physical = self.physical_edge(edge['id'])
        cost,status = physical['energy'],physical['status']
        if cost > self.state['battery']:
            self.feedback = '余电不足以执行本段，车辆在原节点中止。'
            self.end('insufficient_energy',score=0,full_credit=False)
            return
        self.state['battery'] -= cost
        if self.move_seconds:
            self.state['time_s'] += self.move_seconds
        self.state['traversals'].append({'edge':edge['id'],'source':source,'target':target,'energy_used':cost,
                                        **deepcopy({k:v for k,v in physical.items() if k != 'energy'})})
        if status == 'blocked':
            self.state['blocked_attempts'] += 1
            self.feedback = '测线入口岩块封堵，仍在原节点'
            return
        self.state['location'] = target
        self.state['hazard_events'] += int(status == 'hazard')
        self.feedback = '发生侧滑，已自动恢复，抵达目标' if status == 'hazard' else '正常抵达目标'
        self.arrive(target)
        if self.state['closed']:
            nb,nh = self.penalties
            self.score = max(0,self.energy_efficiency()-nb*self.state['blocked_attempts']-nh*self.state['hazard_events'])
            self.full_credit = self.score == 100
