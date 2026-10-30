"""FM-R1-O3: execute four physical pressure stages with real pump-switch losses."""
from copy import deepcopy
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

SEQUENCES = tuple('AAAA AAAB AABA AABB ABAA ABAB ABBA ABBB BAAA BAAB BABA BABB BBAA BBAB BBBA BBBB'.split())
CONFIGS = (
    ((3,4,5,6),(9,10,11,12),2),((5,4,9,6),(11,10,3,12),2),
    ((6,5,10,9),(12,11,4,3),2),((4,12,3,11),(10,6,9,5),2),
    ((9,6,5,4),(3,12,11,10),2),((12,3,11,10),(6,9,5,4),2),
    ((9,11,7,10),(3,5,13,4),2),((11,9,10,12),(5,3,4,6),2),
    ((3,5,5,6),(9,4,11,12),2),((5,5,3,12),(11,4,9,6),2),
    ((10,5,6,9),(4,6,7,3),2),((5,10,4,3),(11,6,10,9),2),
    ((5,9,12,4),(11,3,6,10),3),((3,8,5,12),(9,4,9,6),3),
    ((10,5,7,3),(4,6,6,9),1),((5,5,8,4),(11,3,6,10),2),
)


def program_costs(world):
    return {sequence:sum(world['stage_energy'][pump][i] for i,pump in enumerate(sequence))+
            world['switch_energy']*sum(a != b for a,b in zip(sequence,sequence[1:])) for sequence in SEQUENCES}


def build(index):
    a,b,switch=CONFIGS[index]
    world={'stage_energy':{'A':list(a),'B':list(b)},'switch_energy':switch}
    history=History()
    history.add(1,'完成本批20L补给并合理用电。两泵支路A/B已连接、锁紧、预充并检漏通过，流体、温度及压力条件与标定一致。'
        '受方累计量的四压力段为[0,5)、[5,10)、[10,15)、[15,20]L，依次各实际接收5L。'
        '每段各泵的实际能耗稳定，相邻段换泵另收一次稳定切换能耗，两个方向相同；不从泵名推费用。'
        '首段无前驱泵且两路已预充，不收切换费；连续同泵无切换费。切换循环液返回供方，净转移0L，无流体损失。'
        'transfer(sequence)一次自动完成四段，16种程序按字母顺序完整可选，不得中途换计划、查询费用、补能、撤销或重试。'
        '每个切换或5L段先扣实际能耗，足额才推进；余电恰等费用也可完成。不足则耗尽到0，在该步骤前停止，不推进未完成段。'
        '只有全部20L完成才有本批完整补给成果。精确参数见actions，另可end退出。'
        '总3次调用含非法、有效程序和end；非法不改物理状态，首个有效程序或end即结束。历史标定不计本批供液。',
        event='pump_energy_protocol',sequences=list(SEQUENCES),stage_volume_l=5,target_volume_l=20,max_actions=3)
    history.add(2,'每次标定都由试验台按同流体/温度独立设定指定压力段或切换起始支路，并调定电池500、容量600。'
        '每次均独立重置，不接续上批余电；标定调电和补能不是当前可用操作。',
        event='pump_calibration_setup',initial_battery=500,capacity=600,independent_trials=True)
    trials=[{'kind':'transfer','segment':segment,'pump':pump,'volume_l':5} for segment in range(1,5) for pump in 'AB']
    trials += [{'kind':'switch','source_pump':'A','target_pump':'B','volume_l':0},
               {'kind':'switch','source_pump':'B','target_pump':'A','volume_l':0}]
    for j,trial in enumerate(trials,1):
        cost=world['stage_energy'][trial['pump']][trial['segment']-1] if trial['kind'] == 'transfer' else switch
        recharge=5 if index >= 12 and j in (4,9) else 0
        after=500-cost+recharge
        title=(f'第{trial["segment"]}压力段，泵{trial["pump"]}供5L' if trial['kind'] == 'transfer'
               else f'{trial["source_pump"]}→{trial["target_pump"]}切换，循环液返回供方、净供液0L')
        info={'journey':f'J{j:02d}',**trial}
        if index >= 12:
            history.add(j+2,f'独立标定J{j:02d}：{title}。试验台已按本批条件独立初始化，电量500，启动。',
                        event='pump_trial_start',**{k:v for k,v in info.items() if k != 'volume_l'},
                        requested_volume_l=trial['volume_l'],battery_before=500)
        if index < 6:
            text=f'独立初始电量500，实际耗电{cost}。'
            facts={'battery_before':500,'energy_used':cost}
        else:
            text=('本批独立初始电量500。' if index < 12 else '')+f'本次补能{recharge}，结束读数{after}。'
            if recharge:
                text+='试验实际完成后、报告之前补入5，结束读数已包含补能。'
            facts={'battery_after':after,'recharge':recharge}
            if index < 12:
                facts['battery_before']=500
        history.add(j+2+int(index >= 12),f'独立标定J{j:02d}：{title}。操作已实际完成。'+text,
                    event='pump_trial_receipt',**info,completed=True,**facts)
    history.add(30,'当前新批：供方100L、受方本批0L、电量100，两支路已预充，无前驱工作泵。',
                event='pump_new_batch',supplier_l=100,receiver_l=0,battery=100,active_pump=None)
    task=task_shell('FM-R1-O3',index,current_input_group='FM-R1-O3')
    task.public={'instruction':'本批从供方100L向受方转移20L，受方本批当前0L，电量100。选择四压力段补给程序。',
                 'time_s':clock('09:00'),'stage_volume_l':5,'target_volume_l':20,
                 'pressure_segments':[{'segment':i,'from_l':5*(i-1),'to_l':5*i} for i in range(1,5)],
                 'connections':'A/B均已连接、锁紧、预充并检漏通过。','max_steps':3,
                 'state_fields':['battery','supplier_l','receiver_l','completed_segments','active_pump'],
                 'actions':[{'action':'transfer','sequence':sequence} for sequence in SEQUENCES]+[{'action':'end','description':'放弃本批补给。'}]}
    task.initial={'battery':100,'supplier_l':100,'receiver_l':0,'completed_segments':0,'active_pump':None,
                  'executed_sequence':None,'operations':[]}
    task.world=world
    task.rubric={'score':'100*minimum_actual_program_energy/actual_energy if 20L completed; otherwise 0'}
    return history.finish(task)


class Runtime(TaskRuntime):
    action_contract=ActionContract(('action','sequence'))

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        result=super().observation()
        if self.state['executed_sequence'] is not None:
            result['instruction']=f'本批补给已结束；供方剩余{self.state["supplier_l"]}L，受方本批已接收{self.state["receiver_l"]}L，电量{self.state["battery"]}。'
        return result

    def _perform(self,kind,cost,**details):
        completed=cost <= self.state['battery']
        used=min(cost,self.state['battery'])
        self.state['battery'] -= used
        volume=5 if completed and kind == 'transfer' else 0
        if completed:
            if kind == 'transfer':
                self.state['supplier_l'] -= volume
                self.state['receiver_l'] += volume
                self.state['completed_segments'] += 1
                self.state['active_pump']=details['pump']
            else:
                self.state['active_pump']=details['target_pump']
        self.state['operations'].append({'kind':kind,**details,'completed':completed,'energy_used':used,'volume_l':volume,
                                         'battery_after':self.state['battery'],'supplier_l':self.state['supplier_l'],'receiver_l':self.state['receiver_l']})
        title=(f'第{details["segment"]}段泵{details["pump"]}' if kind == 'transfer'
               else f'{details["source_pump"]}→{details["target_pump"]}切换')
        self.feedback+=f'{title}{"完成" if completed else "未完成，电量耗尽停止"}，实际转移{volume}L；电量{self.state["battery"]}，供方{self.state["supplier_l"]}L，受方{self.state["receiver_l"]}L。'
        if not completed:
            self.end('insufficient_energy',score=0,full_credit=False)
        return completed

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if (not isinstance(action,dict) or set(action) != {'action','sequence'} or action['action'] != 'transfer'
                or not isinstance(action['sequence'],str) or action['sequence'] not in SEQUENCES):
            self.invalid()
            return
        sequence=action['sequence']
        self.state['executed_sequence']=sequence
        for i,pump in enumerate(sequence):
            previous=self.state['active_pump']
            if previous is not None and previous != pump:
                if not self._perform('switch',self.task.world['switch_energy'],source_pump=previous,target_pump=pump):
                    return
            if not self._perform('transfer',self.task.world['stage_energy'][pump][i],segment=i+1,pump=pump):
                return
        energy=100-self.state['battery']
        minimum=min(program_costs(self.task.world).values())
        self.facts={'sequence':sequence,'actual_energy':energy,'transferred_l':self.state['receiver_l'],'minimum_safe_energy':minimum}
        self.end('completed',score=100*minimum/energy,full_credit=minimum == energy)


def reconstruct(history,current):
    starts,stage_costs,switch_costs={},{},{}
    for text in paragraphs(history):
        receipt=re.fullmatch(r'独立标定(J\d+)：(第[1-4]压力段，泵[AB]供5L|[AB]→[AB]切换，循环液返回供方、净供液0L)。(.+)',text)
        if not receipt:
            continue
        journey,trial,reading=receipt.groups()
        transfer=re.fullmatch(r'第([1-4])压力段，泵([AB])供5L',trial)
        switch=re.fullmatch(r'([AB])→([AB])切换，循环液返回供方、净供液0L',trial)
        start=re.fullmatch(r'试验台已按本批条件独立初始化，电量(\d+)，启动。',reading)
        if start:
            starts[journey]=(trial,int(start[1]))
            continue
        completed='操作已实际完成。'
        if not reading.startswith(completed):
            raise ValueError('Pump energy must come from an actually completed calibration trial')
        reading=reading.removeprefix(completed)
        direct=re.fullmatch(r'独立初始电量(\d+)，实际耗电(\d+)。',reading)
        difference=re.fullmatch(r'(?:本批独立初始电量(\d+)。)?本次补能(\d+)，结束读数(\d+)。'
                                r'(?:试验实际完成后、报告之前补入5，结束读数已包含补能。)?',reading)
        if direct:
            cost=int(direct[2])
        elif difference:
            if difference[1] is None:
                start_trial,before=starts[journey]
                if start_trial != trial:
                    raise ValueError('Each independently initialized pump trial must match its own receipt')
            else:
                before=int(difference[1])
            cost=before-int(difference[3])+int(difference[2])
        else:
            raise ValueError('Pump calibration requires an independently initialized energy reading')
        if cost <= 0:
            raise ValueError('Completed pump stages and switches have positive energy costs')
        if transfer:
            stage_costs[transfer[2],int(transfer[1])]=cost
        else:
            switch_costs[switch[1],switch[2]]=cost
    if set(stage_costs) != {(p,s) for p in 'AB' for s in range(1,5)} or set(switch_costs) != {('A','B'),('B','A')}:
        raise ValueError('All eight pump stages and both switching directions require measurements')
    if len(set(switch_costs.values())) != 1:
        raise ValueError('Both switching directions have the same measured energy')
    world={'stage_energy':{p:[stage_costs[(p,s)] for s in range(1,5)] for p in 'AB'},'switch_energy':switch_costs[('A','B')]}
    costs=program_costs(world)
    return {**world,'costs':costs,'minimum_safe_energy':min(costs.values())}


def next_action(facts,current):
    return {'action':'transfer','sequence':min(facts['costs'],key=facts['costs'].get)}


def check_world(task,facts):
    if any(task.world[k] != facts[k] for k in ('stage_energy','switch_energy')):
        raise ValueError('Pump and switch costs must follow the independently initialized historical trials')


def audit_cases(task,facts,solution):
    cases=[([{'action':'transfer','sequence':p}],100*facts['minimum_safe_energy']/cost) for p,cost in facts['costs'].items()]
    return cases+[([{}]*3,0),([{},{}]+solution,100)]
