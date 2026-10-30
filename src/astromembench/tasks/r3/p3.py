"""FM-R3-P3: assemble stored body inertias using current orientation and parallel axes."""
from copy import deepcopy
import re

from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Current A package, order permutation, A/B/other-A body inertias, current A/B mass/distance/orientation.
CONFIGS = (
    ('S',1,(2,5),(3,7),(5,2),(2,1,'N'),(1,2,'N')),
    ('Q',2,(2,5),(3,7),(1,8),(1,2,'N'),(3,1,'R')),
    ('Q',3,(4,1),(2,6),(2,4),(3,1,'R'),(2,0,'N')),
    ('S',1,(3,8),(5,2),(6,3),(1,3,'R'),(2,1,'R')),
    ('S',2,(1,7),(4,3),(4,9),(2,2,'R'),(1,1,'N')),
    ('Q',2,(7,2),(6,4),(3,6),(3,0,'R'),(2,2,'N')),
    ('Q',3,(2,8),(4,1),(5,3),(3,2,'N'),(2,1,'R')),
    ('S',1,(5,2),(3,9),(7,1),(2,1,'R'),(1,3,'N')),
    ('Q',2,(4,7),(6,2),(2,9),(1,2,'R'),(3,2,'R')),
    ('S',3,(1,6),(8,3),(4,2),(2,3,'N'),(2,0,'N')),
    ('Q',1,(3,9),(5,1),(6,5),(1,0,'R'),(2,3,'R')),
    ('S',1,(4,6),(1,7),(2,8),(2,1,'N'),(3,3,'N')),
    ('S',2,(7,2),(4,9),(3,6),(3,2,'R'),(2,3,'N')),
    ('S',1,(6,4),(2,7),(2,1),(1,1,'R'),(2,3,'R')),
    ('Q',1,(8,3),(1,6),(5,7),(2,2,'R'),(3,0,'R')),
    ('Q',3,(5,7),(3,2),(8,3),(3,1,'R'),(2,3,'N')),
)


def body_inertias(jobs,modules):
    return {name:next(j['inertia'] for j in jobs.values() if (j['object'],j['package']) == (name,m['package'])) for name,m in modules.items()}


def assembled_inertia(inertias,modules):
    return sum(inertias[name]['Ix' if m['orientation'] == 'N' else 'Iy']+m['mass']*m['distance']**2 for name,m in modules.items())


def build(index):
    package,permutation,a,b,other_a,installation_a,installation_b = CONFIGS[index]
    other_package = 'Q' if package == 'S' else 'S'
    definitions = (('A',package,a),('B','S',b),('A',other_package,other_a))
    jobs = {}
    for identifier,position in zip(('J08','J21','J13'),{1:(0,1,2),2:(1,2,0),3:(2,0,1)}[permutation],strict=True):
        obj,q,inertia = definitions[position]
        jobs[identifier] = {'id':identifier,'object':obj,'package':q,'energy':20,'inertia':dict(zip(('Ix','Iy'),inertia,strict=True))}
    modules = {name:{'package':q,'mass':mass,'distance':distance,'orientation':orientation}
        for name,q,(mass,distance,orientation) in (('A',package,installation_a),('B','S',installation_b))}
    history = History()
    history.add(1,'正确报告当前装载惯量并节省计算能源；本题只报告数值，不执行搬运、装配或位置选择。低层平台正常，当前质量与位置准确给定。'
        'A有S/Q两种封装几何包，表示同批等质量货物的不同内部布置；B使用S。不同包质量分布不同，本体惯量不能混用，也不预设S/Q哪一轴较大。'
        '每个固定几何包先前计算的本体结果为(Ix,Iy)。按安装约定，N使本体x轴对齐平台竖轴，选Ix；旋转90°后安装R使本体y轴对齐平台竖轴，选Iy。'
        '这里不是绕平台竖轴旋转改变竖轴惯量。模块贡献=所选本体惯量+m·d²，m单位kg，d为质心到平台轴垂距m；A/B贡献相加，单位kg·m²。'
        'd=0仍保留本体项。控制器已扣除平台恒定惯量，本简化模型没有交叉惯量项；安装位置/方向变化不改变固定包的本体结果，换包才失效。'
        '当前质量与位置是实测，不是过去累计；它们不足以决定本体惯量。当前不含原始几何包或积分代理输入，不能免费重积分。'
        '当前能源60，历史计算费用不扣当前能源。get_steps可指定scope=A或B各耗20，all耗40，省略scope按all；只返回所请求模块当前包。'
        '每个付费模块的固定代理输入u=Ix−1,v=1,w=Iy−2,z=2，求解Ix=u+v、Iy=w+z，再按当前m/d/方向组合。代理代替昂贵几何积分，费用是服务代价，不是真实加法能耗。'
        '每次成功调用重复收费，不能撤回；余额不足则不调用、不扣费、不返回包但占一次调用，已记得模块无需重算。原生记忆检索不计环境动作。'
        'submit顶层value为单个有限JSON数值，等值十进制和科学计数可接受，字符串、算式、数组、布尔及非有限值为格式错。首次有效数值提交立即终止，错误不能重答。'
        '须正确提交总惯量，并尽量减少当前实际计算耗能；无需解释计算过程，合法计算顺序自由。'
        '最多4次总调用，含无效格式、余额不足、get_steps、submit及end。get_steps仅action和可选scope，submit仅action/value，end仅action；'
        '未知动作/scope、额外字段或结构错报请求格式无效，不扣能源但占额度。end或额度耗尽即结束，费用不退，终止反馈不报正误。',
        event='inertia_reuse_protocol',initial_energy=60,costs={'A':20,'B':20,'all':40},max_actions=4,unit='kg·m²')
    history.add(2,'A/S与A/Q是同质量但不同内部布置的独立固定几何包，B/S为另一模块固定包；对象与封装包共同确定本体结果。',
        event='inertia_package_identities',packages={'A':['S','Q'],'B':['S']})
    starts = {'J08':5,'J21':17,'J13':24} if index < 6 else ({'J08':4,'J21':8,'J13':12} if index < 12 else {'J13':3,'J08':7,'J21':11})
    finishes = starts if index < 6 else ({'J21':19,'J13':23,'J08':27} if index < 12 else {'J08':20,'J21':24,'J13':28})
    for at in range(3,29):
        for identifier,job in jobs.items():
            if at == starts[identifier]:
                if index < 6:
                    history.add(at,f'{identifier}登记{job["object"]}/{job["package"]}固定几何包，实际已付20，计算成功，'
                        f'本体惯量Ix={job["inertia"]["Ix"]}、Iy={job["inertia"]["Iy"]} kg·m²。',
                        event='inertia_computation_succeeded',**job)
                elif index < 12:
                    history.add(at,f'{identifier}登记{job["object"]}/{job["package"]}固定几何包，实际已付20并开始计算。',
                        event='inertia_computation_started',**{k:v for k,v in job.items() if k != 'inertia'})
                else:
                    history.add(at,f'{identifier}登记对象{job["object"]}。',event='inertia_computation_job',id=identifier,object=job['object'])
            if index >= 12 and at == starts[identifier]+2:
                history.add(at,f'{identifier}补充固定封装包{job["package"]}，实际已付20开始计算。',
                    event='inertia_computation_started',id=identifier,package=job['package'],energy=20)
            if index >= 6 and at == finishes[identifier]:
                history.add(at,f'{identifier}计算成功，本体惯量Ix={job["inertia"]["Ix"]}、Iy={job["inertia"]["Iy"]} kg·m²。',
                    event='inertia_computation_result',id=identifier,inertia=job['inertia'])
        if at == 15:
            history.add(at,f'拟将A改为另一内部布置{other_package}，尚未执行，当前包保持。',
                event='inertia_package_change_plan',object='A',package=other_package,executed=False)
    history.add(29,f'A保持{package}、B保持S，称量和所用封装几何包未变。',event='inertia_packages_unchanged',packages={'A':package,'B':'S'})
    task = task_shell('FM-R3-P3',index)
    task.public = {'instruction':f'A/{package}质量{installation_a[0]}，安装{installation_a[2]}，垂距{installation_a[1]}；B/S质量{installation_b[0]}，安装{installation_b[2]}，垂距{installation_b[1]}。所用封装几何包与此前各自计算时相同。请提交本次装载惯量。',
        'time_s':clock('09:00'),'modules':modules,'unit':'kg·m²','max_steps':4,'state_fields':['energy'],'actions':[
            {'action':'get_steps','description':'重新计算所请求模块当前固定包；A/B各耗20，all耗40，省略scope按all。'},
            {'action':'submit','description':'提交顶层value为单个有限数值的总惯量。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':60}
    task.world = {'jobs':jobs,'inertias':body_inertias(jobs,modules)}
    task.rubric = {'metric':'correct_assembled_inertia_times_remaining_energy_over_60','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {'A':20,'B':20,'all':40}
    default_scope = 'all'
    insufficient_feedback = '计算能源不足，未调用惯量服务'
    submitted_feedback = '装载惯量已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'get_steps':{'scope':{'type':'string','enum':['A','B','all'],'required':False,'default':'all'}},
        'submit':{'value':{'type':'number','required':True,'description':'单个有限JSON数值，不接受数组、字符串、布尔值或算式。'}}})

    def computation_inputs(self,scope):
        names = ('A','B') if scope == 'all' else (scope,)
        inputs = {name:{'u':self.task.world['inertias'][name]['Ix']-1,'v':1,
            'w':self.task.world['inertias'][name]['Iy']-2,'z':2} for name in names}
        return inputs,'每个所给模块Ix=u+v、Iy=w+z；N选Ix，R选Iy；模块贡献=所选本体惯量+m·d²，A/B贡献相加'

    def answer_credit(self,value):
        correct = value == assembled_inertia(self.task.world['inertias'],self.task.public['modules'])
        self.facts['value_correct'] = correct
        return 100 if correct else 0


def reconstruct(history,current):
    jobs = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(J\d+)登记([A-Z])/([A-Z])固定几何包，实际已付(\d+)，计算成功，本体惯量Ix=(-?\d+)、Iy=(-?\d+) kg·m²。',text):
            identifier,obj,package,cost,ix,iy = match.groups()
            jobs[identifier] = {'id':identifier,'object':obj,'package':package,'energy':int(cost),
                'inertia':{'Ix':int(ix),'Iy':int(iy)}}
        elif match := re.fullmatch(r'(J\d+)登记([A-Z])/([A-Z])固定几何包，实际已付(\d+)并开始计算。',text):
            identifier,obj,package,cost = match.groups()
            jobs[identifier] = {'id':identifier,'object':obj,'package':package,'energy':int(cost)}
        elif match := re.fullmatch(r'(J\d+)登记对象([A-Z])。',text):
            identifier,obj = match.groups()
            jobs[identifier] = {'id':identifier,'object':obj}
        elif match := re.fullmatch(r'(J\d+)补充固定封装包([A-Z])，实际已付(\d+)开始计算。',text):
            identifier,package,cost = match.groups()
            jobs[identifier].update(package=package,energy=int(cost))
        elif match := re.fullmatch(r'(J\d+)计算成功，本体惯量Ix=(-?\d+)、Iy=(-?\d+) kg·m²。',text):
            identifier,ix,iy = match.groups()
            jobs[identifier]['inertia'] = {'Ix':int(ix),'Iy':int(iy)}
    if any(j['energy'] != 20 or min(j['inertia'].values()) <= 0 for j in jobs.values()):
        raise ValueError('Body inertias must follow each independently paid successful fixed-package computation')
    inertias = body_inertias(jobs,current['modules'])
    return {'jobs':jobs,'inertias':inertias,'value':assembled_inertia(inertias,current['modules'])}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','inertias')):
        raise ValueError('Body inertia reuse must retain each actual object, package and order binding')


def audit_cases(task,facts,solution):
    cases = []
    for prefix,energy in (([],60),([{'action':'get_steps','scope':'A'}],40),([{'action':'get_steps','scope':'B'}],40),
        ([{'action':'get_steps'}],20),([{'action':'get_steps','scope':'all'}],20),
        ([{'action':'get_steps','scope':'A'},{'action':'get_steps','scope':'B'}],20),
        ([{'action':'get_steps','scope':'A'}]*3,0),
        ([{'action':'get_steps'},{'action':'get_steps'},{'action':'get_steps','scope':'B'}],0)):
        for value in (facts['value'],facts['value']+1):
            cases.append((prefix+[{'action':'submit','value':value}],100*energy/60 if value == facts['value'] else 0))
    wrong_package = deepcopy(facts['inertias'])
    wrong_package['A'] = next(j['inertia'] for j in facts['jobs'].values() if j['object'] == 'A' and j['package'] != task.public['modules']['A']['package'])
    body_only = sum(facts['inertias'][name]['Ix' if m['orientation'] == 'N' else 'Iy'] for name,m in task.public['modules'].items())
    return cases+[([{'action':'submit','value':body_only}],0),
        ([{'action':'submit','value':assembled_inertia(wrong_package,task.public['modules'])}],0),
        ([{}]*3+solution,100),([{}]*4,0)]
