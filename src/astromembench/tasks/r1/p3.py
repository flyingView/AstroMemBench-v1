"""FM-R1-P3: native thirty-round surveys and the retained M11 delivery contract."""
from copy import deepcopy
from heapq import heappop, heappush
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

# Endpoints, distance, and the two energy columns; blocked traversals always cost 1.
MAPS = (
    (('SA',90,24,8),('AB',60,30,10),('BQ',70,34,12),('QC',150,10,30),('CD',120,8,20),
     ('DS',160,12,18),('AE',50,14,6),('EF',35,6,16),('FC',55,16,4),('BF',25,4,2)),
    (('SA',140,12,12),('AB',80,34,6),('BC',45,2,28),('CQ',160,48,8),('SD',65,4,48),
     ('DE',110,6,4),('EF',55,28,16),('FQ',90,22,22),('AD',40,40,2),('BE',30,8,40),('CF',50,16,34)),
    (('SA',60,12,30),('AB',45,16,12),('BQ',70,30,24),('CD',130,6,8),('DE',90,18,18),
     ('EF',140,4,16),('SC',100,24,10),('AD',35,8,6),('BE',55,10,4),('FQ',80,14,14)),
    (('SA',120,2,16),('AB',70,22,8),('BQ',110,40,4),('SC',80,28,12),('CD',140,34,34),
     ('DQ',90,4,22),('AE',50,12,40),('ED',30,16,28),('CF',60,48,6),('FB',40,8,2),('EF',25,6,48)),
)
CONDITIONS = (
    ((2,10),(2,8),(5,10),(5,8)), ((2,10),(2,11),(7,10),(7,11)),
    ((2,8),(2,9),(5,8),(5,9)), ((2,8),(2,10),(5,8),(5,10)),
)
BLOCK_REASONS = ('岩块堵塞通道','裂隙横断路段','塌陷使路面中断','工程散落物封堵')
HAZARD = '通过该路段时发生侧滑，成功离开，检测到后轮短暂不受控，自动修复完毕。'
# Map index, energy column, condition number, and independently reviewed safe minimum.
CONFIGS = (
    (0,0,1,30),(0,1,2,56),(1,1,2,56),(1,0,3,86),(2,0,1,66),(3,0,1,66),
    (0,1,4,30),(1,1,4,54),(2,1,4,60),(2,0,2,56),(3,0,2,34),(3,1,3,24),
    (0,1,1,64),(1,0,4,68),(2,0,4,58),(3,1,1,24),
)
SURVEYS = {
    (0,2):'A B S D C Q B Q C F E A E F B F C D S',
    (0,5):'A B A E F C D Q B Q C F B F E A S D S',
    (1,2):'A B S D E F E B C Q C F Q F C B E D A D S',
    (1,7):'A S D E F D A B C Q C F Q F C B E B A D S',
    (2,2):'A B S C D E F E B Q F Q B E D A D C S',
    (2,5):'A S C D E A B Q B E F Q F E B A D C S',
    (3,2):'A B S C D C F B Q B F E A E D Q D E F C S',
    (3,5):'A S C D F B A B Q B F E A E D Q D E F C S',
}


def build(index):
    map_index,column,condition,minimum = CONFIGS[index]
    blocked,hazard = CONDITIONS[map_index][condition-1]
    edges = [{'id':f'e{i:02d}','endpoints':list(nodes),'distance_m':distance,'energy':(a,b)[column],
              'condition':'blocked' if i == blocked else 'hazard' if i == hazard else 'normal'}
             for i,(nodes,distance,a,b) in enumerate(MAPS[map_index],1)]
    static = {'nodes':list('SABCDEFQ'),'edges':[{k:deepcopy(e[k]) for k in ('id','endpoints','distance_m')} for e in edges],
              'bidirectional':True}
    history = History()
    history.add(1,'完成运输，合理使用能源，并避免已知危险和无效通行尝试。'
        '勘测与当前运输载荷、驱动配置相同，题内路况与费用稳定，双向费用相同；距离不决定电耗。'
        '危险路段的实际费用已经含自动恢复；自动修复不使路段安全。以下为公开拓扑。',
        event='delivery_survey_protocol',static_map=static)
    history.add(2,'勘测从S开始，电量1000、容量1200；本次沿图实际行驶记录原始回执。',
                event='delivery_survey_initial',node='S',energy=1000,capacity=1200)
    node,battery,q_visits = 'S',1000,0
    for j,target in enumerate(SURVEYS[(map_index,blocked)].split(),1):
        edge = next(e for e in edges if set(e['endpoints']) == {node,target})
        status = edge['condition']
        cost = 1 if status == 'blocked' else edge['energy']
        before = battery
        q_visits += int(target == 'Q' and status != 'blocked')
        recharge = 30 if index >= 12 and target == 'Q' and status != 'blocked' and q_visits == 2 else 0
        battery = before-cost+recharge
        info = {'journey':f'J{j:02d}','source':node,'target':target,'edge':edge['id'],'distance_m':edge['distance_m']}
        result_node = node if status == 'blocked' else target
        outcome = (f'{BLOCK_REASONS[map_index]}，无法通行，仍在{node}。' if status == 'blocked'
                   else (HAZARD if status == 'hazard' else '')+f'抵达{target}。')
        title = f'勘测J{j:02d}，路段{edge["id"]}（{node}—{target}），距离{edge["distance_m"]}米。'
        if index >= 12:
            history.add(j+2,title+f'出发，余电{before}。',event='delivery_survey_departure',**info,battery_before=before)
        if index < 6:
            reading = f'本次实际耗电{cost}。'
            facts = {'energy_used':cost}
        else:
            reading = (f'出发余电{before}。' if index < 12 else '')+f'本次补能{recharge}，停靠余电{battery}。'
            if recharge:
                reading += '本次为第二次成功抵Q，在实际到达之后补入30，停靠读数已含补能。'
            facts = {'battery_after':battery,'recharge':recharge}
            if index < 12:
                facts['battery_before'] = before
        history.add(j+2+int(index >= 12),title+outcome+reading,event='delivery_survey_receipt',**info,
                    condition=status,actual_node=result_node,**facts)
        node = result_node
    history.add(30,'勘测结束并回到S；历史勘测账封存。当前运输整车电量另行调定400，货物已装载。',
                event='delivery_new_batch',node='S',energy=400,loaded=True)
    task = task_shell('FM-R1-P3',index,current_input_group=f'FM-R1-P3-G{map_index+1}')
    task.public = {'instruction':'当前位置S，电量400，货物已装载。请前往交付点Q。','static_map':static,
                   'time_s':clock('09:00'),'destination':'Q','max_steps':2*len(edges),'state_fields':['node','energy','delivered']}
    task.initial = {'node':'S','energy':400,'delivered':False,'blocked_attempts':0,'hazardous_passages':0}
    task.world = {'edges':edges,'block_reason':BLOCK_REASONS[map_index]}
    task.rubric = {'initial_energy':400,'minimum_safe_energy':minimum,'blocked_penalty':25,'hazard_penalty':15}
    return history.finish(task)


class Runtime(TaskRuntime):
    """Preserve the original delivery interface, transitions, feedback and grading."""
    action_contract = ActionContract(('action','to'))

    def actions(self):
        if self.done:
            return []
        moves = [] if self.state['delivered'] else [{'action':'move','to':n} for n in self.neighbors()]
        return moves+[{'action':'deliver','description':'提交到达'}]

    def neighbors(self):
        node = self.state['node']
        return sorted(next(n for n in e['endpoints'] if n != node) for e in self.task.public['static_map']['edges'] if node in e['endpoints'])

    def observation(self):
        result = super().observation()
        result['instruction'] = '货物已装载，请前往交付点Q。' if not self.state['delivered'] else '已抵达交付点Q。'
        result['adjacent_nodes'] = self.neighbors()
        return result

    def _grade_arrival(self):
        energy = self.task.rubric['initial_energy']-self.state['energy']
        reference = self.task.rubric['minimum_safe_energy']
        blocked,hazards = self.state['blocked_attempts'],self.state['hazardous_passages']
        self.score = max(0,100*min(1,reference/energy)-25*blocked-15*hazards)
        self.full_credit = energy == reference and blocked == hazards == 0
        self.facts = {'delivered':True,'delivery_energy':self.state['energy'],'actual_energy':energy,
                      'blocked_attempts':blocked,'hazardous_passages':hazards,'minimum_safe_energy':reference}

    def submit(self,action):
        if action == {'action':'deliver'}:
            if self.state['delivered']:
                self.feedback = '验收通过。'
                self.end('delivered')
            else:
                self.feedback = '尚未到达，请继续。'
            return
        if action == {'action':'end'}:
            self.end('ended')
            return
        if (self.state['delivered'] or not isinstance(action,dict) or set(action) != {'action','to'}
                or action['action'] != 'move' or not isinstance(action['to'],str) or action['to'] not in self.neighbors()):
            self.invalid()
            return
        source,target = self.state['node'],action['to']
        edge = next(e for e in self.task.world['edges'] if set(e['endpoints']) == {source,target})
        blocked = edge['condition'] == 'blocked'
        cost = 1 if blocked else edge['energy']
        if cost > self.state['energy']:
            self.feedback = '电量不足以完成本次移动，仍在原位。'
            self.end('insufficient_energy',score=0,full_credit=False)
            return
        self.state['energy'] -= cost
        if blocked:
            self.state['blocked_attempts'] += 1
            self.feedback = f'路段{edge["id"]}（{source}—{target}）：{self.task.world["block_reason"]}，无法通行，仍在{source}。'
        else:
            self.state['node'] = target
            self.feedback = f'抵达{target}。'
            if edge['condition'] == 'hazard':
                self.state['hazardous_passages'] += 1
                self.feedback = f'路段{edge["id"]}（{source}—{target}）：'+HAZARD+self.feedback
            if target == 'Q':
                self.state['delivered'] = True
                self._grade_arrival()


def safe_path(static,edges,start='S'):
    pending,visited = [(0,(),start)],set()
    while pending:
        energy,path,node = heappop(pending)
        if node in visited:
            continue
        visited.add(node)
        if node == 'Q':
            return energy,list(path)
        for edge in static['edges']:
            physical = edges[edge['id']]
            if node not in edge['endpoints'] or physical['condition'] != 'normal':
                continue
            target = next(n for n in edge['endpoints'] if n != node)
            heappush(pending,(energy+physical['energy'],(*path,target),target))
    raise ValueError('Every retained map must permit a safe delivery')


def reconstruct(history,current):
    departures,edges = {},{}
    topology = {edge['id']:edge for edge in current['static_map']['edges']}
    for text in paragraphs(history):
        receipt = re.fullmatch(r'勘测(J\d+)，路段(e\d+)（([SABCDEFQ])—([SABCDEFQ])），距离(\d+)米。(.+)',text)
        if not receipt:
            continue
        journey,edge,source,target,distance,reading = receipt.groups()
        if (edge not in topology or source == target or set(topology[edge]['endpoints']) != {source,target}
                or topology[edge]['distance_m'] != int(distance)):
            raise ValueError('Delivery receipt edge and endpoints must match the public topology')
        identity = (source,target,edge)
        departure = re.fullmatch(r'出发，余电(\d+)。',reading)
        if departure:
            departures[journey] = (identity,int(departure[1]))
            continue
        blocked = re.match('(?:'+'|'.join(BLOCK_REASONS)+r')，无法通行，仍在([SABCDEFQ])。',reading)
        if blocked:
            if blocked[1] != source:
                raise ValueError('A blocked historical attempt must remain at its departure node')
            condition,reading = 'blocked',reading[blocked.end():]
        else:
            condition = 'hazard' if reading.startswith(HAZARD) else 'normal'
            if condition == 'hazard':
                reading = reading.removeprefix(HAZARD)
            arrival = re.match(r'抵达([SABCDEFQ])。',reading)
            if arrival is None or arrival[1] != target:
                raise ValueError('A historical arrival must reach its printed target')
            reading = reading[arrival.end():]
        direct = re.fullmatch(r'本次实际耗电(\d+)。',reading)
        difference = re.fullmatch(r'(?:出发余电(\d+)。)?本次补能(\d+)，停靠余电(\d+)。'
                                  r'(?:本次为第二次成功抵Q，在实际到达之后补入30，停靠读数已含补能。)?',reading)
        if direct:
            cost = int(direct[1])
        elif difference:
            if difference[1] is None:
                departure_identity,before = departures[journey]
                if departure_identity != identity:
                    raise ValueError('Each receipt must match the same historical journey')
            else:
                before = int(difference[1])
            cost = before-int(difference[3])+int(difference[2])
        else:
            raise ValueError('Delivery receipt needs an actual energy reading')
        physical = {'energy':cost,'condition':condition}
        if cost <= 0 or edge in edges and edges[edge] != physical:
            raise ValueError('Repeated passages must retain their measured cost and road condition')
        edges[edge] = physical
    if set(edges) != {e['id'] for e in current['static_map']['edges']}:
        raise ValueError('Every current edge requires historical evidence')
    minimum,_ = safe_path(current['static_map'],edges)
    return {'edges':edges,'minimum_safe_energy':minimum}


def next_action(facts,current):
    if current['state']['delivered']:
        return {'action':'deliver'}
    _,path = safe_path(current['static_map'],facts['edges'],current['state']['node'])
    return {'action':'move','to':path[0]}


def check_world(task,facts):
    actual = {e['id']:{'energy':1 if e['condition'] == 'blocked' else e['energy'],'condition':e['condition']} for e in task.world['edges']}
    if actual != facts['edges'] or task.rubric['minimum_safe_energy'] != facts['minimum_safe_energy']:
        raise ValueError('Delivery costs, risks and safe minimum must follow historical measurements')


def audit_cases(task,facts,solution):
    first = solution[0]['to']
    edge = next(e for e in task.public['static_map']['edges'] if set(e['endpoints']) == {'S',first})
    minimum = facts['minimum_safe_energy']
    extra = 2*facts['edges'][edge['id']]['energy']
    budget = task.public['max_steps']
    return [([solution[0],{'action':'move','to':'S'}]+solution,100*minimum/(minimum+extra)),
            (solution[:-2]+[{'action':'end'}],0),([{'action':'deliver'}]*budget,0),([{}]*budget,0),
            ([{}]*(budget-len(solution))+solution,100),
            ([{}]*(budget-len(solution)+1)+solution[:-1],100),
            (solution[:-1]+[{'action':'end'}],100)]
