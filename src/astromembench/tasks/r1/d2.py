"""FM-R1-D2: maximize atomic scientific output within the actual energy budget."""
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

PROGRAMS = dict(zip((f'p{i}' for i in range(1,11)),(6,2,9,4,10,1,7,3,8,5),strict=True))
COSTS = (
    (19,7,28,13,31,4,22,10,25,16),
    (25,9,37,17,41,6,29,13,33,21),
    (26,12,30,18,38,5,22,8,34,15),
    (18,5,40,11,35,8,32,14,27,23),
)
CONFIGS = ((0,4),(3,5),(0,7),(2,9),(1,17),(3,14),(0,16),(2,15),
           (3,20),(1,29),(2,23),(1,35),(1,40),(3,35),(0,31),(2,38))
PROTOCOL = (
    '本批有且只有一次已分配的探测器采集机会，目标是在当前电量内提交尽可能多的合格光谱单元；每单元等价值、质量阈值相同。'
    '各程序完整提交G01至G0Y；表列Y是科学产出，不是能源，耗电不必随Y单调。'
    '设备、目标亮度、环境、质量门槛和仪器状态与标定一致，各程序实耗稳定并包含全部曝光、预处理、读出和落盘。'
    'observe(program)一次运行完整程序，首个有效选择即用掉本次唯一机会并结束，不能拆分或拼接曝光、试运行后重选、补能或回滚。'
    '实际费用不大于余电则扣费并原子提交全部Y，余电恰好0也成功；费用大于余电则电耗尽到0、产品未提交、有效单元0。'
    '未完成读出不会按比例交付部分产品。没有未来能源任务或预留要求，未使用电量本身不增加产出。'
    '全部十个程序始终可选，另有end退出。动作严格使用arguments字段及值；合法、非法和end合计最多3次调用，格式错误不动电量或采集机会。'
)


def units(count):
    return [f'G{i:02d}' for i in range(1,count+1)]


def build(index):
    group,budget = CONFIGS[index]
    costs = dict(zip(PROGRAMS,COSTS[group],strict=True))
    history = History()
    history.add(1,'用本次能源获得尽可能多的有效科学单元。'+PROTOCOL,
        event='spectral_protocol',program_outputs=PROGRAMS,max_actions=3)
    history.add(2,'连续标定开始，电量500、容量600。每次接续上批结束读数；历史产品按试验独立归档，不计当前新批。'
        '若有补能，发生在该次采集和落盘完成后，结束读数包含该次补能；下一试验从这个读数启动。',
        event='spectral_calibration_start',battery=500,capacity=600)
    battery = 500
    for j,(program,count) in enumerate(PROGRAMS.items(),1):
        before = battery
        recharge = (25 if j == 4 else 15 if j == 9 else 0) if index >= 12 else 0
        battery = before-costs[program]+recharge
        if index >= 12:
            history.add(j+2,f'标定J{j:02d}启动{program}，本批启动电量{before}，预期完整读出{count}单元。',
                event='spectral_trial_start',journey=f'J{j:02d}',program=program,expected_units=count,battery_before=before)
        facts = {'energy_used':costs[program]} if index < 6 else {'battery_after':battery,'recharge':recharge}
        if 6 <= index < 12:
            facts['battery_before'] = before
        text = f'标定J{j:02d}的{program}已完成采集和读出，{count}个合格单元已原子写入并归档。'
        if index < 6:
            text += f'实际耗电{costs[program]}。'
        else:
            if index < 12:
                text += f'启动电量{before}。'
            text += f'本次完成后补能{recharge}，结束电量{battery}。'
        history.add(j+2+int(index >= 12),text,event='spectral_trial_receipt',journey=f'J{j:02d}',
            program=program,qualified_units=count,units=units(count),product_committed=True,**facts)
    history.add(30,f'当前为新批，电量{budget}，一次采集机会尚未使用，当前产品为空。',
        event='spectral_new_batch',battery=budget,acquisition_used=False,units=[],product_committed=False)
    task = task_shell('FM-R1-D2',index,current_input_group=f'FM-R1-D2-B{budget}')
    task.public = {'instruction':f'当前电量{budget}，本批有一次采集机会，请提交尽可能多的合格光谱单元。',
        'time_s':clock('09:00'),'acquisition_protocol':PROTOCOL,'max_steps':3,
        'state_fields':['battery','units','product_committed','acquisition_used'],
        'actions':[{'action':'observe','program':p,'qualified_units':y} for p,y in PROGRAMS.items()]+[{'action':'end','description':'结束本批采集。'}]}
    task.initial = {'battery':budget,'units':[],'product_committed':False,'acquisition_used':False,'executed_program':None}
    task.world = {'costs':costs}
    task.rubric = {'score':'100*actual_committed_units/maximum_affordable_units; zero if no atomic product committed'}
    return history.finish(task)


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action','program'))

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        result = super().observation()
        if self.done:
            result['instruction'] = (f'本批采集已结束；当前电量{self.state["battery"]}，已提交{len(self.state["units"])}个合格光谱单元。')
        return result

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if (not isinstance(action,dict) or set(action) != {'action','program'} or action['action'] != 'observe'
                or not isinstance(action['program'],str) or action['program'] not in PROGRAMS):
            self.invalid()
            return
        program = action['program']
        cost = self.task.world['costs'][program]
        completed = cost <= self.state['battery']
        used = min(cost,self.state['battery'])
        self.state.update(battery=self.state['battery']-used,acquisition_used=True,executed_program=program)
        if completed:
            self.state.update(units=units(PROGRAMS[program]),product_committed=True)
        self.feedback = (f'{program}{"采集读出完成，产品已原子提交" if completed else "读出未完成，能源耗尽，产品未提交"}；'
            f'当前电量{self.state["battery"]}，合格单元编号{self.state["units"]}，已提交标志{self.state["product_committed"]}。')
        if not completed:
            self.end('insufficient_energy',score=0,full_credit=False)
            return
        maximum = max(y for p,y in PROGRAMS.items() if self.task.world['costs'][p] <= self.task.initial['battery'])
        count = len(self.state['units'])
        self.facts = {'program':program,'actual_energy':used,'qualified_units':count,'maximum_affordable_units':maximum}
        self.end('completed',score=100*count/maximum,full_credit=count == maximum)


def reconstruct(history,current):
    starts,costs = {},{}
    yields = {a['arguments']['program']:a['details']['qualified_units'] for a in current['actions'] if a['arguments']['action'] == 'observe'}
    for text in paragraphs(history):
        start = re.fullmatch(r'标定(J\d+)启动(p\d+)，本批启动电量(\d+)，预期完整读出(\d+)单元。',text)
        if start:
            starts[start[1]] = ((start[2],int(start[4])),int(start[3]))
            continue
        receipt = re.fullmatch(r'标定(J\d+)的(p\d+)已完成采集和读出，(\d+)个合格单元已原子写入并归档。(.+)',text)
        if not receipt:
            continue
        journey,program,printed_count,reading = receipt.groups()
        count = int(printed_count)
        if yields.get(program) != count:
            raise ValueError('Completed spectral units must match the public program output')
        direct = re.fullmatch(r'实际耗电(\d+)。',reading)
        difference = re.fullmatch(r'(?:启动电量(\d+)。)?本次完成后补能(\d+)，结束电量(\d+)。',reading)
        if direct:
            cost = int(direct[1])
        elif difference:
            if difference[1] is None:
                identity,before = starts[journey]
                if identity != (program,count):
                    raise ValueError('Spectral receipts must match their own acquisition')
            else:
                before = int(difference[1])
            cost = before-int(difference[3])+int(difference[2])
        else:
            raise ValueError('Completed spectral calibration requires an actual energy reading')
        costs[program] = cost
    if costs.keys() != yields.keys() or any(c <= 0 for c in costs.values()):
        raise ValueError('Every acquisition program needs a positive measured energy cost')
    affordable = {p:y for p,y in yields.items() if costs[p] <= current['state']['battery']}
    return {'costs':costs,'affordable':affordable,'maximum_affordable_units':max(affordable.values())}


def next_action(facts,current):
    return {'action':'observe','program':max(facts['affordable'],key=facts['affordable'].get)}


def check_world(task,facts):
    if task.world['costs'] != facts['costs']:
        raise ValueError('Acquisition costs must follow the continuous historical energy ledger')


def audit_cases(task,facts,solution):
    cases = [([{'action':'observe','program':p}],100*facts['affordable'].get(p,0)/facts['maximum_affordable_units']) for p in PROGRAMS]
    return cases+[([{}]*3,0),([{},{}]+solution,100)]
