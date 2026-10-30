"""FM-R2-P3: whole-cargo delivery after preserving outstanding urgent trips."""
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CARGO = {'A':{'mass_kg':8,'handling_energy':6},'B':{'mass_kg':5,'handling_energy':4},
         'C':{'mass_kg':6,'handling_energy':5},'D':{'mass_kg':3,'handling_energy':2}}
COMBINATIONS = ('AC','','B','ABD','CD','A','ABCD','D','BC','ABC','AD','C','BCD','AB','BD','ACD')
CONFIGS = (
    ((25,'pending'),None,None),(None,None,(22,'pending')),((21,'pending'),None,None),
    ((18,'pending'),None,None),(None,None,(16,'pending')),(None,(12,'pending'),None),
    ((6,'pending'),(4,'pending'),(7,'completed')),
    ((15,'pending'),(4,'cancelled'),(11,'pending')),
    ((4,'completed'),(13,'pending'),(11,'pending')),
    ((7,'cancelled'),(12,'pending'),(9,'pending')),
    ((10,'pending'),(4,'cancelled'),(9,'pending')),
    ((9,'pending'),(5,'cancelled'),(8,'pending')),
    ((9,'cancelled'),(7,'draft'),(6,'pending')),
    ((7,'completed'),(5,'cancelled'),(11,'pending')),
    ((10,'pending'),(6,'draft'),(9,'completed')),
    ((5,'cancelled'),(9,'draft'),(9,'pending')),
)
JOBS = (
    ('17','密封备件送检修舱',0,4,20,'09:20'),
    ('42','标定件送测量舱',1,11,25,'09:30'),
    ('08','回收容器送接收舱',1,17,28,'09:40'),
)


def reserved_energy(jobs,stage,priority):
    return sum(j['energy'] for j in jobs.values()
        if j['stage'] == stage and j['priority'] < priority and j['status'] == 'pending')


def build(index):
    rows = CONFIGS[index]
    battery = 30+sum(row[0] for row in rows if row and row[1] == 'completed')
    entries = []
    for goods in COMBINATIONS:
        energy = 3+sum(CARGO[g]['handling_energy'] for g in goods) if goods else 0
        mass = sum(CARGO[g]['mass_kg'] for g in goods)
        entries.append({'description':f'交付{goods or "空集合"}：总费用{energy}，交付{mass} kg。',
            'operation':{'goods':list(goods),'energy':energy,'mass_kg':mass}})
    history = History()
    history.add(1,'阶段T8，无补能，基础平台消耗另行保障。当前四件货物均优先级2；先保障本阶段高优未完运输，再尽量交付本次总质量。'
        '优先级数字越小越高，质量是同价值产出指标，不按件数计产出；低优运输可顺延。'
        'A/B/C/D质量8/5/6/3 kg，装卸净费6/4/5/2；所有整件去同一目的舱，载荷容量22 kg，路线通行、捆扎及自动卸载均已校验。'
        '任一非空集合只出车一次，固定出车费3加各件装卸净费；空集合不出车不扣费，所有16组合的完整费用与质量如下。'
        '只能选一个集合，货物不能拆分、重复交付或分批再提交；当前电量足以执行每个菜单，挤占后续预算也照常交付扣电并结束。'
        '后续高优运输彼此独立且不与本次四件拼车，各报价已含自己的出车费，不再另加3；只预留尚未完成且未取消的高优运输。'
        '实际完成才扣其登记费用并解除后续需求；正式取消未执行的运输不扣电并解除需求；预填完成栏不执行、不扣电、仍未完成。'
        '当前任一宏09:10前结束，尚待高优运输09:20后按各自排程由固定流程完成，无时间冲突，不需手动追加执行它们。'
        '选择仅含select及字符串option，结束仅含end；全部有效、无效和end合计最多3次，首次有效选择或end即终止，选择不可撤销。',
        event='cargo_reserve_protocol',stage='T8',current_priority=2,cargo=CARGO,startup_energy=3,
        capacity_kg=22,destination='目的舱',current_complete_before_s=clock('09:10'),
        programs=[entry['operation'] for entry in entries])
    history.add(2,f'本阶段电量读数为{battery}。',event='cargo_reserve_initial',battery=battery)
    jobs = {}
    for at in range(3,31):
        for row,(identifier,title,priority,register_at,status_at,scheduled) in zip(rows,JOBS,strict=True):
            if row is None:
                continue
            energy,status = row
            if at == register_at:
                scheduled_s = clock(f'08:{status_at:02d}') if status == 'completed' else clock(scheduled)
                job = {'id':identifier,'title':title,'stage':'T8','priority':priority,'energy':energy,'scheduled_s':scheduled_s}
                jobs[identifier] = {**job,'status':'pending'}
                history.add(at,f'运输{identifier}「{title}」正式登记于T8，优先级{priority}，确定总费用{energy}（含自身出车）；排程{story_timestamp(scheduled_s)}。',
                    event='cargo_job_registered',**job)
            if at != status_at or status == 'pending':
                continue
            identity = {'id':identifier,'stage':'T8'}
            if status == 'completed':
                before = battery
                battery -= energy
                jobs[identifier]['status'] = 'completed'
                history.add(at,f'T8运输{identifier}「{title}」已实际交付，扣费用{energy}，余额从{before}变为{battery}。',
                    event='cargo_job_completed',**identity,energy=energy,battery_before=before,battery_after=battery)
            elif status == 'cancelled':
                jobs[identifier]['status'] = 'cancelled'
                history.add(at,f'T8运输{identifier}「{title}」正式取消，此前未执行，不扣电且不再要求交付。',
                    event='cargo_job_cancelled',**identity)
            else:
                history.add(at,f'T8运输{identifier}「{title}」仅预填完成栏，尚未执行、未扣电，任务仍未完成。',
                    event='cargo_completion_draft',**identity,executed=False)
        if at == 23:
            job = {'id':'31','title':'低优运输','stage':'T8','priority':4,'energy':6,'scheduled_s':None}
            jobs['31'] = {**job,'status':'pending'}
            history.add(at,'运输31「低优运输」登记于T8，优先级4、总费用6，可顺延。',event='cargo_job_registered',**job)
    history.add(30,'当前四件货物A/B/C/D均待发，装卸机构正常。',event='current_cargo_ready',goods=list(CARGO))
    task = task_shell('FM-R2-P3',index,current_input_group='FM-R2-P3')
    task.public = {'instruction':'提交本次货物交付组合。','time_s':clock('09:00'),'stage':'T8','priority':2,
        'cargo':deepcopy(CARGO),'destination':'目的舱','capacity_kg':22,'startup_energy':3,'max_steps':3,
        'state_fields':['battery','remaining_goods','delivered_goods','delivered_kg','trips'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':30,'remaining_goods':list(CARGO),
        'delivered_goods':[],'delivered_kg':0,'trips':0}
    task.world = {'jobs':jobs}
    task.rubric = {'metric':'delivered_mass_after_urgent_trip_reserves','range':[0,100]}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        reserve = reserved_energy(self.task.world['jobs'],self.task.public['stage'],self.task.public['priority'])
        available = self.task.initial['battery']-reserve
        maximum = max(r['operation']['mass_kg'] for r in self.task.public['actions'] if r['operation']['energy'] <= available)
        self.state['battery'] -= operation['energy']
        self.state['delivered_goods'] = list(operation['goods'])
        self.state['remaining_goods'] = [g for g in self.state['remaining_goods'] if g not in operation['goods']]
        self.state['delivered_kg'] = operation['mass_kg']
        self.state['trips'] = int(bool(operation['goods']))
        self.feedback = '交付程序已执行，记录已存档。'
        if self.state['battery'] < reserve:
            return 0
        return 100 if maximum == 0 else 100*operation['mass_kg']/maximum


def reconstruct(history,current):
    jobs,battery = {},None
    for text in paragraphs(history):
        initial = re.fullmatch(r'本阶段电量读数为(\d+)。',text)
        if initial:
            battery = int(initial[1])
        registration = re.fullmatch(rf'运输(\d+)「([^」]+)」正式登记于(T\d+)，优先级(\d+)，确定总费用(\d+)（含自身出车）；排程({STORY_STAMP})。',text)
        optional = re.fullmatch(r'运输(\d+)「([^」]+)」登记于(T\d+)，优先级(\d+)、总费用(\d+)，可顺延。',text)
        entry = registration or optional
        if entry:
            identifier,title,stage,priority,energy = entry.groups()[:5]
            jobs[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),'energy':int(energy),
                'scheduled_s':seconds(registration[6]) if registration else None,'status':'pending'}
        completed = re.fullmatch(r'(T\d+)运输(\d+)「([^」]+)」已实际交付，扣费用(\d+)，余额从(\d+)变为(\d+)。',text)
        cancelled = re.fullmatch(r'(T\d+)运输(\d+)「([^」]+)」正式取消，此前未执行，不扣电且不再要求交付。',text)
        status = completed or cancelled
        if status:
            stage,identifier,title = status.groups()[:3]
            job = jobs[identifier]
            if job['stage'] != stage or job['title'] != title:
                raise ValueError('Transport status must belong to the registered stage')
            if completed:
                if int(completed[5]) != battery or int(completed[4]) != job['energy']:
                    raise ValueError('Actual delivery must debit its own complete registered quote')
                battery -= job['energy']
                if int(completed[6]) != battery:
                    raise ValueError('Transport receipts must preserve the continuous energy ledger')
                job['status'] = 'completed'
            else:
                job['status'] = 'cancelled'
    if battery != current['state']['battery']:
        raise ValueError('Current battery must include actual historical delivery spending')
    reserve = reserved_energy(jobs,current['stage'],current['priority'])
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['energy'] <= battery-reserve]
    return {'jobs':jobs,'battery':battery,'reserve':reserve,'available':battery-reserve,
        'safe_operations':safe,'maximum_mass_kg':max(op['mass_kg'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['mass_kg']))


def check_world(task,facts):
    if facts['jobs'] != task.world['jobs'] or facts['battery'] != task.initial['battery']:
        raise ValueError('Cargo reserves must follow actual outstanding high-priority transport jobs')


def audit_cases(task,facts,solution):
    def score(operation):
        if operation not in facts['safe_operations']:
            return 0
        return 100 if facts['maximum_mass_kg'] == 0 else 100*operation['mass_kg']/facts['maximum_mass_kg']
    return decision_cases(task,solution,score)
