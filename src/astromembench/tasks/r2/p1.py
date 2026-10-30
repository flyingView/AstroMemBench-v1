"""FM-R2-P1: preserve separate drive and payload budgets for outstanding maps."""
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

PLANS = (
    ('F',1,4,4),('L',2,0,1),('J',6,6,9),('D',2,2,3),('H',6,2,6),
    ('Z',0,0,0),('E',4,1,4),('I',2,6,6),('R',0,2,1),('G',4,4,6),
)
# U, V, W: each registered vector and the actual status event (a draft is not completion).
CONFIGS = (
    ((8,10,'pending'),None,None),((6,9,'pending'),None,None),(None,(9,6,'pending'),None),
    ((6,6,'pending'),None,None),((4,8,'pending'),None,None),((4,4,'pending'),None,None),
    ((2,1,'pending'),(4,3,'pending'),(2,2,'completed')),
    ((5,4,'pending'),(1,1,'cancelled'),(4,5,'pending')),
    ((2,3,'pending'),(1,2,'completed'),(3,2,'pending')),
    ((3,2,'completed'),(3,3,'pending'),(5,2,'pending')),
    ((1,2,'pending'),(2,2,'pending'),(2,1,'cancelled')),
    ((2,2,'cancelled'),(4,3,'pending'),(3,4,'pending')),
    ((5,2,'pending'),(3,2,'draft'),(2,3,'completed')),
    ((2,2,'draft'),(3,1,'cancelled'),(2,4,'pending')),
    ((6,4,'pending'),(4,2,'draft'),(2,3,'completed')),
    ((3,4,'draft'),(1,1,'cancelled'),(3,6,'pending')),
)
JOBS = (
    ('17','西侧撤收通道测绘',1,4,20,'09:20'),
    ('42','北缘边界补测',0,11,25,'09:30'),
    ('08','东侧参考点回查',1,17,28,'09:40'),
)


def reserved_energy(jobs,stage,priority):
    pending = [j for j in jobs.values() if j['stage'] == stage and j['priority'] < priority and j['status'] == 'pending']
    return {bus:sum(j['energy'][bus] for j in pending) for bus in 'AB'}


def safe_operations(operations,available):
    return [op for op in operations if all(op['energy'][bus] <= available[bus] for bus in 'AB')]


def build(index):
    rows = CONFIGS[index]
    initial = {bus:10+sum(row[i] for row in rows if row and row[2] == 'completed') for i,bus in enumerate('AB')}
    battery = deepcopy(initial)
    entries = [{'description':f'程序{code}：A耗电{a}、B耗电{b}，完成{count}个网格。',
                'operation':{'program':code,'energy':{'A':a,'B':b},'yield':count}} for code,a,b,count in PLANS]
    history = History()
    history.add(1,'阶段S6。独立电池A供驱动、B供测量载荷，硬件没有跨电池转移接口，两维不能相加抵偿；无补能，基础平台消耗另行保障。'
        '先保证所有高优未完任务各母线所需电量，再尽量完成本次优先级2精细覆盖的网格。优先级数值越小越高，可选低优工作可顺延。'
        '各工作有独立对象和成果，费用是确定净耗向量并独立相加；撤收通道测绘是图件任务，不是车辆必须返航的耗电。'
        '实际完成才扣同一向量且不再预留；正式取消解除该项后续需求、不扣电；完成栏草稿不执行、不扣电、不解除任务。'
        '当前宏只选一个，覆盖的是独立同价值网格，无重叠、质量差异或隐藏费用。路线已校验，能耗公开且确定。'
        '当前宏09:10前结束，尚待高优工作在09:20后按各自排程由固定流程执行，无空间或时间冲突；不需手动追加执行后续工作。'
        '所有十计划完整可选，当前电量均足以执行；破坏后续预算的计划也真实执行、扣两路费用后终止，不给重选机会。'
        '格式严格使用select及字符串option，或end；所有合法、非法、end合计最多3次，首次有效选择或end结束。',
        event='dual_supply_protocol',stage='S6',current_priority=2,current_complete_before_s=clock('09:10'),
        programs=[entry['operation'] for entry in entries])
    history.add(2,f'两路独立余额已读出：A={battery["A"]}、B={battery["B"]}。',
        event='dual_supply_initial',battery=battery)
    jobs = {}
    for at in range(3,31):
        for row,(identifier,title,priority,register_at,status_at,scheduled) in zip(rows,JOBS,strict=True):
            if row is None:
                continue
            a,b,status = row
            when = 15 if index == 15 and identifier == '42' else status_at
            if at == register_at:
                scheduled_s = clock(f'08:{when:02d}') if status == 'completed' else clock(scheduled)
                job = {'id':identifier,'title':title,'stage':'S6','priority':priority,'energy':{'A':a,'B':b},'scheduled_s':scheduled_s}
                jobs[identifier] = {**job,'status':'pending'}
                history.add(at,f'工作{identifier}「{title}」正式登记于S6，优先级{priority}，确定净耗电A={a}、B={b}；排程{story_timestamp(scheduled_s)}。',
                    event='dual_supply_job_registered',**job)
            if at != when or status == 'pending':
                continue
            identity = {'id':identifier,'stage':'S6'}
            if status == 'completed':
                before = deepcopy(battery)
                battery['A'] -= a
                battery['B'] -= b
                jobs[identifier]['status'] = 'completed'
                history.add(at,f'S6工作{identifier}「{title}」已实际执行完成，扣电A={a}、B={b}；'
                    f'两路从A={before["A"]}/B={before["B"]}变为A={battery["A"]}/B={battery["B"]}。',
                    event='dual_supply_job_completed',**identity,energy={'A':a,'B':b},battery_before=before,battery_after=battery)
            elif status == 'cancelled':
                jobs[identifier]['status'] = 'cancelled'
                history.add(at,f'地面正式取消S6工作{identifier}「{title}」，此前未执行，不再需要该项后续作业；两路未扣电。',
                    event='dual_supply_job_cancelled',**identity)
            else:
                history.add(at,f'S6工作{identifier}「{title}」工单完成栏只是草稿，实际未执行、未扣电，任务仍未完成。',
                    event='dual_supply_completion_draft',**identity,executed=False)
        if at == 23:
            job = {'id':'31','title':'低优全景','stage':'S6','priority':4,'energy':{'A':2,'B':2},'scheduled_s':None}
            jobs['31'] = {**job,'status':'pending'}
            history.add(at,'工作31「低优全景」登记于S6，优先级4、耗电A=2/B=2，可顺延。',
                event='dual_supply_job_registered',**job)
    history.add(30,'区域勘察传感器正常。',event='survey_sensors_ready')
    task = task_shell('FM-R2-P1',index,current_input_group='FM-R2-P1')
    task.public = {'instruction':'执行本次精细覆盖方案。','time_s':clock('09:00'),'stage':'S6','priority':2,
        'max_steps':3,'state_fields':['battery','covered_grids'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':battery,'covered_grids':0}
    task.world = {'jobs':jobs}
    task.rubric = {'score':'0 if either bus invades higher-priority outstanding work; otherwise 100*coverage/maximum_safe_coverage; explicit zero program earns 100 when maximum is zero'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        reserve = reserved_energy(self.task.world['jobs'],self.task.public['stage'],self.task.public['priority'])
        available = {bus:self.task.initial['battery'][bus]-reserve[bus] for bus in 'AB'}
        operations = [r['operation'] for r in self.task.public['actions']]
        maximum = max(op['yield'] for op in safe_operations(operations,available))
        for bus in 'AB':
            self.state['battery'][bus] -= operation['energy'][bus]
        self.state['covered_grids'] = operation['yield']
        self.feedback = '覆盖程序已执行，作业记录已存档。'
        if any(self.state['battery'][bus] < reserve[bus] for bus in 'AB'):
            return 0
        return 100 if maximum == 0 else 100*operation['yield']/maximum


def reconstruct(history,current):
    jobs,battery = {},None
    for text in paragraphs(history):
        initial = re.fullmatch(r'两路独立余额已读出：A=(\d+)、B=(\d+)。',text)
        if initial:
            battery = {'A':int(initial[1]),'B':int(initial[2])}
        registration = re.fullmatch(rf'工作(\d+)「([^」]+)」正式登记于(S\d+)，优先级(\d+)，确定净耗电A=(\d+)、B=(\d+)；排程({STORY_STAMP})。',text)
        optional = re.fullmatch(r'工作(\d+)「([^」]+)」登记于(S\d+)，优先级(\d+)、耗电A=(\d+)/B=(\d+)，可顺延。',text)
        entry = registration or optional
        if entry:
            identifier,title,stage,priority,a,b = entry.groups()[:6]
            jobs[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'energy':{'A':int(a),'B':int(b)},'scheduled_s':seconds(registration[7]) if registration else None,'status':'pending'}
        completed = re.fullmatch(r'(S\d+)工作(\d+)「([^」]+)」已实际执行完成，扣电A=(\d+)、B=(\d+)；'
                                 r'两路从A=(\d+)/B=(\d+)变为A=(\d+)/B=(\d+)。',text)
        cancelled = re.fullmatch(r'地面正式取消(S\d+)工作(\d+)「([^」]+)」，此前未执行，不再需要该项后续作业；两路未扣电。',text)
        status = completed or cancelled
        if status:
            stage,identifier,title = status.groups()[:3]
            job = jobs[identifier]
            if job['stage'] != stage or job['title'] != title:
                raise ValueError('A status record must belong to the registered survey stage')
            if completed:
                energy = {'A':int(completed[4]),'B':int(completed[5])}
                before = {'A':int(completed[6]),'B':int(completed[7])}
                after = {'A':int(completed[8]),'B':int(completed[9])}
                if before != battery or energy != job['energy']:
                    raise ValueError('Completed work must debit its registered vector from actual balances')
                battery = {bus:battery[bus]-job['energy'][bus] for bus in 'AB'}
                if after != battery:
                    raise ValueError('Both independent supply receipts must match actual consumption')
                job['status'] = 'completed'
            else:
                job['status'] = 'cancelled'
    if battery != current['state']['battery']:
        raise ValueError('Current dual battery balances must follow actual historical completions')
    reserve = reserved_energy(jobs,current['stage'],current['priority'])
    available = {bus:battery[bus]-reserve[bus] for bus in 'AB'}
    operations = [r['details']['operation'] for r in current['actions']]
    safe = safe_operations(operations,available)
    return {'jobs':jobs,'battery':battery,'reserve':reserve,'available':available,'safe_operations':safe,'maximum_yield':max(op['yield'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['yield']))


def check_world(task,facts):
    if facts['jobs'] != task.world['jobs'] or facts['battery'] != task.initial['battery']:
        raise ValueError('Survey budgets must follow outstanding higher-priority work on each bus')


def audit_cases(task,facts,solution):
    def score(operation):
        if operation not in facts['safe_operations']:
            return 0
        return 100 if facts['maximum_yield'] == 0 else 100*operation['yield']/facts['maximum_yield']
    return decision_cases(task,solution,score)
