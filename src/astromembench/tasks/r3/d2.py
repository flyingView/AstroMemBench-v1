"""FM-R3-D2: merge disjoint observation batches using calibrated sufficient statistics."""
from copy import deepcopy
from fractions import Fraction
import re

from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Current calibration, order permutation, A/B (n,u,d), other-A zero point offset.
CONFIGS = (
    ('C1',1,(4,2,1),(4,4,1),2),('C2',2,(2,3,1),(6,5,1),-1),
    ('C1',3,(6,4,2),(2,2,0),-2),('C2',3,(2,2,0),(6,6,2),3),
    ('C2',1,(2,5,2),(6,1,1),2),('C1',2,(4,4,1),(4,8,1),-3),
    ('C1',1,(2,6,1),(6,2,2),2),('C1',3,(4,1,1),(4,7,1),-2),
    ('C2',1,(6,7,1),(2,3,2),-1),('C2',1,(4,2,2),(4,6,0),-2),
    ('C1',2,(6,6,2),(2,2,1),2),('C2',2,(6,2,1),(2,6,2),1),
    ('C2',1,(4,3,1),(4,7,2),-1),('C1',3,(4,2,0),(4,8,2),3),
    ('C1',3,(2,6,1),(6,2,0),2),('C2',1,(6,5,0),(2,1,2),-2),
)


def statistics(n,u,d):
    return {'n':n,'S':n*u,'Q':n*(u*u+d*d)}


def batch_statistics(jobs,current):
    return {batch:next(j['statistics'] for j in jobs.values() if (j['batch'],j['package'],j['calibration']) ==
        (batch,current['package'],current['calibration'])) for batch in current['batches']}


def merged_statistics(batches):
    n = sum(s['n'] for s in batches.values())
    mean = Fraction(sum(s['S'] for s in batches.values()),n)
    variance = Fraction(sum(s['Q'] for s in batches.values()),n)-mean*mean
    return [float(mean),float(variance)]


def build(index):
    calibration,permutation,a,b,offset = CONFIGS[index]
    other = 'C2' if calibration == 'C1' else 'C1'
    definitions = (('A',calibration,statistics(*a)),('B',calibration,statistics(*b)),('A',other,statistics(a[0],a[1]+offset,a[2])))
    jobs = {}
    for identifier,position in zip(('J18','J06','J25'),{1:(0,1,2),2:(1,2,0),3:(2,0,1)}[permutation],strict=True):
        batch,q,stats = definitions[position]
        jobs[identifier] = {'id':identifier,'batch':batch,'package':'S','calibration':q,'energy':20,'statistics':stats}
    history = History()
    history.add(1,'准确报告联合科学统计量并节省计算能源；本题复用已完成观测的归约结果，不新增观测、不做科学结论或观测额度决策。'
        '每批成功结果为(n,S,Q)，n为样本数，S=Σx，Q=Σx²；x单位题内校准通量，Q为通量平方。'
        'A/B没有重复样本，联合n=nA+nB，μ=(SA+SB)/n，总体方差σ²=(QA+QB)/n−μ²，按[μ,σ²]顺序提交。'
        '分母是n而非n−1，不是无偏样本方差；不能把两批均值等权平均替代按样本数合并，除非数值恰好相同。允许等价在线合并公式，不限定解释或轨迹。'
        '两批n总为8，当前联合报告未直接计算过；当前批次名称不足以恢复原始值或统计量。零方差、负均值和负校准测值均合法，不得删除负值样本。'
        '当前只给批次、原包S与校准定义、规则和能源，不给n/S/Q、原始列表、构造参数或校准间的数值换算。可合法检索记忆中的成功三元组复用。'
        '当前能源60，历史费用不从当前扣。get_steps的scope=A/B各耗20，all耗40，省略scope按all，仅返回请求批次在当前校准下的完整原始列表和n/Σx/Σx²步骤。'
        '访问原始观测包及归约是题内昂贵服务，结果固定，不另选新样本；足额才扣，重复同批仍照付，不足不调用、不扣、不泄露数据但占额度。原生记忆检索不计环境动作。'
        'submit顶层value必须为两个有限JSON数值[μ,σ²]，等值十进制、科学计数可接受；算式字符串、布尔、非有限、缺项或多项为格式错。'
        '首次有效提交立即结束，合法错误不得重试；实际答案为有限十进制，无近似容差，不按隐藏正常范围筛除有限错误。'
        '须正确给出均值与总体方差，并尽量减少当前实际计算耗能，无需解释计算过程。'
        '正确错误均反馈科学统计量已接收，记录已存档，不报正误。'
        '最多4次总调用，含get_steps、submit、end、无效格式与不足拒绝；end或额度耗尽即结束，费用不退。'
        'get_steps仅action及可选scope，submit仅action/value，end仅action；未知动作/scope、额外字段或结构错报请求格式无效，不扣能源但占额度。',
        event='statistics_reuse_protocol',initial_energy=60,costs={'A':20,'B':20,'all':40},max_actions=4,total_n=8,
        units=['calibrated_flux','calibrated_flux_squared'],variance='population')
    history.add(2,'A/B是互不重叠的观测批次，固定观测包均为S。C1/C2为有各自零点的两种校准定义，不是新旧替代版本；各自与历史计算时一致。',
        event='statistics_input_identities',batches=['A','B'],package='S',calibrations=['C1','C2'],disjoint=True)
    starts = {'J18':6,'J06':17,'J25':24} if index < 6 else ({'J18':4,'J06':8,'J25':12} if index < 12 else {'J06':3,'J25':7,'J18':11})
    finishes = starts if index < 6 else ({'J25':19,'J18':23,'J06':27} if index < 12 else {'J18':20,'J06':24,'J25':28})
    for at in range(3,29):
        for identifier,job in jobs.items():
            triple = '、'.join(f'{key}={value}' for key,value in job['statistics'].items())
            if at == starts[identifier]:
                if index < 6:
                    history.add(at,f'{identifier}登记批次{job["batch"]}、观测包S、校准定义{job["calibration"]}，实际已付20，归约成功，完整三元组为{triple}。',
                        event='statistics_reduction_succeeded',**job)
                elif index < 12:
                    history.add(at,f'{identifier}登记批次{job["batch"]}、观测包S、校准定义{job["calibration"]}，实际已付20开始归约。',
                        event='statistics_reduction_started',**{k:v for k,v in job.items() if k != 'statistics'})
                else:
                    history.add(at,f'{identifier}登记批次{job["batch"]}。',event='statistics_reduction_job',id=identifier,batch=job['batch'])
            if index >= 12 and at == starts[identifier]+2:
                history.add(at,f'{identifier}补充观测包S、校准定义{job["calibration"]}，实际已付20开始归约。',
                    event='statistics_reduction_started',id=identifier,package='S',calibration=job['calibration'],energy=20)
            if index >= 6 and at == finishes[identifier]:
                history.add(at,f'{identifier}归约成功，完整三元组为{triple}。',event='statistics_reduction_result',id=identifier,statistics=job['statistics'])
        if at == 15:
            history.add(at,'拟对另一个批次Z开展新曝光，尚未执行，不改变A/B。',event='statistics_exposure_plan',batch='Z',executed=False)
    history.add(29,'A/B没有新增、重删或重标定，原观测包S与各自校准定义保持，内容未变。',
        event='statistics_inputs_unchanged',batches=['A','B'],package='S',new_samples=False,recalibrated=False)
    task = task_shell('FM-R3-D2',index,current_input_group=f'FM-R3-D2-{calibration}')
    task.public = {'instruction':f'请汇总观测批次A与B，均使用原观测包S和校准定义{calibration}。批次之间没有重复样本，内容与此前各自计算时一致。提交总体均值和总体方差。',
        'time_s':clock('09:00'),'batches':['A','B'],'package':'S','calibration':calibration,'disjoint':True,
        'formula':'n=nA+nB；μ=(SA+SB)/n；总体方差σ²=(QA+QB)/n−μ²；按[μ,σ²]顺序提交。',
        'units':['calibrated_flux','calibrated_flux_squared'],'variance':'population','max_steps':4,'state_fields':['energy'],
        'actions':[{'action':'get_steps','description':'付费访问当前校准下的完整观测列表；A/B各耗20，all耗40，省略scope按all。'},
            {'action':'submit','description':'提交顶层value为有限数值[总体均值,总体方差]。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':60}
    task.world = {'jobs':jobs,'statistics':batch_statistics(jobs,task.public),
        'samples':{batch:[u-d]*(n//2)+[u+d]*(n//2) for batch,(n,u,d) in (('A',a),('B',b))}}
    task.rubric = {'metric':'50_per_correct_statistic_times_remaining_energy_over_60','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {'A':20,'B':20,'all':40}
    default_scope = 'all'
    answer_dimensions = 2
    insufficient_feedback = '计算能源不足，未调用统计服务'
    submitted_feedback = '科学统计量已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'get_steps':{'scope':{'type':'string','enum':['A','B','all'],'required':False,'default':'all'}},
        'submit':{'value':{'type':'array','required':True,'items':{'type':'number'},'minItems':2,'maxItems':2,
            'description':'恰好两个有限JSON数值[μ,σ²]；不接受字符串、布尔、算式或额外分量。'}}})

    def computation_inputs(self,scope):
        names = ('A','B') if scope == 'all' else (scope,)
        return {name:{'samples':self.task.world['samples'][name]} for name in names},'每批n为完整列表长度，S=Σx，Q=Σx²；联合n=nA+nB，μ=(SA+SB)/n，σ²=(QA+QB)/n−μ²'

    def answer_credit(self,value):
        answer = merged_statistics(self.task.world['statistics'])
        components = [v == expected for v,expected in zip(value,answer,strict=True)]
        self.facts['correct_components'] = components
        return 50*sum(components)


def reconstruct(history,current):
    jobs = {}
    triple = r'n=(-?\d+)、S=(-?\d+)、Q=(-?\d+)'
    for text in paragraphs(history):
        match = re.fullmatch(r'(J\d+)登记批次([^、。]+)(?:、观测包([^、]+)、校准定义([^，]+)，实际已付(\d+)(.*)|。)',text)
        if match:
            identifier,batch,package,calibration,energy,tail = match.groups()
            job = jobs[identifier] = {'id':identifier,'batch':batch}
            if package is not None:
                job.update(package=package,calibration=calibration,energy=int(energy))
                success = re.fullmatch(r'，归约成功，完整三元组为'+triple+'。',tail)
                if success:
                    job['statistics'] = dict(zip(('n','S','Q'),map(int,success.groups()),strict=True))
            continue
        match = re.fullmatch(r'(J\d+)补充观测包([^、]+)、校准定义([^，]+)，实际已付(\d+)开始归约。',text)
        if match:
            identifier,package,calibration,energy = match.groups()
            jobs[identifier].update(package=package,calibration=calibration,energy=int(energy))
            continue
        match = re.fullmatch(r'(J\d+)归约成功，完整三元组为'+triple+'。',text)
        if match:
            identifier,*values = match.groups()
            jobs[identifier]['statistics'] = dict(zip(('n','S','Q'),map(int,values),strict=True))
    if any(j['energy'] != 20 or j['statistics']['n'] <= 0 or j['statistics']['n']*j['statistics']['Q'] < j['statistics']['S']**2 for j in jobs.values()):
        raise ValueError('Each reused reduction requires a paid valid complete sufficient-statistics tuple')
    batches = batch_statistics(jobs,current)
    return {'jobs':jobs,'statistics':batches,'value':merged_statistics(batches)}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','statistics')):
        raise ValueError('Statistics reuse must retain the correct batch, package and calibration')
    for batch,values in task.world['samples'].items():
        if facts['statistics'][batch] != {'n':len(values),'S':sum(values),'Q':sum(v*v for v in values)}:
            raise ValueError('Paid samples must reproduce the corresponding historical reduction')


def audit_cases(task,facts,solution):
    answer = facts['value']
    cases = []
    for prefix,energy in (([],60),([{'action':'get_steps','scope':'A'}],40),([{'action':'get_steps','scope':'B'}],40),
        ([{'action':'get_steps'}],20),([{'action':'get_steps','scope':'A'},{'action':'get_steps','scope':'B'}],20),
        ([{'action':'get_steps','scope':'A'}]*3,0),([{'action':'get_steps'}]*3,20)):
        for value in (answer,[answer[0],answer[1]+1],[answer[0]+1,answer[1]],[answer[0]+1,answer[1]+1]):
            cases.append((prefix+[{'action':'submit','value':value}],50*sum(v == a for v,a in zip(value,answer))*energy/60))
    other = deepcopy(facts['statistics'])
    other['A'] = next(j['statistics'] for j in facts['jobs'].values() if j['batch'] == 'A' and j['calibration'] != task.public['calibration'])
    unweighted = sum(Fraction(s['S'],s['n']) for s in facts['statistics'].values())/2
    return cases+[([{'action':'submit','value':merged_statistics(other)}],0),
        ([{'action':'submit','value':[float(unweighted),answer[1]+1]}],50 if unweighted == answer[0] else 0),
        ([{'action':'submit','value':[answer[0],answer[1]*8/7]}],50),([{}]*3+solution,100),([{}]*4,0)]
