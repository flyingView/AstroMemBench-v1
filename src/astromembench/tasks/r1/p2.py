"""FM-R1-P2: real sampling switches the energy model for the return journey."""
from copy import deepcopy
from heapq import heappop, heappush
import re

from ..common import History, clock, task_shell
from ..prose import paragraphs
from .navigation import EnergyNavigation, edge_between

TOPOLOGY = (
    {'id':'e1','nodes':['S','A'],'distance_m':40}, {'id':'e2','nodes':['A','Q'],'distance_m':30},
    {'id':'e3','nodes':['S','B'],'distance_m':25}, {'id':'e4','nodes':['B','Q'],'distance_m':50},
    {'id':'e5','nodes':['S','Q'],'distance_m':20}, {'id':'e6','nodes':['A','B'],'distance_m':15},
)
# Empty e1-e5, sample-loaded e1-e5, hazardous edge. e6 is always actually blocked.
CONFIGS = (
    ((6,5,4,8,7),(11,10,5,9,20),'e2'),((8,6,4,5,15),(9,7,10,9,15),'e3'),
    ((3,5,4,4,6),(6,7,6,9,16),'e1'),((5,6,7,3,9),(8,8,9,7,15),'e4'),
    ((9,3,5,9,3),(13,5,6,10,5),'e5'),((6,7,8,6,4),(9,9,10,8,6),'e5'),
    ((5,7,4,6,2),(6,8,8,9,3),'e5'),((9,6,4,7,3),(10,8,6,9,4),'e5'),
    ((4,5,6,7,11),(7,6,8,9,14),'e1'),((3,4,5,4,8),(10,8,6,5,14),'e2'),
    ((7,5,6,6,9),(9,8,8,9,15),'e3'),((6,3,7,5,12),(8,7,9,8,17),'e1'),
    ((7,3,4,8,3),(12,8,6,9,5),'e5'),((4,6,8,5,9),(7,8,9,7,18),'e3'),
    ((8,4,5,9,10),(11,9,6,10,18),'e4'),((5,5,6,4,10),(8,7,7,8,15),'e3'),
)
HISTORY_TARGETS = ('A','B','Q','S','B','Q','A','S','Q','B','S')
BRANCHES = {'A':['S','A','Q'],'B':['S','B','Q'],'D':['S','Q']}


def safe_path(topology,edges,start,goal):
    pending,visited = [(0,(),start)],set()
    while pending:
        cost,path,node = heappop(pending)
        if node in visited:
            continue
        if node == goal:
            return cost,list(path)
        visited.add(node)
        for edge in topology:
            physical = edges[edge['id']]
            if node not in edge['nodes'] or physical['status'] != 'normal':
                continue
            target = next(n for n in edge['nodes'] if n != node)
            heappush(pending,(cost+physical['energy'],(*path,target),target))
    raise ValueError('Both load modes require a safe path between base and sampling point')


def minimum_energy(topology,edges):
    return 12+safe_path(topology,edges['empty'],'S','Q')[0]+safe_path(topology,edges['loaded'],'Q','S')[0]


def build(index):
    empty,loaded,hazard = CONFIGS[index]
    edges = {load:{edge['id']:{'energy':cost,'status':'blocked' if edge['id'] == 'e6' else 'hazard' if edge['id'] == hazard else 'normal'}
                   for edge,cost in zip(TOPOLOGY,(*costs,2),strict=True)} for load,costs in (('empty',empty),('loaded',loaded))}
    history = History()
    history.add(1,'空载从S赴固定样点Q，取唯一一份样品后装样送回S。S/A/B/Q六条边双向等耗，同载荷费用及路况稳定，距离不决定耗电。'
        '导航和采样程序均正常，能源单位为合成模型。每次真实移动或受阻尝试60秒。'
        '首次实际到Q，若余电≥12就自动扣12并用60秒完成唯一固定采样，立即持样并切为装样费用；等于12也采样成功。'
        '到Q余电<12则不能启动采样，保留已抵Q的余额并失败结束；不能继续探索后重试。以后回Q不再取样或扣12。'
        '首次持样回S即时交接、卸下样品并锁定本批成果，此后不能移动；初始在S或空载返S不完成。'
        'finish确认已交样结果；未交样时仅报告尚未交回且占一次，end或耗尽额度保留已锁定成果、未完成为无成果。'
        '当前无补能、费用查询、回滚，自动取样不能拒绝；合理用电并避免已知风险。'
        '受阻尝试耗2且留原地；侧滑按该载荷实际费用通过并自动恢复，恢复费用已包含，但风险经历不消除。'
        '所需边费用大于余电时尚未执行、原地原余额中止；等于余电可执行，最后返S余0仍可交样。'
        '只接受move和当前邻接节点精确字符串to，或finish、end，不能多字段/缺字段/错类型/猜自然语言路线。'
        '总共18次调用，包括移动、受阻、非法、提前finish及end。非法调用不耗电、不移动也不推进时钟；交样/finish/end即时。',
        event='sample_route_protocol',topology=TOPOLOGY,sampling_energy=12,move_seconds=60,sampling_seconds=60,max_actions=18)
    history.add(2,'历史空载标定从S、电量500、容量600开始。标定模式只测路段，到Q不自动采样；另一模式使用与本次一份样品同重量和驱动配置的固定测试载荷。',
                event='sample_calibration_initial',load='empty',location='S',battery=500,battery_capacity=600,sampling_enabled=False)
    for load,prefix,start_round in (('empty','L',3),('loaded','H',16 if index >= 12 else 15)):
        if load == 'loaded':
            history.add(15 if index >= 12 else 14,'在S安装固定测试载荷，电量独立调定500、容量600；标定时到Q仍不采样。',
                        event='sample_calibration_initial',load=load,location='S',battery=500,battery_capacity=600,sampling_enabled=False)
        location,battery = 'S',500
        for j,target in enumerate(HISTORY_TARGETS,1):
            edge = edge_between(TOPOLOGY,location,target)
            physical = edges[load][edge['id']]
            before = battery
            recharge = (20 if load == 'empty' else 30) if index >= 12 and j == 6 else 0
            battery = before-physical['energy']+recharge
            result_round = start_round+j-1+int(index >= 12)
            arrived = clock(f'08:{result_round:02d}:{2*j:02d}')
            departed = arrived-60
            received = arrived+int(recharge > 0)
            info = {'journey':f'{prefix}{j:02d}','load':load,'source':location,'target':target,'edge':edge['id'],'distance_m':edge['distance_m'],
                    'departed_s':departed}
            outcome = '测线入口岩块封堵，仍在原节点' if physical['status'] == 'blocked' else '发生侧滑，已自动恢复，抵达目标' if physical['status'] == 'hazard' else '正常抵达目标'
            title = f'标定{prefix}{j:02d}（{"空载" if load == "empty" else "装样"}）：{location}前往{target}，边{edge["id"]}，距离{edge["distance_m"]}米。'
            if index >= 12:
                history.add(result_round-1,title+f'行程出发，余电{before}。',occurred=departed,received=departed,
                            event='sample_travel_departure',**info,battery_before=before)
            if index < 6:
                facts = {'energy_used':physical['energy']}
                text = f'{outcome}；实际耗电{physical["energy"]}。'
            else:
                facts = {'battery_after':battery,'recharge':recharge,'recharged_s':arrived+1 if recharge else None}
                if index < 12:
                    facts['battery_before'] = before
                text = (f'出发余电{before}，' if index < 12 else '')+f'{outcome}；本次补能{recharge}，停靠余电{battery}。'
                if recharge:
                    text += '本次第二次抵Q，行程到达后一秒补能完成；所报停靠余电为补能后读数。'
            history.add(result_round,title+text,occurred=arrived,received=received,
                        event='sample_travel_receipt',**info,arrived_s=arrived,status=physical['status'],**facts)
            if physical['status'] != 'blocked':
                location = target
    history.add(30,'结束标定并卸下测试载荷；新批在S，空载、电量160、尚未取样。',
                event='sample_new_batch',location='S',battery=160,load='empty',sampled=False,has_sample=False)
    task = task_shell('FM-R1-P2',index,current_input_group='FM-R1-P2')
    task.public = {'instruction':'当前在S，电量160，空载。本批在Q取一份样品并送回S；自动取样耗12电量。',
                   'time_s':clock('09:00'),'topology':deepcopy(list(TOPOLOGY)),'sampling_energy':12,'max_steps':18,
                   'state_fields':['time_s','location','battery','load','sampled','has_sample','closed'],'actions':[]}
    task.initial = {'time_s':clock('09:00'),'location':'S','battery':160,'load':'empty','sampled':False,'has_sample':False,'closed':False,
                    'sampling_completed_s':None,'blocked_attempts':0,'hazard_events':0,'traversals':[]}
    task.world = {'edges':edges,'minimum_safe_energy':minimum_energy(TOPOLOGY,edges)}
    task.rubric = {'score':'0 before sample handover; max(0,100*min(1,minimum_safe_energy/(160-battery))-10*blocked_attempts-30*hazard_events)'}
    return history.finish(task)


class Runtime(EnergyNavigation):
    move_seconds = 60
    penalties = (10,30)
    finish_description = '提交本批取样任务。'
    finish_feedback = ('本批尚未交回样品','本批样品已交回。')

    def observation(self):
        load = '空载' if self.state['load'] == 'empty' else '装样'
        return {**super().observation(),'instruction':f'当前在{self.state["location"]}，电量{self.state["battery"]}，{load}。本批在Q取一份样品并送回S；自动取样耗12电量。'}

    def physical_edge(self,edge):
        load = self.state['load']
        return {**self.task.world['edges'][load][edge],'load':load}

    def arrive(self,target):
        if target == 'Q' and not self.state['sampled']:
            if self.state['battery'] < 12:
                self.feedback += '；已抵达Q，但余电不足12，采样不能启动，本次结束。'
                self.end('insufficient_sampling_energy',score=0,full_credit=False)
                return
            self.state['battery'] -= 12
            self.state['time_s'] += 60
            self.state.update(sampled=True,has_sample=True,load='loaded',sampling_completed_s=self.state['time_s'])
            self.feedback += '；自动取样已完成，扣电12，现为装样模式。'
        elif target == 'S' and self.state['has_sample']:
            self.state.update(closed=True,has_sample=False,load='empty')
            self.feedback += '；样品已交接卸下，本批成果已锁定。'


def reconstruct(history,current):
    departures,edges = {},{'empty':{},'loaded':{}}
    statuses = {'测线入口岩块封堵，仍在原节点':'blocked',
                '发生侧滑，已自动恢复，抵达目标':'hazard','正常抵达目标':'normal'}
    outcomes = '('+'|'.join(statuses)+')'
    for text in paragraphs(history):
        receipt = re.fullmatch(r'标定([LH]\d+)（(空载|装样)）：([SABQ])前往([SABQ])，边(e[1-6])，距离(\d+)米。(.+)',text)
        if not receipt:
            continue
        journey,printed_load,source,target,edge,distance,reading = receipt.groups()
        load = {'空载':'empty','装样':'loaded'}[printed_load]
        topology = edge_between(current['topology'],source,target)
        if topology is None or topology['id'] != edge or topology['distance_m'] != int(distance):
            raise ValueError('Calibration receipt edge and endpoints must match the public topology')
        identity = (source,target,edge)
        departure = re.fullmatch(r'行程出发，余电(\d+)。',reading)
        if departure:
            departures[load,journey] = (identity,int(departure[1]))
            continue
        direct = re.fullmatch(outcomes+r'；实际耗电(\d+)。',reading)
        difference = re.fullmatch(r'(?:出发余电(\d+)，)?'+outcomes+r'；本次补能(\d+)，停靠余电(\d+)。'
                                  r'(?:本次第二次抵Q，行程到达后一秒补能完成；所报停靠余电为补能后读数。)?',reading)
        if direct:
            energy,status = int(direct[2]),statuses[direct[1]]
        elif difference:
            if difference[1] is None:
                departure_identity,before = departures[load,journey]
                if departure_identity != identity:
                    raise ValueError('Each calibration receipt must match its same-load journey departure')
            else:
                before = int(difference[1])
            energy,status = before-int(difference[4])+int(difference[3]),statuses[difference[2]]
        else:
            raise ValueError('Calibration receipt needs an actual outcome and energy reading')
        physical = {'energy':energy,'status':status}
        by_load = edges[load]
        if energy <= 0 or edge in by_load and by_load[edge] != physical:
            raise ValueError('Same-load bidirectional road costs and conditions must stay stable')
        by_load[edge] = physical
    for load in edges:
        if set(edges[load]) != {edge['id'] for edge in current['topology']}:
            raise ValueError('All edges require independent calibration in both load modes')
    return {'edges':edges,'minimum_safe_energy':minimum_energy(current['topology'],edges)}


def next_action(facts,current):
    state = current['state']
    if state['closed']:
        return {'action':'finish'}
    _,path = safe_path(current['topology'],facts['edges'][state['load']],state['location'],'S' if state['has_sample'] else 'Q')
    return {'action':'move','to':path[0]}


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Round-trip minimum and both load costs must come from the calibration receipts')


def audit_cases(task,facts,solution):
    cases = []
    minimum = facts['minimum_safe_energy']
    for out in BRANCHES.values():
        for back in BRANCHES.values():
            path = out+list(reversed(back))[1:]
            energy,hazards = 12,0
            for load,leg in (('empty',out),('loaded',list(reversed(back)))):
                for source,target in zip(leg,leg[1:]):
                    physical = facts['edges'][load][edge_between(task.public['topology'],source,target)['id']]
                    energy += physical['energy']
                    hazards += int(physical['status'] == 'hazard')
            score = max(0,100*min(1,minimum/energy)-30*hazards)
            cases.append(([{'action':'move','to':n} for n in path[1:]]+[{'action':'finish'}],score))
    cases.extend([(solution[:-2]+[{'action':'end'}],0),([{}]*18,0),([{'action':'finish'}]*18,0),
                  ([{}]*(18-len(solution))+solution,100)])
    return cases
