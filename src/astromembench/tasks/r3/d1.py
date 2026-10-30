"""FM-R3-D1: reuse a wheel assembly's LU factors for a new correction vector."""
from fractions import Fraction
import re

from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Current assembly, order permutation, target and other assembly (l,u,v,w), current e.
CONFIGS = (
    ('K',1,(1,2,1,1),(-1,1,2,2),(7,10)),
    ('J',2,(0,1,2,2),(2,1,2,2),(5,2)),
    ('J',1,(-1,2,1,2),(1,2,1,2),(0,-4)),
    ('J',2,(1,1,1,2),(2,1,1,2),(2,8)),
    ('J',1,(0,2,1,1),(2,1,-1,2),(5,-1)),
    ('J',1,(2,2,1,1),(1,2,1,1),(-3,-5)),
    ('J',2,(1,2,2,1),(0,1,-1,2),(8,11)),
    ('J',2,(0,2,1,2),(1,1,2,1),(2,8)),
    ('J',2,(-1,2,2,1),(1,2,2,1),(10,-9)),
    ('K',2,(2,1,1,2),(0,2,-1,1),(1,-2)),
    ('J',1,(-1,1,-1,2),(0,2,1,2),(-2,8)),
    ('K',1,(2,2,2,1),(-1,2,2,1),(6,15)),
    ('K',1,(2,1,2,1),(1,2,-1,2),(4,11)),
    ('K',2,(-1,1,1,1),(1,1,1,1),(0,-4)),
    ('J',2,(1,2,1,1),(0,1,-1,2),(-4,-2)),
    ('K',1,(2,1,-1,2),(-1,1,-1,2),(5,4)),
)


def selected_factors(jobs,current):
    return next(j['factors'] for j in jobs.values() if (j['assembly'],j['geometry'],j['calibration']) ==
        (current['assembly'],current['geometry'],current['calibration']))


def allocation(factors,error):
    e1,e2 = error
    c2 = Fraction(e2-factors['l']*e1,factors['w'])
    c1 = (e1-factors['v']*c2)/factors['u']
    return [float(c1),float(c2)]


def build(index):
    assembly,permutation,target,other,error = CONFIGS[index]
    alternate = 'J' if assembly == 'K' else 'K'
    definitions = ((assembly,target),(alternate,other))
    jobs = {}
    for identifier,position in zip(('Q09','Q26'),(0,1) if permutation == 1 else (1,0),strict=True):
        obj,values = definitions[position]
        jobs[identifier] = {'id':identifier,'assembly':obj,'geometry':'S','calibration':'C','energy':30,
            'factors':dict(zip(('l','u','v','w'),values,strict=True))}
    history = History()
    history.add(1,'准确报告巡航双轴分配命令并节省计算能源；只提交命令数值，不执行轮组机动，不统计累计动量或待办调度。'
        '本题是公开归一化单位的2×2反作用轮分配模型，目标e由正常导航系统给出，G·c=e。'
        '成功分解G=L·U，L=[[1,0],[l,1]]、U=[[u,v],[0,w]]，u与w正且非零。先y1=e1、y2=e2−l·e1，再c2=y2/w、c1=(y1−v·c2)/u；代数等价求解均可。'
        '轮组几何与标定输入不变时分解可用于新目标，e改变不使G失效，也不能直接照搬旧命令。'
        '当前只给轮组、几何包S、标定C、e及能源，没有原矩阵、分解、原始标定包或旧命令，不能只由e免费恢复G。'
        '合法记忆中的成功分解可低成本回代，原生记忆检索不计环境动作；重新访问矩阵及分解服务才收取费用，简化数值运算是可控代理，不代表真实运算功耗。'
        '当前能源40，历史费用不从当前扣。get_steps每次需要30，足额才扣，返回当前指定轮组S/C原始矩阵G及分解步骤，不能免费请求另一轮组。'
        'G=[[u,v],[l·u,l·v+w]]，求解u=G11、v=G12、l=G21/u、w=G22−l·v，再按当前e回代。余额不足不调用、不扣、不返矩阵但占额度；费用不退。'
        'submit顶层value为两个有限JSON数值[c1,c2]，等值整数、小数、科学计数可接受；非有限、布尔、缺项、多项、字符串或算式为格式错。'
        '负值、0及任意较大的有限错误幅值都是有效数值；首次有效提交即结束，不能按范围筛选或正误重答。'
        '须正确给出两个分配命令，并尽量减少当前实际计算耗能，无需解释或提交工单。'
        '正确错误都反馈巡航分配命令已接收，记录已存档，不报正误。最多4次总调用，包含get_steps、submit、end、格式错及余额不足；end或额度耗尽即结束。'
        '合法请求严格为get_steps仅action、submit仅action/value、end仅action，不接受scope或parameters；未知动作、额外字段或结构错报请求格式无效，不扣能源但占额度。',
        event='allocation_reuse_protocol',initial_energy=40,service_cost=30,max_actions=4,unit='normalized')
    history.add(2,'K与J为两套独立健康轮组；几何包均名S、标定均名C，但完整输入按各自轮组绑定，不能跨对象共用。两套矩阵均可正确，命令可正负或0。',
        event='allocation_input_identities',assemblies=['K','J'],geometry='S',calibration='C',healthy=True)
    starts = {'Q09':6,'Q26':22} if index < 6 else ({'Q26':4,'Q09':10} if index < 12 else {'Q09':3,'Q26':8})
    payments = starts if index < 6 else ({'Q26':16,'Q09':17} if index < 12 else {'Q26':12,'Q09':15})
    finishes = starts if index < 6 else ({'Q26':20,'Q09':27} if index < 12 else {'Q09':20,'Q26':27})
    for at in range(3,28):
        for identifier,job in jobs.items():
            parameters = '、'.join(f'{key}={value}' for key,value in job['factors'].items())
            if at == starts[identifier]:
                if index < 6:
                    history.add(at,f'{identifier}登记轮组{job["assembly"]}、几何包S、标定C，实际已付30，分解成功，参数为{parameters}。',
                        event='allocation_decomposition_succeeded',**job)
                else:
                    identity = {k:job[k] for k in (('id','assembly','geometry','calibration') if index < 12 else ('id','assembly'))}
                    history.add(at,f'{identifier}登记轮组{job["assembly"]}'+('、几何包S、标定C。' if index < 12 else '。'),
                        event='allocation_decomposition_job',**identity)
            if index >= 6 and at == payments[identifier]:
                detail = {'geometry':'S','calibration':'C'} if index >= 12 else {}
                history.add(at,f'{identifier}'+('补齐几何包S、标定C，' if index >= 12 else '')+'实际已付30，开始矩阵分解。',
                    event='allocation_decomposition_started',id=identifier,energy=30,**detail)
            if index >= 6 and at == finishes[identifier]:
                history.add(at,f'{identifier}分解成功，参数为{parameters}。',event='allocation_decomposition_result',id=identifier,factors=job['factors'])
        if 6 <= index < 12 and at == 24:
            history.add(at,'Q26：确认收到此前同一笔已付30的登记，并非再次调用或收费。',
                event='allocation_payment_acknowledged',id='Q26',payment_s=clock('08:16'),additional_energy=0)
    history.add(28,f'拟在下一班改变轮组{assembly}安装，目前尚未执行。',event='allocation_installation_plan',assembly=assembly,executed=False)
    history.add(29,'K/J两套轮组健康，各自几何包S与标定C均未变化。',event='allocation_inputs_unchanged',assemblies=['K','J'],geometry='S',calibration='C',healthy=True)
    task = task_shell('FM-R3-D1',index,current_input_group=f'FM-R3-D1-{assembly}-{error[0]}-{error[1]}')
    task.public = {'instruction':f'本次使用轮组{assembly}，保持其原几何包S和标定C，状态正常。目标修正向量e=({error[0]},{error[1]})，请提交两个控制分配命令。',
        'time_s':clock('09:00'),'assembly':assembly,'geometry':'S','calibration':'C','healthy':True,'error':list(error),
        'formula':'G·c=e；G=L·U，L=[[1,0],[l,1]]，U=[[u,v],[0,w]]；y1=e1，y2=e2−l·e1，c2=y2/w，c1=(y1−v·c2)/u。',
        'unit':'normalized','max_steps':4,'state_fields':['energy'],
        'actions':[{'action':'get_steps','description':'付30获取当前轮组S/C原矩阵及分解步骤。'},
            {'action':'submit','description':'提交顶层value为两个有限数值[c1,c2]的分配命令。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':40}
    task.world = {'jobs':jobs,'factors':selected_factors(jobs,task.public)}
    task.rubric = {'metric':'50_per_correct_command_times_remaining_energy_over_40','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {None:30}
    answer_dimensions = 2
    insufficient_feedback = '计算能源不足，未调用分配解算服务'
    submitted_feedback = '巡航分配命令已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'submit':{'value':{'type':'array','required':True,'items':{'type':'number'},'minItems':2,'maxItems':2,
            'description':'恰好两个有限JSON数值[c1,c2]，允许负值与0；不接受字符串、布尔、算式或额外分量。'}}})

    def computation_inputs(self,scope):
        f = self.task.world['factors']
        return {'G':[[f['u'],f['v']],[f['l']*f['u'],f['l']*f['v']+f['w']]]},'u=G11、v=G12、l=G21/u、w=G22−l·v；y1=e1、y2=e2−l·e1；c2=y2/w、c1=(y1−v·c2)/u'

    def answer_credit(self,value):
        answer = allocation(self.task.world['factors'],self.task.public['error'])
        components = [v == expected for v,expected in zip(value,answer,strict=True)]
        self.facts['correct_components'] = components
        return 50*sum(components)


def reconstruct(history,current):
    jobs = {}
    parameters = r'l=(-?\d+)、u=(-?\d+)、v=(-?\d+)、w=(-?\d+)'
    for text in paragraphs(history):
        match = re.fullmatch(r'(Q\d+)登记轮组([^、。]+)(?:、几何包([^、]+)、标定([^，。]+))?([。，].*)',text)
        if match:
            identifier,assembly,geometry,calibration,tail = match.groups()
            job = jobs[identifier] = {'id':identifier,'assembly':assembly}
            if geometry is not None:
                job.update(geometry=geometry,calibration=calibration)
            success = re.fullmatch(r'，实际已付(\d+)，分解成功，参数为'+parameters+'。',tail)
            if success:
                energy,*values = map(int,success.groups())
                job.update(energy=energy,factors=dict(zip(('l','u','v','w'),values,strict=True)))
            continue
        match = re.fullmatch(r'(Q\d+)(?:补齐几何包([^、]+)、标定([^，]+)，)?实际已付(\d+)，开始矩阵分解。',text)
        if match:
            identifier,geometry,calibration,energy = match.groups()
            job = jobs[identifier]
            job['energy'] = int(energy)
            if geometry is not None:
                job.update(geometry=geometry,calibration=calibration)
            continue
        match = re.fullmatch(r'(Q\d+)分解成功，参数为'+parameters+'。',text)
        if match:
            identifier,*values = match.groups()
            jobs[identifier]['factors'] = dict(zip(('l','u','v','w'),map(int,values),strict=True))
    if any(j['energy'] != 30 or min(j['factors'][k] for k in ('u','w')) <= 0 for j in jobs.values()):
        raise ValueError('Each complete decomposition must follow a paid solve with nonsingular triangular factors')
    factors = selected_factors(jobs,current)
    return {'jobs':jobs,'factors':factors,'value':allocation(factors,current['error'])}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','factors')):
        raise ValueError('Control allocation must reuse the selected assembly and complete S/C identity')


def audit_cases(task,facts,solution):
    answer = facts['value']
    candidates = (answer,[answer[0]+1,answer[1]],[answer[0],answer[1]+1],[answer[0]+1,answer[1]+1])
    cases = []
    for count in range(4):
        for value in candidates:
            score = 50*sum(v == a for v,a in zip(value,answer))*(10 if count else 40)/40
            cases.append(([{'action':'get_steps'}]*count+[{'action':'submit','value':value}],score))
    other = next(j['factors'] for j in facts['jobs'].values() if j['assembly'] != task.public['assembly'])
    uncoupled = [task.public['error'][0]/facts['factors']['u'],task.public['error'][1]/facts['factors']['w']]
    for value in (allocation(other,task.public['error']),uncoupled):
        cases.append(([{'action':'submit','value':value}],50*sum(v == a for v,a in zip(value,answer))))
    return cases+[([{}]*3+solution,100),([{'action':'get_steps'}]*4,0)]
