"""FM-E1-P1: retrieve the standard for the complete observed survey condition."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

# Focus, current, main presets, other device/phase, contrast, recent/frequent fit, answer.
CONFIGS = (
    ('recent','A阴低连',(3,6),4,9,1,False,True,6),
    ('recent','A阴低连',(6,3),4,9,1,False,True,3),
    ('frequency','A日低连',(8,1),9,4,2,True,False,8),
    ('frequency','A日低连',(1,8),9,4,2,True,False,1),
    ('phase','A阴低连',(7,10),8,3,'phase',True,True,10),
    ('phase','A阴低连',(7,3),8,10,'phase',True,True,3),
    ('frequency','A阴低连',(2,7,5,9),3,8,1,False,False,5),
    ('frequency','A阴低连',(5,7,2,9),3,8,1,False,False,2),
    ('device','A日低启',(4,9,7,1),5,10,'device',True,True,4),
    ('device','A日低启',(5,9,7,1),4,10,'device',True,True,5),
    ('phase','B日暖连',(2,7,5,9),3,8,'phase',True,True,7),
    ('phase','B日暖连',(2,8,5,9),3,7,'phase',True,True,8),
    ('frequency','B阴暖连',(8,2,4,7,10,5,1,9),3,None,6,False,False,9),
    ('frequency','B阴暖连',(8,2,4,7,10,9,1,5),3,None,6,False,False,5),
    ('device','A阴低启',(8,2,4,7,10,5,1,9),3,None,'device',False,False,10),
    ('device','A阴低启',(8,2,4,7,3,5,1,9),10,None,'device',False,False,3),
)
# Authored per pair; no target-condition insertion or difficulty/device slot rule.
REGISTRATION_ORDERS = (
    ('B阴低连','A日低连','A阴低启','A阴低连'),
    ('A日低连','A日低启','A阴低连','B日低连'),
    ('A日低连','A阴低连','B阴低连','A阴低启'),
    ('A阴暖连','B阴低连','A日低连','A阴低启','A日暖连','A阴低连'),
    ('A日暖启','A日低连','A日低启','A阴暖启','B日低启','A阴低启'),
    ('B阴低连','B日暖启','B日低连','A日暖连','B日暖连','B阴暖连'),
    ('B日暖连','B阴暖连','B阴低启','A阴暖连','B日低连','B阴暖启','B日暖启','B日低启','B阴低连'),
    ('A阴暖连','A日低启','B阴低启','A阴低连','A日暖启','A阴暖启','A阴低启','A日低连','A日暖连'),
)
MENUS = (
    (2,5,6,3,9,7,8,10,4,1),(7,8,5,4,3,10,1,6,2,9),(1,4,9,6,5,10,2,3,7,8),
    (4,10,5,8,2,3,6,9,1,7),(9,8,5,2,6,7,3,10,1,4),(9,5,8,2,6,4,7,1,3,10),
    (3,5,1,10,9,6,8,4,2,7),(5,6,9,1,7,10,4,8,2,3),
)
MINUTES = (1,2,3,4,5,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,38,40,42,44,46,47,48,49,50)
FIELDS = ('instrument','illumination','temperature_band','phase')


def _condition(code):
    return dict(zip(FIELDS,(code[0],{'日':'日照','阴':'阴影'}[code[1]],{'低':'低温','暖':'较暖'}[code[2]],{'启':'启动','连':'连续'}[code[3]]),strict=True))


def _key(condition):
    return tuple(condition[k] for k in FIELDS)


def _program(number):
    return f'P{number:02d}'


def build(index):
    focus,current_code,presets,other_device,other_phase,contrast,recent_fit,frequent_fit,correct = CONFIGS[index]
    instrument,light,temp,phase = current_code
    pairs = ('日低','阴低') if index < 6 else ('日低','日暖','阴低','阴暖')
    main = [instrument+p+phase for p in pairs] if index < 12 else [instrument+p+s for p in pairs for s in '启连']
    device_code = ('B' if instrument == 'A' else 'A')+light+temp+phase
    phase_code = instrument+light+temp+('连' if phase == '启' else '启')
    mapping = dict(zip(main,(_program(p) for p in presets),strict=True))
    mapping[device_code] = _program(other_device)
    if other_phase is not None:
        mapping[phase_code] = _program(other_phase)
    contrast_code = main[contrast-1] if isinstance(contrast,int) else device_code if contrast == 'device' else phase_code
    frequent = current_code if frequent_fit else contrast_code
    recent = current_code if recent_fit else next(c for c in main if c not in (current_code,contrast_code)) if focus == 'frequency' else contrast_code
    rounds = (6,10,14,18) if index < 6 else (6,9,12,15,18,20) if index < 12 else (5,7,9,11,13,15,17,19,21)
    times = [clock(f'08:{minute:02d}') for minute in MINUTES]
    history = History(times=times)

    def add(at,text,**facts):
        history.add(at,text,occurred=times[at-1],received=times[at-1],**facts)

    add(1,'勘察仪A/B均支持十套存储参数P01—P10，调用即执行测量，编号不含冷热、优劣或顺序含义。'
          '使用对应仪器、完整光照和温区、测量阶段下已经登记的标准方案。每个适用条件的标定分别保存并持续有效，'
          '不同条件的新记录不撤销旧条件；每条标定均已实际测量并通过验收，不是未执行的建议。'
          '当前四元条件由观测系统直接提供，无需识图或推断温度阈值，设备与测量准备已完成。'
          '十项都可实际调用，错误方案也执行；有效无效共3次，首有效选择即结束，end放弃。推理与检索不推进故事时间。',event='survey_experience_protocol')

    def measurement(at,code,registration):
        condition = _condition(code)
        text = '、'.join(condition.values())+f'，使用{mapping[code]}实际测量通过验收。'
        add(at,text+('登记为此完整条件的标准方案。' if registration else '再次完成该条件的成功测量，标准方案不变。'),
            event='calibration_registered' if registration else 'measurement_completed',condition=condition,program=mapping[code],accepted=True)

    for at,code in zip(rounds,REGISTRATION_ORDERS[index//2],strict=True):
        measurement(at,code,True)
    for at in (22,23,24,25):
        measurement(at,frequent,False)
    for at in (27,29):
        measurement(at,recent,False)
    add(30,'已到达N28，准备下一次勘察测量。',event='survey_ready',location='N28')
    group = f'FM-E1-P1-pair{index//2+1:02d}'
    task = task_shell('FM-E1-P1',index,group=group,background_group=group,current_input_group=group)
    current = _condition(current_code)
    task.public = {'time_s':clock('09:00'),'location':'N28','condition':current,'equipment_ready':True,'max_steps':3,'state_fields':[],
                   'instruction':'第120日09:00，地点N28，当前'+ '、'.join(current.values())+'；设备与测量准备已完成。请选择下一步操作。',
                   'actions':fixed_options([{'operation':{'program':_program(p)},'description':f'用{_program(p)}执行当前仪器一次测量。'} for p in MENUS[index//2]])}
    task.initial = {'time_s':clock('09:00'),'measurements':[]}
    standards = sorted(({'condition':_condition(c),'program':p} for c,p in mapping.items()),key=lambda r:_key(r['condition']))
    task.world = {'standards':standards,'correct_operation':{'program':_program(correct)}}
    task.rubric = {'score':'100 for the registered standard of the full current instrument/light/temperature/phase condition'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        accepted = operation == self.task.world['correct_operation']
        self.state['measurements'].append({'location':self.task.public['location'],'condition':self.task.public['condition'],
                                           'program':operation['program'],'accepted':accepted,'performed_s':self.state['time_s']})
        self.feedback = '操作已执行，记录已存档。'
        return 100 if accepted else 0


def reconstruct(history,current):
    standards = {}
    repetitions = []
    for text in paragraphs(history):
        receipt = re.fullmatch(r'([AB])、(日照|阴影)、(低温|较暖)、(启动|连续)，使用(P\d+)实际测量通过验收。'
                               r'(登记为此完整条件的标准方案。|再次完成该条件的成功测量，标准方案不变。)',text)
        if not receipt:
            continue
        record = {'condition':dict(zip(FIELDS,receipt.groups()[:4],strict=True)),'program':receipt[5]}
        if receipt[6].startswith('登记'):
            key = _key(record['condition'])
            if key in standards and standards[key]['program'] != record['program']:
                raise ValueError('Stable condition has contradictory registered programs')
            standards[key] = record
        else:
            repetitions.append(record)
    if any(standards[_key(r['condition'])]['program'] != r['program'] for r in repetitions):
        raise ValueError('Repeated successful measurements disagree with their stable condition')
    ordered = [standards[k] for k in sorted(standards)]
    return {'standards':ordered,'correct_operation':{'program':standards[_key(current['condition'])]['program']}}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Survey preset differs from the full public condition and its stable calibration')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
