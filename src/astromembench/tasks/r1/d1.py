"""FM-R1-D1: four real thermal slots, including active temperature holding."""
from itertools import product
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp
from ..common import History, clock, task_shell
from ..prose import STORY_STAMP, microseconds, paragraphs

SEQUENCES = tuple(''.join(modes) for modes in product('HCM', repeat=4))
DELTA = {'H':1,'C':-1,'M':0}
CONFIGS = (
    (20,4,8,1,2,3),(20,7,4,1,2,5),(22,9,3,1,2,3),
    (21,6,4,2,2,6),(22,8,4,2,2,5),(20,3,10,1,3,4),
    (20,4,5,2,3,4),(22,10,3,2,3,4),(21,5,9,1,2,3),
    (21,9,7,3,2,7),(21,8,3,1,1,2),(22,8,2,1,1,3),
    (21,12,7,2,4,8),(21,6,10,2,3,5),(22,7,9,2,3,5),(20,6,10,1,4,6),
)
MODEL = (
    '离散合成热控：每槽60秒，共四槽。H补偿散热后净升1℃，C不主动加热、净降1℃，M补偿散热、温度不变；三档均耗电。'
    '槽内单调变化，M恒定，无比端点更极端的瞬态；全程必须在闭区间[19,22]℃，末温回到初温。'
    'H的实耗按槽前温度分为≤20℃的L和≥21℃的Hc，C各允许温度实耗d，M实耗m。'
    '相邻不同模式另耗s，任意方向相同；初始无前驱模式，第一槽不收切换费。切换即时、温度不变。'
    '费用均为正且稳定，是包含控制器和循环部件的实测总量，模式号或热功率不能代替电量。'
    '每槽先检查拟到达温度，越界则保护拒绝该槽及相应切换，不扣两者费用且不推进时间，保留先前已发生状态并结束。'
    '温度合法才先扣切换费、再扣槽费；足额才完成对应步骤，完整槽才推进温度和60秒。'
    '不足耗尽到0并结束，未完成步骤不推进温度或时间；余电恰好等于费用也能完成。'
    'cycle(sequence)一次自动执行完整四槽，H/C/M四字符的全部81程序均可选，不能中途改选、等待、免费测功耗、补能、回滚或重试。'
    '四槽完成但末温不等于初温也未完成本周期保障目标。'
)


def slot_cost(mode, temperature, world):
    if mode == 'H':
        return world['L'] if temperature <= 20 else world['Hc']
    return world['d'] if mode == 'C' else world['m']


def feasible_costs(initial_temperature, world):
    costs = {}
    for sequence in SEQUENCES:
        temperature, energy, previous = initial_temperature, 0, None
        for mode in sequence:
            after = temperature+DELTA[mode]
            if not 19 <= after <= 22:
                break
            energy += slot_cost(mode,temperature,world)
            if previous is not None and previous != mode:
                energy += world['s']
            temperature,previous = after,mode
        else:
            if temperature == initial_temperature:
                costs[sequence] = energy
    return costs


def build(index):
    initial,low,high,cool,switch,hold = CONFIGS[index]
    world = {'L':low,'Hc':high,'d':cool,'s':switch,'m':hold}
    history = History()
    history.add(1,'保障本周期热稳定并合理用电。'+MODEL+
        '严格使用actions中的参数，不附理由。总3次调用含格式错误、有效程序和end；非法不改状态，首个有效程序或end即终止。',
        event='thermal_protocol',allowed_temperature_c=[19,22],slots=4,slot_duration_s=60,max_actions=3)
    history.add(2,'每次标定均由试验台独立完成指定温度、初始模式及电池500的设置，容量600；不接续上批温度或余电。'
        '单槽已经选定该模式，不另含切换费。切换单独实测、即时完成且温度不变。复位在启动前一秒完成，'
        '需要补能时在试验完成后一秒补入；实际发生与接收时刻分别记录。标定台复位和补能不是当前可用动作。',
        event='thermal_calibration_setup',initial_battery=500,capacity=600,independent_trials=True)
    trials = (
        (20,'H',None),(21,'H',None),(20,'C',None),(20,'C','H'),
        (20,'H','C'),(19,'H',None),(21,'H',None),(22,'C',None),
        (20,'M','H'),(20,'C','M'),(20,'M',None),(21,'M',None),
    )
    for j,(before,mode,source) in enumerate(trials,1):
        kind = 'switch' if source is not None else 'slot'
        duration = 0 if kind == 'switch' else 60
        cost = switch if kind == 'switch' else slot_cost(mode,before,world)
        after_temperature = before if kind == 'switch' else before+DELTA[mode]
        start_round = j+2 if index >= 12 else j+1
        started = clock(f'08:{start_round:02d}:{2*j:02d}')
        completed = started+duration
        recharge = 8 if index >= 12 and j in (2,7) else 0
        received = clock(f'08:{start_round+1:02d}:{2*j:02d}')+int(recharge > 0)
        identity = {'journey':f'J{j:02d}','kind':kind,'mode':mode}
        if source is not None:
            identity['source_mode'] = source
        timing = {'reset_s':started-1,'started_s':started}
        clock_text = f'复位时刻{story_timestamp(started-1)}，启动时刻{story_timestamp(started)}'
        title = f'{source}→{mode}即时切换' if source else f'已选定{mode}模式执行60秒单槽'
        if index >= 12:
            history.add(j+2,f'独立标定J{j:02d}：复位已完成，初温{before}℃，电量500；{title}，现在启动。'
                f'{clock_text}；报告接收时刻{story_timestamp(started)}。',
                occurred=started,received=started,event='thermal_trial_start',**identity,**timing,
                temperature_before_c=before,battery_before=500,requested_duration_s=duration)
        facts = {'energy_used':cost,'battery_before':500} if index < 6 else {
            'battery_after':500-cost+recharge,'recharge':recharge,'recharged_s':completed+1 if recharge else None}
        if index < 12:
            facts['temperature_before_c'] = before
            facts['battery_before'] = 500
        text = f'独立标定J{j:02d}：{title}已完成，实际末温{after_temperature}℃。'
        if index < 6:
            text += f'独立初温{before}℃、初电500，实耗{cost}。'
        else:
            if index < 12:
                text += f'独立初温{before}℃、初电500。'
            text += f'本批补能{recharge}，最终电量读数{500-cost+recharge}。'
            if recharge:
                text += f'补能8发生在{story_timestamp(completed+1)}，即试验完成后一秒、报告之前，读数已包含补能。'
        text += f'{clock_text}，完成时刻{story_timestamp(completed)}；报告接收时刻{story_timestamp(received)}。'
        history.add(j+2+int(index >= 12),text,occurred=completed,received=received,
            event='thermal_trial_receipt',**identity,**timing,completed_s=completed,actual_duration_s=duration,
            temperature_after_c=after_temperature,completed=True,**facts)
    history.add(30,f'当前新周期初温{initial}℃，电量100，尚无模式，四槽均未开始。',
        event='thermal_new_cycle',temperature_c=initial,battery=100,mode=None,completed_slots=0)
    task = task_shell('FM-R1-D1',index,current_input_group=f'FM-R1-D1-T{initial}')
    task.public = {'instruction':f'当前温度{initial}℃，电量100。执行一个四槽保障周期，温度全程保持19—22℃，末温回到{initial}℃。',
        'time_s':clock('09:00'),'thermal_model':MODEL,'allowed_temperature_c':[19,22],
        'target_temperature_c':initial,'slots':4,'slot_duration_s':60,'max_steps':3,
        'state_fields':['time_s','temperature_c','battery','completed_slots','mode','cycle_complete'],
        'actions':[{'action':'cycle','sequence':sequence} for sequence in SEQUENCES]+[{'action':'end','description':'结束本周期。'}]}
    task.initial = {'time_s':clock('09:00'),'temperature_c':initial,'battery':100,'completed_slots':0,'mode':None,
                    'cycle_complete':False,'executed_sequence':None,'operations':[]}
    task.world = world
    task.rubric = {'score':'100*minimum_feasible_energy/actual_energy if all four slots complete safely and return to initial temperature; otherwise 0'}
    return history.finish(task)


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action','sequence'))

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        result = super().observation()
        result['time_s'] = self.state['time_s']
        result['current_time'] = story_timestamp(self.state['time_s'])
        if self.done:
            result['instruction'] = (f'本周期已结束；当前温度{self.state["temperature_c"]}℃，电量{self.state["battery"]}，'
                f'已完成{self.state["completed_slots"]}/4槽，目标末温{self.task.public["target_temperature_c"]}℃。')
        return result

    def end(self,reason,**grading):
        super().end(reason,**grading)
        self.feedback += f'周期完成标志：{"已完成" if self.state["cycle_complete"] else "未完成"}。'

    def _record(self,kind,completed,used,**details):
        self.state['operations'].append({'kind':kind,**details,'completed':completed,'energy_used':used,
            'temperature_c':self.state['temperature_c'],'battery_after':self.state['battery'],
            'completed_slots':self.state['completed_slots'],'time_s':self.state['time_s']})
        if kind == 'protection':
            title = f'第{details["slot"]}槽{details["mode"]}拟到达{details["proposed_temperature_c"]}℃越界，热保护拒绝该槽及相应切换'
        else:
            title = (f'{details["source_mode"]}→{details["mode"]}切换' if kind == 'switch' else f'第{details["slot"]}槽{details["mode"]}')
            title += '完成' if completed else '未完成，电量耗尽停止'
        self.feedback += (f'{title}，实际耗电{used}；温度{self.state["temperature_c"]}℃，电量{self.state["battery"]}，'
            f'已完成{self.state["completed_slots"]}/4槽，时刻{story_timestamp(self.state["time_s"])}。')

    def _perform(self,kind,mode,cost,**details):
        completed = cost <= self.state['battery']
        used = min(cost,self.state['battery'])
        self.state['battery'] -= used
        if completed:
            self.state['mode'] = mode
            if kind == 'slot':
                self.state['temperature_c'] += DELTA[mode]
                self.state['time_s'] += 60
                self.state['completed_slots'] += 1
        self._record(kind,completed,used,mode=mode,**details)
        if not completed:
            self.end('insufficient_energy',score=0,full_credit=False)
        return completed

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if (not isinstance(action,dict) or set(action) != {'action','sequence'} or action['action'] != 'cycle'
                or not isinstance(action['sequence'],str) or action['sequence'] not in SEQUENCES):
            self.invalid()
            return
        sequence = action['sequence']
        self.state['executed_sequence'] = sequence
        for i,mode in enumerate(sequence,1):
            proposed = self.state['temperature_c']+DELTA[mode]
            if not 19 <= proposed <= 22:
                self._record('protection',False,0,slot=i,mode=mode,proposed_temperature_c=proposed)
                self.end('thermal_protection',score=0,full_credit=False)
                return
            previous = self.state['mode']
            if previous is not None and previous != mode:
                if not self._perform('switch',mode,self.task.world['s'],source_mode=previous):
                    return
            if not self._perform('slot',mode,slot_cost(mode,self.state['temperature_c'],self.task.world),slot=i):
                return
        if self.state['temperature_c'] != self.task.public['target_temperature_c']:
            self.end('temperature_mismatch',score=0,full_credit=False)
            return
        self.state['cycle_complete'] = True
        energy = 100-self.state['battery']
        minimum = min(feasible_costs(self.task.public['target_temperature_c'],self.task.world).values())
        self.facts = {'sequence':sequence,'actual_energy':energy,'minimum_safe_energy':minimum}
        self.end('completed',score=100*minimum/energy,full_credit=minimum == energy)


def _trial_title(text):
    match = re.search(r'([HCM])→([HCM])即时切换|已选定([HCM])模式执行60秒单槽', text)
    if match is None:
        raise ValueError('Missing the performed thermal operation in the report')
    source, target, slot = match.groups()
    return source, target or slot


def _trial_clocks(text):
    stamps = dict(re.findall(rf'(复位|启动|完成|报告接收)时刻({STORY_STAMP})', text))
    return {name: microseconds(stamp) for name, stamp in stamps.items()}


def reconstruct(history,current):
    # Read the actual narrative. Authored event/measurement fields are neither
    # a fallback nor an oracle for the public-evidence reference solution.
    starts, measurements, seen = {}, {key:[] for key in ('L','Hc','d','s','m')}, set()
    for text in paragraphs(history):
        start = re.match(r'独立标定(J\d{2})：复位已完成，初温(\d+)℃，电量(\d+)；', text)
        if start:
            journey, before, battery = start.groups()
            clocks = _trial_clocks(text)
            if clocks['复位'] + 1_000_000 != clocks['启动'] or clocks['报告接收'] != clocks['启动']:
                raise ValueError('Thermal start report has inconsistent reset/start clocks')
            starts[journey] = (int(before), int(battery), _trial_title(text), clocks)
            continue
        receipt = re.match(r'独立标定(J\d{2})：(?!复位).*?已完成，实际末温(\d+)℃。', text)
        if receipt is None:
            continue
        journey, after = receipt.groups()
        if journey in seen:
            raise ValueError('Duplicate completed thermal trial')
        seen.add(journey)
        operation, clocks = _trial_title(text), _trial_clocks(text)
        source, mode = operation
        duration = 0 if source else 60_000_000
        if (clocks['复位'] + 1_000_000 != clocks['启动']
                or clocks['完成'] != clocks['启动'] + duration
                or clocks['报告接收'] < clocks['完成']):
            raise ValueError('Thermal completion report has inconsistent physical clocks')
        initial = re.search(r'独立初温(\d+)℃、初电(\d+)', text)
        if initial:
            before, battery = map(int, initial.groups())
        else:
            if journey not in starts:
                raise ValueError('Missing the matching thermal trial start report')
            before, battery, started_operation, started_clocks = starts[journey]
            if operation != started_operation or any(clocks[k] != started_clocks[k] for k in ('复位','启动')):
                raise ValueError('Thermal receipts must match their own independent trial')
        if int(after) != before + (0 if source else DELTA[mode]):
            raise ValueError('Thermal endpoint does not match the reported operation')
        direct = re.search(r'实耗(\d+)。', text)
        if direct:
            cost = int(direct[1])
        else:
            reading = re.search(r'本批补能(\d+)，最终电量读数(\d+)。', text)
            if reading is None:
                raise ValueError('Missing the thermal trial energy reading')
            recharge, remaining = map(int, reading.groups())
            if recharge:
                recharge_at = re.search(rf'补能{recharge}发生在({STORY_STAMP})，', text)
                if recharge_at is None or not clocks['完成'] < microseconds(recharge_at[1]) <= clocks['报告接收']:
                    raise ValueError('Recharge must occur after the completed trial and before its reading')
            cost = battery - remaining + recharge
        if source:
            key = 's'
        elif mode == 'H':
            key = 'L' if before <= 20 else 'Hc'
        else:
            key = 'd' if mode == 'C' else 'm'
        measurements[key].append(cost)
    if any(len(measurements[k]) != (4 if k == 's' else 2) or len(set(measurements[k])) != 1 or measurements[k][0] <= 0 for k in measurements):
        raise ValueError('All twelve thermal measurements must support stable positive costs')
    world = {key:values[0] for key,values in measurements.items()}
    costs = feasible_costs(current['target_temperature_c'],world)
    return {**world,'costs':costs,'minimum_safe_energy':min(costs.values())}


def next_action(facts,current):
    return {'action':'cycle','sequence':min(facts['costs'],key=facts['costs'].get)}


def check_world(task,facts):
    if any(task.world[k] != facts[k] for k in ('L','Hc','d','s','m')):
        raise ValueError('Thermal costs must follow the independent historical measurements')


def audit_cases(task,facts,solution):
    cases = [([{'action':'cycle','sequence':p}],100*facts['minimum_safe_energy']/facts['costs'][p] if p in facts['costs'] else 0) for p in SEQUENCES]
    return cases+[([{}]*3,0),([{},{}]+solution,100)]
