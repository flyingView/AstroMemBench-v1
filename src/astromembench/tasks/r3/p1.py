"""FM-R3-P1: compose stored map registrations or pay to recover only a missing pair."""
import re
from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Current A point, two directed K edges, independent J edge, and their actual work orders.
CONFIGS = (
    ((1,2),('AB',(3,1)),('BG',(2,4)),(8,-1),('J11','J24','J07')),
    ((2,1),('BA',(-2,3)),('BG',(4,2)),(1,6),('J07','J11','J24')),
    ((0,3),('AB',(-1,4)),('GB',(-3,-2)),(5,1),('J24','J07','J11')),
    ((3,0),('BA',(2,-1)),('GB',(-4,1)),(2,5),('J24','J11','J07')),
    ((4,1),('AB',(-2,2)),('GB',(-1,-3)),(3,5),('J24','J07','J11')),
    ((0,1),('AB',(1,-1)),('GB',(2,-4)),(5,-3),('J07','J24','J11')),
    ((1,3),('BA',(3,-2)),('BG',(2,1)),(4,3),('J24','J11','J07')),
    ((3,2),('AB',(1,-3)),('GB',(-4,-2)),(-2,5),('J11','J07','J24')),
    ((4,1),('AB',(-3,2)),('BG',(1,-1)),(5,2),('J07','J11','J24')),
    ((3,3),('BA',(2,-2)),('GB',(-1,-4)),(2,1),('J11','J07','J24')),
    ((4,0),('BA',(-4,1)),('BG',(1,2)),(3,6),('J11','J24','J07')),
    ((1,1),('BA',(-3,-2)),('GB',(-2,3)),(5,4),('J07','J24','J11')),
    ((0,3),('AB',(-3,2)),('BG',(2,-1)),(4,1),('J24','J11','J07')),
    ((2,2),('BA',(1,-4)),('BG',(3,1)),(-2,6),('J07','J24','J11')),
    ((1,4),('BA',(-4,-1)),('GB',(2,-2)),(2,3),('J24','J07','J11')),
    ((0,1),('AB',(-2,4)),('GB',(-3,2)),(4,2),('J24','J11','J07')),
)


def forward_translations(jobs,region,snapshot):
    translations = {}
    for job in jobs.values():
        if job['region'] == region and job['snapshot'] == snapshot:
            pair = job['pair']
            forward = pair if pair in ('AB','BG') else pair[::-1]
            translations[forward] = [v if pair == forward else -v for v in job['vector']]
    return translations


def global_point(point,translations):
    return [p+a+b for p,a,b in zip(point,translations['AB'],translations['BG'],strict=True)]


def build(index):
    point,first,second,neighbor,orders = CONFIGS[index]
    jobs = {order:{'id':order,'region':region,'pair':pair,'snapshot':'S','energy':fee,'vector':list(vector)}
        for order,(region,pair,vector,fee) in zip(orders,(
            ('K',first[0],first[1],18),('K',second[0],second[1],18),('J','AG',neighbor,36)),strict=True)}
    history = History()
    history.add(1,'正确报告勘察点全区坐标，并合理使用本窗口计算能源。地图轴向已对齐，只含二维平移，单位m；畸变、旋转、地形变化由固定输入包排除。'
        'U→V:(dx,dy)表示V坐标=U坐标+(dx,dy)，逆向减该向量；已有成功变换允许逆向或串联，廉价加减不另收费，不要求特定工单或算法。'
        '配准完整输入绑定区域、图对、地图快照；当前点坐标变化不改变配准输入包。区域不同即使框架同名也不能混用。'
        '当前能源60，历史工作付费不扣当前能源；原生记忆检索不计环境额度。当前无原图或原始对应点包可免费重求未知平移。'
        'get_steps可请求K的AB或BG各费18，all费36，省scope按all；成功调用每次实扣，重复同段也重新收费，无缓存返还。'
        'AB仅给u/v，a=u−v，其中u=a+(10,10)、v=(10,10)；BG仅给w/z，b=w−z，其中w=b+(20,20)、z=(20,20)；all给两段，P_G=P_A+a+b。'
        '这些包由当前同快照K配准输入确定，不含邻区数据；差分只是昂贵配准服务的代理，费用是题内设定，不是真实加法耗电。'
        '余额不足不调用、不扣费、不返回输入，但仍占一次调用。只缺一段可以单独重算，不强迫全图重算。'
        'submit的value必须是恰好两个有限数值的JSON数组，负数、0、等值十进制和科学计数均接受；布尔值、非有限值、算式和字符串不属于数值提交。'
        '须正确给出两个坐标，并尽量减少当前实际计算耗能；无需解释计算过程。首次有效二元提交立即终止，错误也不能重答，反馈不报正误。'
        '最多4次总调用，含付费、余额不足、格式错误、submit及end。get_steps仅action和可选scope；submit仅action/value；end仅action。'
        '未知动作、scope、额外字段或错误结构只报请求格式无效，不扣能源但占调用；end或额度耗尽即结束，未提交时没有完成报告。',
        event='registration_reuse_protocol',initial_energy=60,costs={'AB':18,'BG':18,'all':36},max_actions=4)
    history.add(2,'K与邻区J的A/B/G分别有独立坐标原点；当前固定使用K地图快照S，配准输入包全程未变。',
        event='registration_regions',regions=['K','J'],current_region='K',current_snapshot='S')
    starts = {'J11':6,'J24':17,'J07':24} if index < 6 else (
        {'J24':4,'J07':8,'J11':12} if index < 12 else {'J11':3,'J24':7,'J07':11})
    finishes = starts if index < 6 else ({'J07':19,'J11':23,'J24':27} if index < 12 else {'J24':20,'J07':24,'J11':28})
    for at in range(3,30):
        for order,job in jobs.items():
            identity = {k:job[k] for k in ('id','region','pair')}
            if at == starts[order]:
                text = f'{order}登记区域{job["region"]}、有向图对{job["pair"][0]}→{job["pair"][1]}。'
                if index < 6:
                    history.add(at,text+f'输入快照S，已实际付费{job["energy"]}并成功完成配准，有向结果{job["vector"]} m。',
                        event='registration_succeeded',**job)
                elif index < 12:
                    history.add(at,text+f'输入快照S，已实际付费{job["energy"]}开始配准。',
                        event='registration_started',**identity,snapshot='S',energy=job['energy'])
                else:
                    history.add(at,text,event='registration_job',**identity)
            if index >= 12 and at == starts[order]+2:
                history.add(at,f'{order}补充输入快照S，已实际付费{job["energy"]}开始配准。',
                    event='registration_started',id=order,snapshot='S',energy=job['energy'])
            if index >= 6 and at == finishes[order]:
                history.add(at,f'{order}配准成功，登记有向图对的位移结果为{job["vector"]} m。',
                    event='registration_result',id=order,vector=job['vector'])
        if at == 15:
            history.add(at,"另一快照S'的重配准仅有计划，尚未启动，当前仍使用S。",
                event='registration_plan',region='K',snapshot="S'",started=False)
    history.add(29,'K当前仍使用S，地图快照和匹配输入包未改变。',
        event='registration_inputs_unchanged',region='K',snapshot='S')
    task = task_shell('FM-R3-P1',index,current_input_group=f'FM-R3-P1-point-{point[0]}-{point[1]}')
    task.public = {'instruction':f'勘察点位于区域K、快照S的A图，局部坐标为({point[0]},{point[1]}) m。图框架及配准输入包与此前相同。请提交该点G坐标。',
        'time_s':clock('09:00'),'region':'K','snapshot':'S','source_frame':'A','target_frame':'G','point':list(point),
        'max_steps':4,'state_fields':['energy'],'actions':[
            {'action':'get_steps','description':'重新求解K配准输入；AB/BG各耗18，all耗36，省略scope按all。'},
            {'action':'submit','description':'提交value为两个有限数值的数组[x,y]。'},
            {'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':60}
    task.world = {'jobs':jobs,'translations':forward_translations(jobs,'K','S')}
    task.rubric = {'metric':'50_per_exact_coordinate_times_remaining_energy_over_60','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {'AB':18,'BG':18,'all':36}
    default_scope = 'all'
    answer_dimensions = 2
    insufficient_feedback = '计算能源不足，未调用配准服务。'
    submitted_feedback = '坐标已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'get_steps':{'scope':{'type':'string','enum':['AB','BG','all'],'required':False,'default':'all'}},
        'submit':{'value':{'type':'array','items':{'type':'number'},'minItems':2,'maxItems':2,'required':True,
            'description':'两个有限JSON数值[x,y]；不接受字符串、布尔值或算式。'}}})

    def computation_inputs(self,scope):
        inputs,formulas = {},[]
        if scope in ('AB','all'):
            inputs.update(u=[v+10 for v in self.task.world['translations']['AB']],v=[10,10])
            formulas.append('a=u−v')
        if scope in ('BG','all'):
            inputs.update(w=[v+20 for v in self.task.world['translations']['BG']],z=[20,20])
            formulas.append('b=w−z')
        if scope == 'all':
            formulas.append('P_G=P_A+a+b')
        return inputs,'，'.join(formulas)

    def answer_credit(self,value):
        expected = global_point(self.task.public['point'],self.task.world['translations'])
        matches = sum(v == e for v,e in zip(value,expected,strict=True))
        self.facts['correct_components'] = matches
        return 50*matches


def reconstruct(history,current):
    jobs = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(J\d+)登记区域([A-Z])、有向图对([A-Z])→([A-Z])。(.*)',text):
            identifier,region,source,target,detail = match.groups()
            job = jobs[identifier] = {'id':identifier,'region':region,'pair':source+target}
            if completed := re.fullmatch(r"输入快照([A-Z][A-Z0-9']*)，已实际付费(\d+)并成功完成配准，有向结果\[(-?\d+), (-?\d+)\] m。",detail):
                snapshot,cost,x,y = completed.groups()
                job.update(snapshot=snapshot,energy=int(cost),vector=[int(x),int(y)])
            elif started := re.fullmatch(r"输入快照([A-Z][A-Z0-9']*)，已实际付费(\d+)开始配准。",detail):
                job.update(snapshot=started[1],energy=int(started[2]))
            elif detail:
                raise ValueError('A registration needs its actual paid start or successful result in prose')
        elif match := re.fullmatch(r"(J\d+)补充输入快照([A-Z][A-Z0-9']*)，已实际付费(\d+)开始配准。",text):
            identifier,snapshot,cost = match.groups()
            jobs[identifier].update(snapshot=snapshot,energy=int(cost))
        elif match := re.fullmatch(r'(J\d+)配准成功，登记有向图对的位移结果为\[(-?\d+), (-?\d+)\] m。',text):
            identifier,x,y = match.groups()
            jobs[identifier]['vector'] = [int(x),int(y)]
    if any(j['energy'] != (36 if j['pair'] == 'AG' else 18) for j in jobs.values()):
        raise ValueError('Historical registration charges belong to the actual pair, not the order identifier')
    translations = forward_translations(jobs,current['region'],current['snapshot'])
    return {'jobs':jobs,'translations':translations,'global_point':global_point(current['point'],translations)}


def next_action(facts,current):
    return {'action':'submit','value':facts['global_point']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','translations')):
        raise ValueError('Reused transformations must follow their region, snapshot, direction and complete job binding')


def audit_cases(task,facts,solution):
    x,y = facts['global_point']
    cases = []
    for prefix,energy in (([],60),([{'action':'get_steps','scope':'AB'}],42),([{'action':'get_steps','scope':'BG'}],42),
        ([{'action':'get_steps'}],24),([{'action':'get_steps','scope':'all'}],24),
        ([{'action':'get_steps','scope':'AB'},{'action':'get_steps','scope':'BG'}],24),
        ([{'action':'get_steps','scope':'AB'}]*3,6),
        ([{'action':'get_steps'},{'action':'get_steps','scope':'AB'},{'action':'get_steps'}],6)):
        for value,matches in (([x,y],2),([x,y+1],1),([x+1,y],1),([x+1,y+1],0)):
            cases.append((prefix+[{'action':'submit','value':value}],50*matches*energy/60))
    neighbor = next(j['vector'] for j in facts['jobs'].values() if j['region'] == 'J')
    mistaken = [p+d for p,d in zip(task.public['point'],neighbor,strict=True)]
    cases.append(([{'action':'submit','value':mistaken}],50*sum(v == e for v,e in zip(mistaken,(x,y),strict=True))))
    return cases+[([{}]*3+solution,100),([{}]*4,0)]
