"""FM-R3-P2: reuse one complete calibration curve for the unchanged head and fixture."""
import re
from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Head, fixture, target order, independently authored target/distractor curves, new reading.
CONFIGS = (
    ('H1','F1',1,(2,3,1,13),(3,1,2,11),4),
    ('H1','F1',2,(3,2,2,12),(2,4,1,14),12),
    ('H2','F1',2,(2,4,3,-6),(1,6,4,-24),10),
    ('H1','F2',1,(3,0,1,20),(2,2,4,-18),18),
    ('H3','F2',1,(1,2,3,-18),(2,1,1,11),11),
    ('H2','F2',2,(4,3,1,33),(3,5,2,15),6),
    ('H3','F1',1,(3,1,4,-9),(2,6,1,16),7),
    ('H1','F2',1,(4,2,2,22),(3,4,4,-6),10),
    ('H2','F1',2,(1,3,3,-17),(2,5,4,-15),17),
    ('H1','F1',2,(3,5,1,25),(4,1,2,21),5),
    ('H1','F2',2,(2,2,4,-18),(3,4,1,24),15),
    ('H1','F1',2,(1,0,3,-20),(2,3,4,-17),8),
    ('H3','F2',1,(2,5,3,-5),(3,0,2,10),16),
    ('H2','F2',2,(4,6,2,26),(3,6,4,-4),10),
    ('H1','F2',1,(2,3,1,13),(1,6,2,-4),20),
    ('H1','F1',1,(1,5,2,-5),(2,2,1,12),10),
)


def calibrated_value(curve,reading):
    return curve['a']*reading+curve['b'] if reading <= 10 else curve['c']*reading+curve['d']


def build(index):
    head,fixture,target_order,target,distractor,reading = CONFIGS[index]
    other_fixture = 'F2' if fixture == 'F1' else 'F1'
    jobs = {f'J{number:02d}':{'id':f'J{number:02d}','head':head,'fixture':fixture if number == target_order else other_fixture,
        'input_fixed':True,'energy':18,'coefficients':dict(zip('abcd',target if number == target_order else distractor,strict=True))}
        for number in (1,2)}
    history = History()
    history.add(1,'正确给出当前读数对应进给量，同时节省取样标定计算能源。H1/H2/H3为不同取样头，F1/F2为不同机械夹持装配；每个(头,F)有独立固定标定输入。'
        'r为0—20无量纲整数码，y为题内标定进给单位。连续两段曲线：r≤10时y=a·r+b，r>10时y=c·r+d，d=b+10(a−c)。'
        '两种夹持影响零点和传动响应，没有哪一种必定输出较大；高段负截距不意味着进给无效，r=0允许零进给。'
        '头/夹持和标定包相同则旧曲线可复用，按新r乘加不算重新解算；旧测点的单个输出不能替代新r结果。'
        '当前能源24，历史求解费不扣当前能源；当前输入不含原始标定包或曲线系数，不能仅从r恢复曲线。原生记忆检索不计环境动作。'
        'get_steps访问当前组合完整固定包，成功实扣18并给u1=1,v1=a−1,u2=0,v2=b,u3=0,v3=c，'
        '求解a=u1+v1,b=u2+v2,c=u3+v3,d=b+10(a−c)，再按r所在段计算。只返回当前组合，不给其他头/夹持的曲线。'
        '成功请求重复计费，余额不足18不调用、不扣费、不返回任何输入，但占一次调用。'
        '须正确提交调校量，并尽量减少当前实际计算耗能；无需提交工单号或解释推导过程。'
        'submit的顶层value须为单个有限JSON数值，等值十进制和科学计数接受，数组、布尔、字符串、算式、非有限值均为格式错误。'
        '首次有效数值提交立即终止，无论正误均不能重答，反馈不报得分；提交调校量不表示已经取样或配置设备。'
        '最多4次总调用，含无效格式、能源不足、get_steps、submit及end。get_steps/end只含action，submit只含action/value，不能用parameters包装；'
        '未知动作、额外字段或错误结构只报请求格式无效，不扣能源但占额度。end或耗尽无有效提交0，已付费不退。',
        event='sampling_calibration_protocol',initial_energy=24,computation_energy=18,max_actions=4,reading_range=[0,20],breakpoint=10)
    history.add(2,'H1、H2、H3标识三个独立物理取样头，F1、F2标识两种夹持装配；标定身份必须同时包含头和夹持，每个组合的原始包固定。',
        event='sampling_calibration_identities',heads=['H1','H2','H3'],fixtures=['F1','F2'])
    starts = {'J01':6,'J02':21} if index < 6 else ({'J02':4,'J01':10} if index < 12 else {'J01':3,'J02':8})
    configured = {'J02':11,'J01':14}
    low_results = {'J01':16,'J02':23} if index < 12 else {'J02':17,'J01':22}
    high_results = {'J02':18,'J01':26} if index < 12 else {'J01':19,'J02':27}
    for at in range(3,29):
        for identifier,job in jobs.items():
            if at == starts[identifier]:
                text = f'{identifier}登记取样头{head}'
                if index < 6:
                    coefficients = job['coefficients']
                    history.add(at,text+f'、夹持{job["fixture"]}，输入包固定，已耗18求解并通过完整验证，'
                        f'低段a={coefficients["a"]}、b={coefficients["b"]}；高段c={coefficients["c"]}、d={coefficients["d"]}。',
                        event='sampling_calibration_succeeded',**job,verified=True)
                elif index < 12:
                    history.add(at,text+f'、夹持{job["fixture"]}，输入包固定，已耗18开始求解。',
                        event='sampling_calibration_started',**{k:v for k,v in job.items() if k != 'coefficients'})
                else:
                    history.add(at,text+'。',event='sampling_calibration_job',id=identifier,head=head)
            if index >= 12 and at == configured[identifier]:
                history.add(at,f'{identifier}补充夹持{job["fixture"]}，该组合输入包固定，已耗18开始求解。',
                    event='sampling_calibration_started',id=identifier,fixture=job['fixture'],input_fixed=True,energy=18)
            if index >= 6:
                for segment,round_number,keys in (('low',low_results[identifier],'ab'),('high',high_results[identifier],'cd')):
                    if at == round_number:
                        coefficients = '、'.join(f'{key}={job["coefficients"][key]}' for key in keys)
                        history.add(at,f'{identifier}的'+('低段' if segment == 'low' else '高段')+f'标定结果已成功验证，系数为{coefficients}。',
                            event='sampling_calibration_result',id=identifier,segment=segment,
                            coefficients={k:job['coefficients'][k] for k in keys},verified=True)
        if at == (12 if index < 6 else 15):
            next_head = {'H1':'H2','H2':'H3','H3':'H1'}[head]
            history.add(at,f'另一个取样头{next_head}的装配更换仅有计划，尚未执行，不改变当前取样头与夹持。',
                event='sampling_head_change_plan',head=next_head,executed=False)
    history.add(29,'本次头/夹持及标定包未变，设备正常。',event='sampling_calibration_unchanged',head=head,fixture=fixture,input_fixed=True)
    task = task_shell('FM-R3-P2',index,current_input_group=f'FM-R3-P2-{head}-{fixture}-r{reading}')
    task.public = {'instruction':f'取样头{head}已在夹持配置{fixture}就位，装配和标定输入包与该组合上次验证时相同。当前读数r={reading}。请提交调校量。',
        'time_s':clock('09:00'),'head':head,'fixture':fixture,'reading':reading,'max_steps':4,'state_fields':['energy'],
        'actions':[{'action':'get_steps','description':'重新求解当前头/夹持的完整固定标定包，耗能18。'},
            {'action':'submit','description':'提交顶层value为单个有限数值。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':24}
    task.world = {'jobs':jobs,'curve':dict(zip('abcd',target,strict=True))}
    task.rubric = {'metric':'correct_calibration_value_times_remaining_energy_over_24','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {None:18}
    insufficient_feedback = '计算能源不足，未调用解算服务。'
    submitted_feedback = '取样调校量已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'submit':{'value':{'type':'number','required':True,'description':'单个有限JSON数值，不接受数组、字符串、布尔值或算式。'}}})

    def computation_inputs(self,scope):
        curve = self.task.world['curve']
        inputs = {'u1':1,'v1':curve['a']-1,'u2':0,'v2':curve['b'],'u3':0,'v3':curve['c']}
        return inputs,'a=u1+v1，b=u2+v2，c=u3+v3，d=b+10(a−c)；r≤10时y=a·r+b，r>10时y=c·r+d'

    def answer_credit(self,value):
        correct = value == calibrated_value(self.task.world['curve'],self.task.public['reading'])
        self.facts['value_correct'] = correct
        return 100 if correct else 0


def reconstruct(history,current):
    jobs = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(J\d+)登记取样头(H\d+)(.*)',text):
            identifier,head,detail = match.groups()
            job = jobs[identifier] = {'id':identifier,'head':head}
            if completed := re.fullmatch(r'、夹持(F\d+)，输入包固定，已耗(\d+)求解并通过完整验证，低段a=(-?\d+)、b=(-?\d+)；高段c=(-?\d+)、d=(-?\d+)。',detail):
                fixture,cost,*values = completed.groups()
                job.update(fixture=fixture,input_fixed=True,energy=int(cost),coefficients=dict(zip('abcd',map(int,values),strict=True)))
            elif started := re.fullmatch(r'、夹持(F\d+)，输入包固定，已耗(\d+)开始求解。',detail):
                job.update(fixture=started[1],input_fixed=True,energy=int(started[2]),coefficients={})
            elif detail != '。':
                raise ValueError('A calibration needs its fixed assembly and actual successful validation in prose')
        elif match := re.fullmatch(r'(J\d+)补充夹持(F\d+)，该组合输入包固定，已耗(\d+)开始求解。',text):
            identifier,fixture,cost = match.groups()
            jobs[identifier].update(fixture=fixture,input_fixed=True,energy=int(cost),coefficients={})
        elif match := re.fullmatch(r'(J\d+)的(低段|高段)标定结果已成功验证，系数为([abcd])=(-?\d+)、([abcd])=(-?\d+)。',text):
            identifier,segment,first,x,second,y = match.groups()
            if first+second != ('ab' if segment == '低段' else 'cd'):
                raise ValueError('A validated calibration segment must give its own two coefficients')
            jobs[identifier]['coefficients'].update({first:int(x),second:int(y)})
    for job in jobs.values():
        curve = job['coefficients']
        if not job['input_fixed'] or job['energy'] != 18 or curve['d'] != curve['b']+10*(curve['a']-curve['c']):
            raise ValueError('Each fixed head/fixture curve must be continuous and paid independently')
    curve = next(j['coefficients'] for j in jobs.values() if (j['head'],j['fixture']) == (current['head'],current['fixture']))
    return {'jobs':jobs,'curve':curve,'value':calibrated_value(curve,current['reading'])}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','curve')):
        raise ValueError('Both calibration segments must retain the same actual head, fixture and work order')


def audit_cases(task,facts,solution):
    cases = []
    for count in range(4):
        prefix = [{'action':'get_steps'}]*count
        for value in (facts['value'],facts['value']+1):
            cases.append((prefix+[{'action':'submit','value':value}],(100 if count == 0 else 25) if value == facts['value'] else 0))
    other = next(j['coefficients'] for j in facts['jobs'].values() if j['fixture'] != task.public['fixture'])
    return cases+[([{'action':'submit','value':calibrated_value(other,task.public['reading'])}],0),
        ([{}]*3+solution,100),([{}]*4,0),([{'action':'get_steps'}]*4,0)]
