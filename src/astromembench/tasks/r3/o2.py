"""FM-R3-O2: retained M13 repair calibration, authored directly in thirty rounds."""
from decimal import Decimal, InvalidOperation
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

OPERATIONS = {'X':'锁扣行程调校','Y':'夹持零点调校'}
CONDITIONS = {'T1':(2,0),'T2':(4,0),'T3':(2,20),'T4':(4,20)}
CHANGES = {1:((0,),(1,),(3,),(2,),(0,1)),2:((1,),(3,),(2,),(0,),(1,2)),
    3:((3,),(2,),(0,),(1,),(3,0)),4:((2,),(0,),(1,),(3,),(2,3))}
# Confusion group, complete target key, alternate condition, paid inputs, other results, target order.
CONFIGS = (
    (1,'A X F11 T1','T2',4,8,(19,),1),
    (1,'A X F11 T1','T3',7,16,(16,),2),
    (2,'B Y F11 T1','T2',28,8,(11,),2),
    (3,'C X F11 T1','T2',2,26,(35,),1),
    (3,'C X F11 T1','T3',3,4,(32,),2),
    (4,'A Y F11 T1','T3',23,8,(24,),1),
    (1,'B X F11 T3','T4',16,8,(31,6,13),2),
    (2,'C Y F11 T3','T1',3,2,(30,23,16),3),
    (2,'C Y F11 T3','T4',14,2,(23,30,5),4),
    (3,'A X F11 T3','T4',4,4,(15,22,29),1),
    (4,'B Y F11 T3','T1',13,8,(14,7,32),4),
    (4,'B Y F11 T3','T4',30,2,(7,14,21),3),
    (1,'A Y F12 T2','T1',11,3,(21,28,35,10,17),1),
    (2,'B X F12 T2','T4',7,10,(10,35,28,21,14),5),
    (3,'C Y F12 T2','T4',7,2,(34,27,20,13,6),6),
    (4,'A X F12 T2','T4',7,26,(26,19,12,5,30),2),
)


def build(index):
    group,key,other_condition,u,v,other_values,position = CONFIGS[index]
    target = key.split()
    replacements = ('BCA'['ABC'.index(target[0])],'Y' if target[1] == 'X' else 'X',
        'F12' if target[2] == 'F11' else 'F11',other_condition)
    calculations = []
    for parameter,fields in zip(other_values,CHANGES[group]):
        other = [replacements[i] if i in fields else value for i,value in enumerate(target)]
        calculations.append({'key':other,'u':parameter//2,'v':parameter-parameter//2,'parameter':parameter})
    calculations.insert(position-1,{'key':target,'u':u,'v':v,'parameter':u+v})
    history = History()
    history.add(1,'准确提交维修操作所需的调校参数，合理使用计算能源；获取操作参数计算步骤需调用星载参数解算服务，每次消耗30单位计算能源。'
        '只提交参数，不执行后续机械维修；参数使用统一题内参数单位，服务费用不是真实模型功耗或推理时间。'
        '设备A/B/C独立；X为锁扣行程调校，Y为夹持零点调校；F11是短适配器、F12是长适配器，不是新旧版本。'
        '工况T1=2kg/0℃、T2=4kg/0℃、T3=2kg/20℃、T4=4kg/20℃。设备、操作、配置、工况四字段共同组成完整标定键。'
        '同题内每个完整组合的标定输入包固定，成功参数唯一；另一个组合的成功结果不能因较新、数值大或工单号高而通用。'
        '各题独立初始化，同名键跨题不保证相同输入。历史仅给条件、工单、已获取步骤耗30及成功参数，不给输入或中间算式。'
        '当前条件与此前该组合相同，但无数值输入；可以合法检索记忆复用，不另扣环境能源。仅当前实际get_steps付费返回本组合u/v及调校参数=u+v。'
        '当前计算能源重新初始化300，历史费用不从当前再扣。每次get_steps扣30并计一次，重复仍返回同一包且重复扣费。'
        '最多4次总调用，包含有效、非法、格式错、get_steps、submit及end；当前余调用数可见。四轮内能源足够，不按余额另外判失败。'
        'submit的value直接放在action对象顶层，不用parameters包装；接受整数、有限浮点、十进制数值字符串和科学计数，如24、24.0、+2.4e1数值相等。'
        '空字符串、布尔、NaN/Infinity、多值和算式字符串不是数值，格式错占一次调用；有效但错误的数值首次提交即结束，不能按正误重试。'
        '须正确报告当前组合的调校参数，优先复用已知结果，避免重新启动付费计算服务。'
        '历史已经支付的计算费用不重复收取；当前仅实际调用服务才付费，无需解释计算过程。'
        '正确错误均反馈调校参数已接收，记录已存档；end或四轮耗尽即结束，已扣费用不退，结束后不再接受调用。'
        '合法入口仅get_steps的action、submit的action/value及end的action；未知动作、额外字段和错误结构为格式错，不调用服务。',
        event='repair_calibration_protocol',operations=OPERATIONS,conditions={name:{'load_kg':pair[0],'temperature_c':pair[1]} for name,pair in CONDITIONS.items()},
        initial_energy=300,service_cost=30,max_actions=4)
    starts = (6,20) if index < 6 else ((10,4,13,7) if index < 12 else (6,12,18,3,9,15))
    finishes = starts if index < 6 else ((18,21,24,27) if index < 12 else (22,23,24,25,26,27))
    for at in range(2,31):
        for number,(calculation,start,finish) in enumerate(zip(calculations,starts,finishes,strict=True),1):
            identifier = f'J{number:02d}'
            device,operation,configuration,condition = calculation['key']
            load,temperature = CONDITIONS[condition]
            identity = {'device':device,'operation':operation,'configuration':configuration}
            operating = {'condition':condition,'load_kg':load,'temperature_c':temperature,'input_fixed':True,'energy':30}
            if at == start:
                text = f'{identifier}：设备{device}，{operation}为{OPERATIONS[operation]}，配置{configuration}。'
                if index < 6:
                    history.add(at,text+f'工况{condition}，载荷{load}kg、温度{temperature}℃，标定输入包已固定；已获取计算步骤，耗电30。计算成功完成，调校参数{calculation["parameter"]}。',
                        event='repair_calibration_succeeded',id=identifier,**identity,**operating,parameter=calculation['parameter'])
                elif index < 12:
                    history.add(at,text+f'工况{condition}，载荷{load}kg、温度{temperature}℃，标定输入包已固定；已获取计算步骤，耗电30。',
                        event='repair_calibration_started',id=identifier,**identity,**operating)
                else:
                    history.add(at,text,event='repair_calibration_job',id=identifier,**identity)
            if index >= 12 and at == start+2:
                history.add(at,f'{identifier}：工况{condition}，载荷{load}kg、温度{temperature}℃，标定输入包已固定；已获取计算步骤，耗电30。',
                    event='repair_calibration_started',id=identifier,**operating)
            if index >= 6 and at == finish:
                history.add(at,f'{identifier}计算成功完成，调校参数{calculation["parameter"]}。',
                    event='repair_calibration_result',id=identifier,parameter=calculation['parameter'])
    load,temperature = CONDITIONS[target[3]]
    task = task_shell('FM-R3-O2',index,group=f'binding-{group}',current_input_group='FM-R3-O2-'+'-'.join(target))
    task.design['scoring_version'] = 'fm-r3-o2/6'
    task.public = {'instruction':f'请继续处理设备{target[0]}的{OPERATIONS[target[1]]}。当前配置{target[2]}，载荷{load} kg，温度{temperature}℃。'
        '装配状态、工况和标定输入与此前该组合计算时相同，设备已就位。请提交调校参数。',
        'device':target[0],'operation':target[1],'configuration':target[2],'condition':target[3],
        'load_kg':load,'temperature_c':temperature,'time_s':clock('09:00'),'max_steps':4,'state_fields':['computing_energy'],
        'actions':[{'action':'get_steps','description':'获取操作参数计算步骤'},
            {'action':'submit','description':'输入答案','parameters':{'value':'一个数值'}}]}
    task.initial = {'computing_energy':300,'step_requests':0}
    task.world = {'u':u,'v':v,'parameter':u+v,'calibrations':calculations}
    task.rubric = {'score':'100*remaining_computing_energy/initial_computing_energy if correct; otherwise 0'}
    return history.finish(task)


def numeric_value(value):
    if type(value) not in (int,float,str) or not re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?',str(value).strip()):
        return None
    try:
        number = Decimal(str(value).strip())
        return number if number.is_finite() else None
    except InvalidOperation:
        return None


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action',),{'submit':{
        'value':{'required':True,'type':'number or numeric string',
            'description':'计算得到的数值，直接放在 action 对象的 value 字段，不使用 parameters 包装。'}}})

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
        elif action == {'action':'get_steps'}:
            self.state['computing_energy'] -= 30
            self.state['step_requests'] += 1
            self.feedback = f'标定输入u={self.task.world["u"]}，v={self.task.world["v"]}；调校参数=u+v。此次耗电30，计算能源余额{self.state["computing_energy"]}。'
        elif isinstance(action,dict) and set(action) == {'action','value'} and action['action'] == 'submit' and numeric_value(action['value']) is not None:
            correct = numeric_value(action['value']) == self.task.world['parameter']
            score = 100*self.state['computing_energy']/self.task.initial['computing_energy'] if correct else 0
            self.facts.update(parameter_correct=correct,step_requests=self.state['step_requests'],spent_energy=300-self.state['computing_energy'])
            self.feedback = '调校参数已接收，记录已存档。'
            self.end('completed',score=score,full_credit=score == 100)
        else:
            self.invalid()


def reconstruct(history,current):
    jobs = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(J\d+)：设备([A-Z])，([A-Z])为([^，]+)，配置(F\d+)。(.*)',text):
            identifier,device,operation,name,configuration,operating = match.groups()
            if OPERATIONS.get(operation) != name:
                raise ValueError('A calibration identity must name its own repair operation')
            jobs[identifier] = {'device':device,'operation':operation,'configuration':configuration}
        elif match := re.fullmatch(r'(J\d+)：(工况.+)',text):
            identifier,operating = match.groups()
        elif match := re.fullmatch(r'(J\d+)计算成功完成，调校参数(-?\d+)。',text):
            jobs[match[1]]['parameter'] = int(match[2])
            continue
        else:
            continue
        if not operating:
            continue
        condition = re.fullmatch(r'工况(T\d+)，载荷(\d+)kg、温度(-?\d+)℃，标定输入包已固定；已获取计算步骤，耗电(\d+)。(?:计算成功完成，调校参数(-?\d+)。)?',operating)
        if condition is None:
            raise ValueError('A repair calibration needs its fixed conditions and paid computation in prose')
        name,load,temperature,cost,parameter = condition.groups()
        jobs[identifier].update(condition=name,load_kg=int(load),temperature_c=int(temperature),input_fixed=True,energy=int(cost))
        if parameter is not None:
            jobs[identifier]['parameter'] = int(parameter)
    keys = ('device','operation','configuration','condition')
    if any(not j['input_fixed'] or j['energy'] != 30 or CONDITIONS[j['condition']] != (j['load_kg'],j['temperature_c']) for j in jobs.values()):
        raise ValueError('Repair reuse requires complete fixed inputs and successful paid results')
    parameters = [{'key':[jobs[identifier][k] for k in keys],'parameter':jobs[identifier]['parameter']} for identifier in sorted(jobs)]
    if len({tuple(p['key']) for p in parameters}) != len(jobs):
        raise ValueError('Each repair order must carry its own distinct calibration combination')
    return {'parameters':parameters,'value':next(p['parameter'] for p in parameters if p['key'] == [current[k] for k in keys])}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    expected = [{'key':c['key'],'parameter':c['parameter']} for c in task.world['calibrations']]
    if facts['parameters'] != expected or facts['value'] != task.world['parameter']:
        raise ValueError('Repair results must match full calibration keys')


def audit_cases(task,facts,solution):
    cases = []
    for count in range(4):
        prefix = [{'action':'get_steps'}]*count
        for value in (p['parameter'] for p in facts['parameters']):
            cases.append((prefix+[{'action':'submit','value':value}],100-10*count if value == facts['value'] else 0))
    return cases+[([{}]*3+solution,100),([{'action':'get_steps'}]*4,0),([{'action':'submit','value':f'+{facts["value"]}e0'}],100)]
