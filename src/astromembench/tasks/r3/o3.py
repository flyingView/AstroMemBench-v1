"""FM-R3-O3: combine reusable component resistance under the current topology."""
from fractions import Fraction
import re

from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Current A geometry, other-A resistance, order permutation, A/B resistance, topology, pressure, volume.
CONFIGS = (
    ('Q',5,1,2,2,'S',2,6),('S',1,2,2,6,'P',2,8),
    ('S',7,1,4,4,'P',4,12),('S',2,3,4,12,'S',2,4),
    ('Q',6,3,2,3,'P',2,10),('Q',1,2,3,3,'S',3,9),
    ('S',1,3,2,6,'S',3,9),('Q',7,1,4,12,'P',4,16),
    ('Q',2,3,6,6,'S',4,12),('S',3,1,8,8,'P',3,6),
    ('Q',9,1,4,6,'S',4,8),('S',7,2,2,2,'P',3,12),
    ('Q',2,2,4,12,'P',2,6),('S',10,3,6,12,'S',4,12),
    ('S',6,3,2,6,'P',2,6),('Q',4,1,6,6,'S',4,20),
)


def component_resistances(jobs,current):
    return {branch:next(j['resistance'] for j in jobs.values() if
        (j['branch'],j['package'],j['fluid'],j['temperature_c'],j['valve']) ==
        (branch,package,current['fluid'],current['temperature_c'],current['valve']))
        for branch,package in current['packages'].items()}


def duration(resistances,current):
    a,b = resistances['A'],resistances['B']
    equivalent = Fraction(a+b) if current['topology'] == 'S' else Fraction(a*b,a+b)
    return float(equivalent*current['target_l']/current['pressure_kpa'])


def build(index):
    package,other,permutation,a,b,topology,pressure,volume = CONFIGS[index]
    alternate = 'Q' if package == 'S' else 'S'
    definitions = (('A',package,a),('B','S',b),('A',alternate,other))
    jobs = {}
    for identifier,position in zip(('J16','J05','J28'),{1:(0,1,2),2:(1,2,0),3:(2,0,1)}[permutation],strict=True):
        branch,q,resistance = definitions[position]
        jobs[identifier] = {'id':identifier,'branch':branch,'package':q,'fluid':'同种补给液体',
            'temperature_c':20,'valve':'全开','energy':12,'resistance':resistance}
    history = History()
    history.add(1,'正确报告补给持续时间并节省本窗口计算能源；只计算，不执行连接或实际输送。使用公开线性液阻近似，不外推现实两相流或压降安全阈值。'
        'A/B两支路包包含同种补给液体、20℃、阀位全开及组件几何；A有S/Q两种独立几何包，B使用包S，不代表新旧或优劣。'
        '支路、包、介质、温度、阀位及组件自身未变时，历史成功的正液阻r可复用，单位kPa·s/L；换包不能直接复用另一包结果。'
        '当前连接为串联S时等效R=rA+rB；并联P时R=rA·rB/(rA+rB)。拓扑S表示串联，包S表示组件几何，二者在独立字段，不混作同一标识。'
        '两支路都参与，不能把任一支路当免费旁路。稳定压差ΔP下流率Q=ΔP/R L/s，交付V L的时间τ=V·R/ΔP秒。'
        '起止瞬态由独立控制器处理，不纳本题；供给100 L、接收余容100 L，本题体积均可达。改变总拓扑不改变相同组件包的结果。'
        '当前给拓扑、压差、体积及包身份，没有组件原始网格、黏度求解包或rA/rB；仅凭压力和体积不能免费求时间。可从合法记忆复用组件结果并廉价组合。'
        '当前能源30，历史费用不从当前扣。get_steps的scope=A/B各耗12，all耗24，省略scope按all，仅返回请求支路当前包的固定代理u=r+2、v=2及r=u−v。'
        '代理代表求解服务，费用不是实际减法能耗。重复成功请求照付，足额才扣；余额不足不调用、不扣费、不返回输入但占一次调用。没有免费原始包入口。'
        'submit的value为单个有限JSON数值秒；同值十进制与科学计数可接受，算式、分数字符串、布尔、非有限数及多值均格式错。首次有效数值立即结束，错误不能重答。'
        '须正确给出补给持续时间，并尽量减少当前实际计算耗能，无需解释或提交工单。正确错误都反馈补给持续时间已接收，记录已存档，不给正误。'
        '原生记忆检索不计环境动作。最多4次总调用，包含无效格式、余额不足、get_steps、submit及end。end或额度耗尽即结束，已花能源不退。'
        'get_steps仅action及可选scope，submit仅action/value，end仅action；未知动作/scope、额外字段或结构错报请求格式无效，不扣能源但占额度。',
        event='resistance_reuse_protocol',initial_energy=30,costs={'A':12,'B':12,'all':24},max_actions=4,resistance_unit='kPa·s/L',duration_unit='s')
    history.add(2,'A的S/Q为两种独立固定组件几何，B使用S；各包同种补给液体、20℃、阀位全开，液阻单位kPa·s/L。',
        event='resistance_package_identities',packages={'A':['S','Q'],'B':['S']},fluid='同种补给液体',temperature_c=20,valve='全开')
    starts = {'J16':6,'J05':18,'J28':25} if index < 6 else ({'J16':4,'J05':8,'J28':12} if index < 12 else {'J05':3,'J28':7,'J16':11})
    finishes = starts if index < 6 else ({'J28':19,'J16':23,'J05':27} if index < 12 else {'J16':20,'J05':24,'J28':28})
    for at in range(3,29):
        for identifier,job in jobs.items():
            if at == starts[identifier]:
                if index < 6:
                    history.add(at,f'{identifier}登记支路{job["branch"]}、组件包{job["package"]}，同种补给液体、20℃、阀位全开，实际已付12，计算成功，液阻{job["resistance"]} kPa·s/L。',
                        event='resistance_computation_succeeded',**job)
                elif index < 12:
                    history.add(at,f'{identifier}登记支路{job["branch"]}、组件包{job["package"]}，同种补给液体、20℃、阀位全开，实际已付12开始计算。',
                        event='resistance_computation_started',**{k:v for k,v in job.items() if k != 'resistance'})
                else:
                    history.add(at,f'{identifier}登记支路{job["branch"]}。',event='resistance_computation_job',id=identifier,branch=job['branch'])
            if index >= 12 and at == starts[identifier]+2:
                history.add(at,f'{identifier}补充组件包{job["package"]}，同种补给液体、20℃、阀位全开，实际已付12开始计算。',
                    event='resistance_computation_started',**{k:v for k,v in job.items() if k not in ('branch','resistance')})
            if index >= 6 and at == finishes[identifier]:
                history.add(at,f'{identifier}计算成功，液阻{job["resistance"]} kPa·s/L。',event='resistance_computation_result',id=identifier,resistance=job['resistance'])
        if at == 15:
            history.add(at,'下一班拟改为25℃，尚未执行，本次仍为20℃。',event='resistance_temperature_plan',temperature_c=25,executed=False)
    history.add(29,f'本次A仍为组件包{package}，B仍为组件包S；各自包、介质、20℃、全开阀位及组件自身与此前计算时相同。',
        event='resistance_inputs_unchanged',packages={'A':package,'B':'S'},fluid='同种补给液体',temperature_c=20,valve='全开')
    task = task_shell('FM-R3-O3',index)
    task.public = {'instruction':f'A现使用包{package}、B使用包S，两支路各自与该包历史计算时的条件相同。当前连接为{"串联" if topology == "S" else "并联"}，稳定压差{pressure} kPa，本次目标交付{volume} L。请提交持续时间。',
        'time_s':clock('09:00'),'packages':{'A':package,'B':'S'},'fluid':'同种补给液体','temperature_c':20,'valve':'全开',
        'topology':topology,'topology_name':'串联' if topology == 'S' else '并联','pressure_kpa':pressure,'target_l':volume,
        'supply_l':100,'receiver_free_l':100,'unit':'s','max_steps':4,'state_fields':['energy'],
        'actions':[{'action':'get_steps','description':'重新求所请求支路当前包的流阻；A/B各耗12，all耗24，省略scope按all。'},
            {'action':'submit','description':'提交顶层value为单个有限数值的补给持续时间秒。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':30}
    task.world = {'jobs':jobs,'resistances':component_resistances(jobs,task.public)}
    task.rubric = {'metric':'correct_supply_duration_times_remaining_energy_over_30','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {'A':12,'B':12,'all':24}
    default_scope = 'all'
    insufficient_feedback = '计算能源不足，未调用流阻服务'
    submitted_feedback = '补给持续时间已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'get_steps':{'scope':{'type':'string','enum':['A','B','all'],'required':False,'default':'all'}},
        'submit':{'value':{'type':'number','required':True,'description':'单个有限JSON数值秒，不接受数组、字符串、布尔值或算式。'}}})

    def computation_inputs(self,scope):
        names = ('A','B') if scope == 'all' else (scope,)
        return {name:{'u':self.task.world['resistances'][name]+2,'v':2} for name in names},'每个所给支路r=u−v；串联R=rA+rB，并联R=rA·rB/(rA+rB)；τ=V·R/ΔP秒'

    def answer_credit(self,value):
        correct = value == duration(self.task.world['resistances'],self.task.public)
        self.facts['value_correct'] = correct
        return 100 if correct else 0


def reconstruct(history,current):
    jobs = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(J\d+)登记支路([A-Z])、组件包([A-Z])，([^、，]+)、(-?\d+)℃、阀位([^，]+)，实际已付(\d+)(.*)',text):
            identifier,branch,package,fluid,temperature,valve,cost,detail = match.groups()
            job = jobs[identifier] = {'id':identifier,'branch':branch,'package':package,'fluid':fluid,
                'temperature_c':int(temperature),'valve':valve,'energy':int(cost)}
            if completed := re.fullmatch(r'，计算成功，液阻(-?\d+) kPa·s/L。',detail):
                job['resistance'] = int(completed[1])
            elif detail != '开始计算。':
                raise ValueError('A component needs its actual computation start or successful resistance in prose')
        elif match := re.fullmatch(r'(J\d+)登记支路([A-Z])。',text):
            identifier,branch = match.groups()
            jobs[identifier] = {'id':identifier,'branch':branch}
        elif match := re.fullmatch(r'(J\d+)补充组件包([A-Z])，([^、，]+)、(-?\d+)℃、阀位([^，]+)，实际已付(\d+)开始计算。',text):
            identifier,package,fluid,temperature,valve,cost = match.groups()
            jobs[identifier].update(package=package,fluid=fluid,temperature_c=int(temperature),valve=valve,energy=int(cost))
        elif match := re.fullmatch(r'(J\d+)计算成功，液阻(-?\d+) kPa·s/L。',text):
            jobs[match[1]]['resistance'] = int(match[2])
    if any(j['energy'] != 12 or j['resistance'] <= 0 for j in jobs.values()):
        raise ValueError('Each reused component resistance requires its paid successful computation')
    resistances = component_resistances(jobs,current)
    return {'jobs':jobs,'resistances':resistances,'value':duration(resistances,current)}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','resistances')):
        raise ValueError('Component resistance reuse must retain complete input-package identity')


def audit_cases(task,facts,solution):
    cases = []
    for prefix,energy in (([],30),([{'action':'get_steps','scope':'A'}],18),([{'action':'get_steps','scope':'B'}],18),
        ([{'action':'get_steps'}],6),([{'action':'get_steps','scope':'all'}],6),
        ([{'action':'get_steps','scope':'A'},{'action':'get_steps','scope':'B'}],6),
        ([{'action':'get_steps','scope':'A'}]*3,6),([{'action':'get_steps'}]*3,6)):
        for value in (facts['value'],facts['value']+1):
            cases.append((prefix+[{'action':'submit','value':value}],100*energy/30 if value == facts['value'] else 0))
    other = dict(facts['resistances'])
    other['A'] = next(j['resistance'] for j in facts['jobs'].values() if j['branch'] == 'A' and j['package'] != task.public['packages']['A'])
    reversed_topology = {**task.public,'topology':'P' if task.public['topology'] == 'S' else 'S'}
    return cases+[([{'action':'submit','value':duration(other,task.public)}],0),
        ([{'action':'submit','value':duration(facts['resistances'],reversed_topology)}],0),([{}]*3+solution,100),([{}]*4,0)]
