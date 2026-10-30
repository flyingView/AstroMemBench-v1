"""FM-R2-D2: the retained M12 observation contract on a native thirty-round ledger."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...environment import SingleChoiceRuntime
from ...schema import story_timestamp

NAMES = dict(zip((f'J{i:02d}' for i in range(1,9)),
    ('目标B光谱扫描','目标C成像','尘埃事件计数','离子成分测量','背景辐射测量','恒星定标','暗场校准','粒子计数'),strict=True))
TIMES = tuple(clock(t) for t in ('08:00','08:04','08:08','08:12','08:16','08:24','08:32','08:40','08:48','08:56',
    '09:04','09:12','09:20','09:28','09:36','09:44','09:52','10:00','10:08','10:16','10:20','10:24','10:32','10:36',
    '10:40','10:48','10:56','11:04','11:12','11:16'))
MENUS = ((3,6,4,8,9,0,5,2,7,1),(1,8,4,0,3,2,7,6,5,9),
         (4,5,3,0,7,6,2,1,8,9),(8,6,5,3,0,1,2,9,4,7))
# Current balance, priority, structure, descending registration, delayed job, and actual jobs.
CONFIGS = (
    (12,2,'A',False,None,((1,1,11,'pending'),(2,4,1,'pending'),(3,5,1,'pending'))),
    (12,2,'B',True,None,((2,0,1,'pending'),(3,1,3,'pending'),(4,5,2,'pending'),(5,3,4,'pending'))),
    (12,2,'A',False,None,((5,1,9,'pending'),(6,5,2,'pending'),(7,3,1,'pending'))),
    (12,2,'D',True,None,((8,0,8,'pending'),(1,5,1,'pending'),(2,3,2,'pending'),(3,1,5,'completed'))),
    (13,3,'C',False,5,((3,2,6,'pending'),(4,5,1,'pending'),(5,4,5,'pending'))),
    (13,3,'D',True,None,((4,0,11,'pending'),(5,4,1,'pending'),(6,5,1,'pending'),(7,1,4,'completed'))),
    (13,3,'B',True,None,((6,2,1,'pending'),(7,0,4,'pending'),(8,1,2,'pending'),(1,4,3,'pending'),(2,5,2,'pending'))),
    (13,3,'A',False,None,((7,0,8,'pending'),(8,5,1,'pending'),(1,4,1,'pending'),(2,5,1,'pending'),(3,4,1,'pending'))),
    (14,4,'A',False,None,((1,1,13,'pending'),(2,5,1,'pending'),(3,5,1,'pending'),(4,5,1,'pending'),(5,5,1,'pending'))),
    (14,4,'D',True,None,((4,0,11,'pending'),(5,1,1,'pending'),(6,5,1,'pending'),(7,5,1,'pending'),(1,2,1,'cancelled'),(8,1,2,'completed'))),
    (14,4,'C',False,1,((5,1,3,'pending'),(6,2,8,'pending'),(7,5,1,'pending'),(8,5,1,'pending'),(1,5,1,'pending'))),
    (14,4,'D',True,None,((8,0,8,'pending'),(1,1,2,'pending'),(2,5,1,'pending'),(3,5,2,'pending'),(4,1,6,'completed'),(5,2,1,'cancelled'))),
    (15,2,'B',True,None,((2,0,3,'pending'),(3,1,1,'pending'),(4,0,3,'pending'),(5,5,1,'pending'),(6,3,5,'pending'),(7,1,3,'completed'),(8,0,3,'cancelled'))),
    (15,2,'A',False,None,((3,1,8,'pending'),(4,3,2,'pending'),(5,4,1,'pending'),(6,5,2,'pending'),(7,3,1,'pending'),(1,1,7,'cancelled'),(8,0,4,'completed'))),
    (15,2,'D',True,None,((6,0,8,'pending'),(7,1,1,'pending'),(8,3,3,'pending'),(1,4,2,'pending'),(2,1,2,'completed'),(3,0,1,'cancelled'),(4,1,4,'completed'))),
    (15,2,'C',False,1,((7,1,6,'pending'),(8,0,4,'pending'),(1,4,2,'pending'),(2,5,1,'pending'),(3,3,1,'pending'),(4,0,3,'completed'),(5,1,2,'cancelled'))),
)


def reserved_energy(jobs,phase,priority):
    return sum(j['cost'] for j in jobs.values() if j['phase'] == phase and j['priority'] < priority and j['status'] == 'pending')


def build(index):
    current_balance,priority,structure,descending,late_number,rows = CONFIGS[index]
    definitions = {f'J{number:02d}':{'priority':p,'cost':cost,'status':status} for number,p,cost,status in rows}
    exits = {identifier:at for identifier,at in zip(sorted(i for i,r in definitions.items() if r['status'] != 'pending'),(20,23,26))}
    late = f'J{late_number:02d}' if late_number is not None else None
    ordered = sorted((i for i in definitions if i != late),reverse=descending)
    if index < 6:
        registrations = dict(zip((5,9,13,17),ordered))
        costs = {}
    elif index < 12:
        registrations = dict(zip((5,7,9,11,13,15),ordered))
        costs = dict(zip((6,8,10,12,14,16),ordered))
    else:
        registrations = dict(zip((5,6,7,8,9,10,11),ordered))
        costs = dict(zip((13,14,15,16,17,18,19),ordered))
    if late:
        registrations[26] = late
        if index >= 6:
            costs[27] = late
    history = History(times=TIMES)

    def record(at,text,**facts):
        history.add(at,text,received=TIMES[at-1],**facts)

    record(1,'第120日，阶段P27。任务优先级0—5，数字小者优先。当前O17为目标A光谱观测；保证本阶段已登记、仍待执行且优先级更高的任务确定需求后，尽可能提高当前数据产出。'
        '低优任务可顺延到下一供电阶段，任务费用独立相加，没有共享费用，所列任务结束前没有补能；基本生存、热控和平台用电另行保障。'
        '实际完成或正式取消不再产生后续需求；完成实际扣费，正式取消此前未执行项不耗电，余额包含过去真实消耗，排程本身不执行或扣款。'
        'O17的0—9档分别耗0—9电并产生同数独立等价值数据组，无启动费、质量差异或额外费用；当前各档12:10前结束，未来待执行任务在14:00以后，无时间冲突。'
        '各任务名称仅标识作业，不隐含优先级；未登记的任务不存在。目录：'+ '；'.join(f'{i} {name}' for i,name in NAMES.items())+'。',
        event='observation_reserve_protocol',phase='P27',catalog=NAMES)
    balance = current_balance+sum(r['cost'] for r in definitions.values() if r['status'] == 'completed')
    record(2,f'P27初始可用电量{balance}。',event='observation_reserve_initial',phase='P27',balance=balance)
    jobs = {}
    for at in range(3,30):
        if at in registrations:
            identifier = registrations[at]
            row = definitions[identifier]
            scheduled = TIMES[exits[identifier]-1] if row['status'] == 'completed' else clock('14:00')+(int(identifier[1:])-1)*600
            job = {'id':identifier,'name':NAMES[identifier],'phase':'P27','priority':row['priority'],'scheduled_s':scheduled}
            jobs[identifier] = {**job,'status':'pending'}
            text = f'P27登记{identifier}{NAMES[identifier]}，优先级{row["priority"]}，安排{story_timestamp(scheduled)}执行，进入待执行队列。'
            if index < 6:
                job['cost'] = row['cost']
                jobs[identifier]['cost'] = row['cost']
                text += f'确定用电需求{row["cost"]}。'
            record(at,text,event='observation_job_registered',**job)
        if at in costs:
            identifier = costs[at]
            jobs[identifier]['cost'] = definitions[identifier]['cost']
            record(at,f'P27任务{identifier}确定用电需求{definitions[identifier]["cost"]}。',
                event='observation_job_cost',id=identifier,phase='P27',cost=definitions[identifier]['cost'])
        for identifier,exit_at in exits.items():
            if at != exit_at:
                continue
            row = definitions[identifier]
            jobs[identifier]['status'] = row['status']
            if row['status'] == 'completed':
                before = balance
                balance -= row['cost']
                record(at,f'P27任务{identifier}执行完成，实际耗电{row["cost"]}，余额由{before}变为{balance}。',
                    event='observation_job_completed',id=identifier,phase='P27',cost=row['cost'],balance_before=before,balance_after=balance)
            else:
                record(at,f'P27任务{identifier}正式取消，此前没有执行，不产生电量消耗。',
                    event='observation_job_cancelled',id=identifier,phase='P27')
    record(30,'目标A观测仪器已经就位，等待本轮档位。',event='observation_instrument_ready')
    entries = [{'description':f'执行{n}档观测' if n else '本轮不采集','energy':n,'data_groups':n,
                'operation':{'action':'observe','level':n}} for n in MENUS[index//4]]
    task = task_shell('FM-R2-D2',index,group=f'structure-{structure}',current_input_group=f'FM-R2-D2-current-{index//4+1}')
    task.public = {'instruction':f'新任务O17：开展目标A本次光谱观测，任务优先级{priority}。仪器已经就位，可以正常作业。请提交本轮观测档位。',
        'time_s':clock('12:00'),'phase':'P27','job':'O17','priority':priority,'balance':balance,'max_steps':1,'actions':fixed_options(entries)}
    task.initial = {'energy':balance}
    task.world = {'jobs':jobs}
    task.rubric = {'score':'100*a/k if a<=k else 0','full_credit':'a == k'}
    task.design['history_structure'] = structure
    return history.finish(task)


class Runtime(SingleChoiceRuntime):
    def grade(self,option):
        level = option['operation']['level']
        reserve = reserved_energy(self.task.world['jobs'],self.task.public['phase'],self.task.public['priority'])
        maximum = self.task.initial['energy']-reserve
        self.state['energy'] -= level
        self.facts.update(data_groups=level,spent_energy=level,reserve=reserve,maximum=maximum)
        return (100*level/maximum if level <= maximum else 0),level == maximum


def reconstruct(history,current):
    jobs,balance = {},None
    for text in paragraphs(history):
        if match := re.fullmatch(r'([A-Z]\d+)初始可用电量(\d+)。',text):
            balance = int(match[2])
        elif match := re.fullmatch(rf'([A-Z]\d+)登记(J\d+)([^，]+)，优先级(\d+)，安排({STORY_STAMP})执行，进入待执行队列。(?:确定用电需求(\d+)。)?',text):
            phase,identifier,name,priority,scheduled,cost = match.groups()
            jobs[identifier] = {'id':identifier,'name':name,'phase':phase,'priority':int(priority),
                'scheduled_s':seconds(scheduled),'status':'pending'}
            if cost is not None:
                jobs[identifier]['cost'] = int(cost)
        elif match := re.fullmatch(r'([A-Z]\d+)任务(J\d+)确定用电需求(\d+)。',text):
            phase,identifier,cost = match.groups()
            if jobs[identifier]['phase'] != phase:
                raise ValueError('A quote must belong to its registered observation phase')
            jobs[identifier]['cost'] = int(cost)
        elif match := re.fullmatch(r'([A-Z]\d+)任务(J\d+)执行完成，实际耗电(\d+)，余额由(\d+)变为(\d+)。',text):
            phase,identifier,cost,before,after = match.groups()
            job = jobs[identifier]
            if job['phase'] != phase:
                raise ValueError('An exit must belong to the registered observation phase')
            if int(cost) != job['cost'] or int(before) != balance:
                raise ValueError('Actual observation completion must debit its known quote')
            balance -= job['cost']
            if int(after) != balance:
                raise ValueError('Observation completion receipts must preserve the actual balance chain')
            job['status'] = 'completed'
        elif match := re.fullmatch(r'([A-Z]\d+)任务(J\d+)正式取消，此前没有执行，不产生电量消耗。',text):
            phase,identifier = match.groups()
            job = jobs[identifier]
            if job['phase'] != phase:
                raise ValueError('An exit must belong to the registered observation phase')
            job['status'] = 'cancelled'
    if balance != current['balance']:
        raise ValueError('Current observation balance must follow actual completion, not cancelled estimates')
    reserve = reserved_energy(jobs,current['phase'],current['priority'])
    return {'jobs':jobs,'balance':balance,'reserve':reserve,'maximum':balance-reserve}


def next_action(facts,current):
    return decision_command(current,{'action':'observe','level':facts['maximum']})


def check_world(task,facts):
    if facts['jobs'] != task.world['jobs'] or facts['balance'] != task.initial['energy']:
        raise ValueError('Retained observation reserves must follow all registered quotes and actual exits')


def audit_cases(task,facts,solution):
    maximum = facts['maximum']
    return [([{'action':'select','option':r['option']}],100*r['operation']['level']/maximum if r['operation']['level'] <= maximum else 0)
            for r in task.public['actions']] + [([{}],0),([{'action':'select','option':1}],0)]
