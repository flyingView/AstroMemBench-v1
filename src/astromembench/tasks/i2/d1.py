"""FM-I2-D1: signed wheel momentum persists through motor and counter resets."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

CONFIGS = (
    ('A',(3,-1,2)),('B',(-3,1,-2)),('C',(2,1,-3)),('A',(4,-2,3)),('C',(-2,3,-2)),('A',(3,-1,-1)),
    ('B',(4,-3,2,-1)),('C',(-4,2,-1,1)),('C',(4,-2,1,-3)),('A',(3,-2,3,-1)),
    ('A',(-4,3,-3,1)),('B',(2,-3,4,-2)),('B',(4,-1,0,3,-2,1)),('A',(2,-4,0,3,1,-2)),
    ('C',(5,-2,0,1,-3,2)),('A',(-4,3,0,-2,1,1)),
)
DELTAS = (0,-4,3,-5,1,-2,4,-3,2,-1)
# Actual independent-axis receipts at R07 and R21, authored per case.
OTHER_AXIS_DELTAS = (
    (1,-2),(3,-1),(1,-3),(-4,2),(4,-1),(-5,2),(3,-2),(-3,2),
    (4,-2),(-3,1),(2,-1),(5,-2),(-2,1),(-4,1),(3,-1),(-3,1),
)


def build(index):
    target,sequence = CONFIGS[index]
    u,v = ['ABC'[('ABC'.index(target)+n)%3] for n in (1,2)]
    momentum = dict.fromkeys('ABC',0)
    history = History()
    history.add(1,'三个独立实验轴轮A/B/C初始角动量为0，单位mN·m·s；各轮的正负方向固定于惯性参考，整题不改。'
        '实际ΔH按符号相加，反向操作和真实卸载都必须计入；请求、候选计划不是已发生量。'
        '关电机、重新使能、软件计数器归零均无角动量变化。此理想模型中轴承摩擦与外扰为0，轮会继续惯性旋转。'
        '当前任务使目标轮净角动量尽量接近0，目标是完全消除残余角动量。'
        '这是本题离散质量模型，不代表真实系统通用容差。'
        '当前十程序准确向目标轮施加−5至+4的ΔH；底层已标定成对推力器维持舱体姿态，将指定角动量交换到外部，不改变其他轴。'
        '任一合法程序均执行5秒，恒定等效力矩为ΔH/5 mN·m；零程序保持、不点火，也占5秒窗口。'
        '没有当前角动量或轮速查询，也不能小步试探后修正。提交select和字符串option或end，最多3次总调用含格式错误与合法选择。'
        '额外字段、数值型或范围外编号无效；首次合法选择即执行并结束，错误卸载也不能重选。',
        event='wheel_momentum_protocol',units='mN*m*s',reference='fixed_inertial',friction=0,disturbance=0,window_seconds=5)
    history.add(2,'A/B/C三轮初始H均0。十个完整程序U−5至U+4的数值就是施加的有符号ΔH，U0保持且不点火。',
                event='wheel_initial',angular_momentum=momentum,program_deltas=list(range(-5,5)))
    rounds = (4,13,23) if index < 6 else (4,11,18,25) if index < 12 else (3,8,13,18,23,27)
    du,dv = OTHER_AXIS_DELTAS[index]
    receipts = [(7,u,du,du),(21,v,dv,dv)]
    for ordinal,(at,actual) in enumerate(zip(rounds,sequence,strict=True)):
        requested = actual+(1 if actual > 0 else -1) if index >= 6 and ordinal == 0 else 1 if index >= 12 and ordinal == 2 else actual
        receipts.append((at,target,requested,actual))
    for at,wheel,requested,actual in sorted(receipts):
        momentum[wheel] += actual
        note = '联锁未使能，实际无变化。' if actual == 0 else '提前结束，仅完成所报实际ΔH。' if requested != actual else '实际变化已完成。'
        history.add(at,f'轴轮{wheel}，沿固定惯性正方向计量：请求ΔH={requested:+d}，实际ΔH={actual:+d} mN·m·s。{note}',
                    event='wheel_momentum_receipt',wheel=wheel,requested_delta=requested,actual_delta=actual,reference='fixed_inertial')
    if index >= 6:
        history.add(15,f'候选计划向轴轮{target}施加ΔH=+1，尚未执行，没有力矩作用。',
                    event='wheel_momentum_plan',wheel=target,planned_delta=1,executed=False)
    history.add(20,f'关闭后重新使能轴轮{target}电机，没有外部卸载或力矩作用；轮保持惯性旋转。',
                event='wheel_motor_cycle',wheel=target,momentum_changed=False)
    history.add(29,'软件指令计数器清零，无力矩作用，不改变任何轮的物理角动量。',event='wheel_counter_reset',momentum_changed=False)
    history.add(30,f'轴轮{target}与卸载装置接口正常就位。',event='wheel_ready',wheel=target)
    entries = [{'description':f'执行ΔH={delta:+d} mN·m·s的5秒程序。' if delta else '保持5秒，不点火。',
                'operation':{'action':'unload','delta_H':delta}} for delta in DELTAS]
    task = task_shell('FM-I2-D1',index)
    task.public = {'instruction':f'巡航保障窗口已经打开，轴轮{target}及卸载装置正常。请提交本窗口操作。',
                   'target':target,'time_s':clock('09:00'),'max_steps':3,'state_fields':[],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'angular_momentum':momentum,'window_completed':False,
                    'thrusters_fired':False,'applied_delta':0,'equivalent_torque':0,'external_exchange_delta':0}
    task.world = {'angular_momentum':momentum,'zeroing_delta':-momentum[target]}
    task.rubric = {'score':'100*max(0,1-abs(final target wheel momentum)/2)'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def invalid(self):
        self.feedback = '格式无效，请使用当前菜单编号。'

    def submit(self,action):
        super().submit(action)
        if action == {'action':'end'}:
            self.feedback = '本窗口已结束。'

    def execute(self,operation):
        target,delta = self.task.public['target'],operation['delta_H']
        self.state['angular_momentum'][target] += delta
        self.state.update(time_s=self.state['time_s']+5,window_completed=True,thrusters_fired=delta != 0,
                          applied_delta=delta,equivalent_torque=delta/5,external_exchange_delta=-delta)
        self.feedback = '卸载窗口执行完毕，记录已存档。'
        return 100*max(0,1-abs(self.state['angular_momentum'][target])/2)


def reconstruct(history,current):
    momentum = {}
    for text in paragraphs(history):
        initial = re.match(r'A/B/C三轮初始H均([+-]?\d+)。',text)
        receipt = re.match(r'轴轮([ABC])，沿固定惯性正方向计量：请求ΔH=([+-]\d+)，实际ΔH=([+-]\d+) mN·m·s。',text)
        if initial:
            momentum = dict.fromkeys('ABC',int(initial[1]))
        elif receipt:
            wheel,requested,actual = receipt[1],int(receipt[2]),int(receipt[3])
            if abs(actual) > abs(requested) or actual*requested < 0:
                raise ValueError('Partial execution must preserve the requested inertial direction')
            momentum[wheel] += actual
    if set(momentum) != set('ABC'):
        raise ValueError('All three independent wheels need initial angular momentum')
    return {'angular_momentum':momentum,'zeroing_delta':-momentum[current['target']]}


def next_action(facts,current):
    return decision_command(current,{'action':'unload','delta_H':facts['zeroing_delta']})


def check_world(task,facts):
    if facts != task.world or facts['angular_momentum'] != task.initial['angular_momentum']:
        raise ValueError('Wheel state must accumulate signed actual changes without software resets')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*max(0,1-abs(facts['angular_momentum'][task.public['target']]+op['delta_H'])/2))
