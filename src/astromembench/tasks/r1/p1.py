"""FM-R1-P1: visit both survey endpoints and close the real energy-costed walk."""
from copy import deepcopy
from heapq import heappop, heappush
import re

from ..common import History, clock, task_shell
from ..prose import paragraphs
from .navigation import EnergyNavigation, edge_between

TOPOLOGY = (
    {'id':'e1','nodes':['S','A'],'distance_m':40}, {'id':'e2','nodes':['A','B'],'distance_m':25},
    {'id':'e3','nodes':['B','C'],'distance_m':35}, {'id':'e4','nodes':['C','S'],'distance_m':60},
    {'id':'e5','nodes':['S','B'],'distance_m':20}, {'id':'e6','nodes':['A','C'],'distance_m':15},
)
CONFIGS = (
    (1,(6,7,5,8,3,4)),(4,(4,12,3,8,2,5)),(2,(7,6,3,4,15,2)),
    (3,(7,4,2,12,3,10)),(1,(20,3,4,5,8,2)),(3,(6,20,4,4,5,3)),
    (1,(5,18,3,4,2,6)),(3,(3,6,2,8,7,4)),(4,(5,7,8,9,2,6)),
    (3,(4,3,2,5,20,4)),(1,(3,4,12,15,5,2)),(2,(8,6,4,5,9,2)),
    (2,(5,8,3,4,14,2)),(3,(9,16,2,5,4,3)),(1,(7,5,4,6,3,2)),(4,(4,5,7,8,2,6)),
)
CONDITIONS = {1:('e5','e6'),2:('e2','e6'),3:('e1','e3'),4:('e4','e5')}
HISTORICAL_TARGETS = {
    1:('A','B','C','A','C','B','A','S','C','S','B'),
    2:('A','B','C','B','S','B','C','A','S','C','S'),
    3:('A','B','A','C','B','C','A','B','S','C','S'),
    4:('A','B','C','S','A','C','B','A','S','B','S'),
}


def safe_walk(topology,edges,location='S',observed=None):
    """Shortest walk in (node, visited endpoints), accepting every visit order."""
    observed = observed or {'A':False,'B':False}
    mask = int(observed['A'])+2*int(observed['B'])
    pending = [(0,(),location,mask)]
    visited = set()
    while pending:
        energy,path,node,mask = heappop(pending)
        if (node,mask) in visited:
            continue
        visited.add((node,mask))
        if node == 'S' and mask == 3:
            return energy,list(path)
        for edge in topology:
            physical = edges[edge['id']]
            if node not in edge['nodes'] or physical['status'] != 'normal':
                continue
            destination = next(n for n in edge['nodes'] if n != node)
            next_mask = mask | {'A':1,'B':2}.get(destination,0)
            heappush(pending,(energy+physical['energy'],(*path,destination),destination,next_mask))
    raise ValueError('The public recovered graph must permit a safe closed survey')


def build(index):
    kind,costs = CONFIGS[index]
    blocked,hazard = CONDITIONS[kind]
    edges = {edge['id']:{'energy':2 if edge['id'] == blocked else energy,
                        'status':'blocked' if edge['id'] == blocked else 'hazard' if edge['id'] == hazard else 'normal'}
             for edge,energy in zip(TOPOLOGY,costs,strict=True)}
    history = History()
    history.add(1,'同载荷车辆在S/A/B/C六条双向测线行驶；费用和路况稳定，距离不代表耗电。'
        '本批须实际到访A、B完成两个端点定位观测并回S，访问先后任意，C可中转。自动载荷首次到访即观测，无额外能耗、动作或许可；重复不增加收益。'
        '低层导航、定位、扫描与配置正常，旧批观测不算本批。完成勘察应合理用电，经历侧滑即使自动恢复仍应避免该风险。'
        '阻断尝试实际耗2电并留原地；危险边按其实际通行费用扣电，含自动恢复，记一次风险。双向和重复规则相同。'
        '当前不提供边费用或路况查询，不补能或回滚；只可逐边move(to)、finish或end，参数严格按当前动作列，不接收自然语言路线。'
        '总计18次调用含合法、格式错误、非邻接移动、finish和end；非法调用不耗电、不移动但占一次。'
        '首次在A/B均已观测后进入S即锁定本批闭合成果，之后不能再移动；finish确认结束，end或额度耗尽保留已锁定成果。'
        '未闭合时finish只报告尚未闭合，未闭合主动结束或额度耗尽均无本批成果。'
        '边的实际费用大于余电时原地中止，未产生闭合成果；等于余电且闭合时正常结算。',
        event='closed_survey_protocol',topology=TOPOLOGY,targets=['A','B'],rendezvous='S',blocked_energy=2,max_actions=18)
    history.add(2,'旧批勘测从S出发，试验电池余电500、容量600；历史观测属于旧批。',
                event='survey_trial_initial',location='S',battery=500,battery_capacity=600)
    location,battery,returns = 'S',500,0
    for j,target in enumerate(HISTORICAL_TARGETS[kind],1):
        edge = edge_between(TOPOLOGY,location,target)
        physical = edges[edge['id']]
        before = battery
        arrived = physical['status'] != 'blocked'
        returns += int(arrived and target == 'S')
        recharge = 20 if index >= 12 and arrived and target == 'S' and returns == 2 else 0
        battery = before-physical['energy']+recharge
        info = {'journey':f'J{j:02d}','edge':edge['id'],'source':location,'target':target,'distance_m':edge['distance_m']}
        outcome = '测线入口岩块封堵，仍在原节点' if not arrived else '发生侧滑，已自动恢复，抵达目标' if physical['status'] == 'hazard' else '正常抵达目标'
        if index < 6:
            history.add(j+2,f'旧批J{j:02d}：{location}前往{target}，边{edge["id"]}距离{edge["distance_m"]}米。{outcome}；实际耗电{physical["energy"]}。',
                        event='survey_travel_receipt',**info,status=physical['status'],energy_used=physical['energy'])
        elif index < 12:
            history.add(j+2,f'旧批J{j:02d}：{location}前往{target}，边{edge["id"]}距离{edge["distance_m"]}米。出发余电{before}，停靠余电{battery}，无补能；{outcome}。',
                        event='survey_travel_receipt',**info,status=physical['status'],battery_before=before,battery_after=battery,recharge=0)
        else:
            history.add(j+2,f'旧批J{j:02d}出发：从{location}前往{target}，边{edge["id"]}距离{edge["distance_m"]}米；出发余电{before}。',
                        event='survey_travel_departure',**info,battery_before=before)
            history.add(j+3,f'旧批J{j:02d}结果：{outcome}；停靠余电{battery}，此次明确补能{recharge}。'+
                        ('这是第二次成功返回S，已补入20电。' if recharge else ''),
                        event='survey_travel_receipt',**info,status=physical['status'],battery_after=battery,recharge=recharge)
        if arrived:
            location = target
    history.add(15,'旧批勘测已经结束，车辆已回S；载荷记录归入旧批档案。',event='survey_trial_finished',location='S')
    history.add(30,'本批重新初始化：车辆在S，余电200，A/B两个端点均未完成本批观测；当前无补能。',
                event='survey_new_batch',location='S',battery=200,observed={'A':False,'B':False})
    minimum,_ = safe_walk(TOPOLOGY,edges)
    task = task_shell('FM-R1-P1',index,current_input_group='FM-R1-P1')
    task.public = {'instruction':'当前在S，电量200。本批需完成A、B两个测线端点观测并回到S汇合。',
                   'time_s':clock('09:00'),'topology':deepcopy(list(TOPOLOGY)),'max_steps':18,
                   'state_fields':['location','battery','observed','closed'],'actions':[]}
    task.initial = {'location':'S','battery':200,'observed':{'A':False,'B':False},'closed':False,
                    'blocked_attempts':0,'hazard_events':0,'traversals':[]}
    task.world = {'edges':edges,'minimum_safe_energy':minimum}
    task.rubric = {'score':'0 before closure; max(0,100*min(1,minimum_safe_energy/(200-battery))-15*blocked_attempts-25*hazard_events)'}
    return history.finish(task)


class Runtime(EnergyNavigation):
    penalties = (15,25)
    finish_description = '提交本批勘察。'
    finish_feedback = ('本批测线尚未闭合','本批测线已闭合。')

    def observation(self):
        return {**super().observation(),'instruction':f'当前在{self.state["location"]}，电量{self.state["battery"]}。本批需完成A、B两个测线端点观测并回到S汇合。'}

    def physical_edge(self,edge):
        return self.task.world['edges'][edge]

    def arrive(self,target):
        if target in self.state['observed']:
            self.state['observed'][target] = True
        if target == 'S' and all(self.state['observed'].values()):
            self.state['closed'] = True


def reconstruct(history,current):
    departures,edges = {},{}
    statuses = {'测线入口岩块封堵，仍在原节点':'blocked',
                '发生侧滑，已自动恢复，抵达目标':'hazard','正常抵达目标':'normal'}
    outcomes = '('+'|'.join(statuses)+')'
    for text in paragraphs(history):
        departure = re.fullmatch(r'旧批(J\d+)出发：从([SABC])前往([SABC])，边(e[1-6])距离(\d+)米；出发余电(\d+)。',text)
        combined = re.fullmatch(r'旧批(J\d+)：([SABC])前往([SABC])，边(e[1-6])距离(\d+)米。(.+)',text)
        title = departure or combined
        if title:
            journey,source,target,edge,distance = title.groups()[:5]
            topology = edge_between(current['topology'],source,target)
            if topology is None or topology['id'] != edge or topology['distance_m'] != int(distance):
                raise ValueError('Survey receipt edge and endpoints must match the public topology')
            if departure:
                departures[journey] = {'edge':edge,'battery_before':int(departure[6])}
                continue
            direct = re.fullmatch(outcomes+r'；实际耗电(\d+)。',combined[6])
            difference = re.fullmatch(r'出发余电(\d+)，停靠余电(\d+)，无补能；'+outcomes+r'。',combined[6])
            if direct:
                status,energy = statuses[direct[1]],int(direct[2])
            elif difference:
                status,energy = statuses[difference[3]],int(difference[1])-int(difference[2])
            else:
                raise ValueError('Survey receipt needs an actual outcome and energy reading')
        else:
            receipt = re.fullmatch(r'旧批(J\d+)结果：'+outcomes+r'；停靠余电(\d+)，此次明确补能(\d+)。'
                                   r'(?:这是第二次成功返回S，已补入20电。)?',text)
            if not receipt:
                continue
            departure = departures[receipt[1]]
            edge,status = departure['edge'],statuses[receipt[2]]
            energy = departure['battery_before']-int(receipt[3])+int(receipt[4])
        physical = {'energy':energy,'status':status}
        if energy <= 0 or edge in edges and edges[edge] != physical:
            raise ValueError('Both directions must have the same stable actual cost and road condition')
        edges[edge] = physical
    if set(edges) != {e['id'] for e in current['topology']}:
        raise ValueError('Every current edge needs historical energy and road-condition evidence')
    minimum,_ = safe_walk(current['topology'],edges)
    return {'edges':edges,'minimum_safe_energy':minimum}


def next_action(facts,current):
    if current['state']['closed']:
        return {'action':'finish'}
    _,path = safe_walk(current['topology'],facts['edges'],current['state']['location'],current['state']['observed'])
    return {'action':'move','to':path[0]}


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Current road costs, conditions and optimal closure must follow the historical receipts')


def audit_cases(task,facts,solution):
    # Real harmless extra travel, incomplete coverage, invalid calls, and budget expiry.
    first = solution[0]['to']
    extra = 2*facts['edges'][edge_between(task.public['topology'],'S',first)['id']]['energy']
    minimum = facts['minimum_safe_energy']
    cases = [([solution[0],{'action':'move','to':'S'}]+solution,100*minimum/(minimum+extra)),
             (solution[:-2]+[{'action':'end'}],0),([{'action':'finish'}]*18,0),([{}]*18,0),
             ([{}]*(18-len(solution))+solution,100)]
    # Reverse a safe optimal cycle/walk; endpoint visit order is unconstrained.
    nodes = ['S']+[a['to'] for a in solution if a['action'] == 'move']
    cases.append(([{'action':'move','to':n} for n in list(reversed(nodes))[1:]]+[{'action':'finish'}],100))
    return cases
