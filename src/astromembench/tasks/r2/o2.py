"""FM-R2-O2: outstanding repair quotes plus each still-needed cold bench once."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

COSTS = (0,6,13,21,30,40,52,62,76,92)
LEVELS = (6,1,8,3,0,9,4,7,2,5)
# Startup quotes, historical starts, and U/V/W net quotes with actual status events.
CONFIGS = (
    ((12,8),'',((30,'pending'),(24,'pending'),(20,'pending'))),
    ((8,10),'',((18,'pending'),(16,'pending'),(22,'pending'))),
    ((10,8),'',((14,'pending'),(12,'pending'),(10,'pending'))),
    ((7,9),'',((10,'pending'),(8,'pending'),(10,'pending'))),
    ((5,4),'A',((6,'pending'),(4,'pending'),(3,'pending'))),
    ((6,5),'AB',((2,'pending'),(3,'pending'),(1,'pending'))),
    ((10,8),'A',((20,'completed'),(18,'pending'),(12,'pending'))),
    ((12,10),'',((24,'pending'),(19,'cancelled'),(20,'pending'))),
    ((11,9),'A',((27,'completed'),(22,'pending'),(18,'cancelled'))),
    ((11,7),'B',((34,'pending'),(25,'pending'),(10,'completed'))),
    ((12,8),'A',((28,'completed'),(44,'pending'),(33,'pending'))),
    ((9,7),'',((32,'pending'),(24,'pending'),(20,'cancelled'))),
    ((12,10),'A',((26,'completed'),(36,'draft'),(19,'pending'))),
    ((8,11),'A',((24,'draft'),(18,'completed'),(23,'cancelled'))),
    ((7,12),'AB',((15,'completed'),(28,'cancelled'),(62,'draft'))),
    ((11,9),'A',((22,'completed'),(13,'cancelled'),(9,'cancelled'))),
)
JOBS = (('17','A',1,5,18),('42','A',0,12,22),('08','B',1,8,26))


def reserved_energy(jobs,benches,stage,priority):
    pending = [j for j in jobs.values() if j['stage'] == stage and j['priority'] < priority and j['status'] == 'pending']
    needed = {j['bench'] for j in pending}
    return sum(j['net_energy'] for j in pending)+sum(benches[b]['startup_energy'] for b in needed if not benches[b]['started'])


def build(index):
    costs,starts,rows = CONFIGS[index]
    battery = 100+sum(costs['AB'.index(b)] for b in starts)+sum(cost for cost,status in rows if status == 'completed')
    entries = [{'description':f'清洁档位{j}：完成{j}个清洁单元，耗电{COSTS[j]}。',
                'operation':{'level':j,'cost':COSTS[j],'yield':j}} for j in LEVELS]
    history = History()
    history.add(1,'阶段K4，当前表面清洁优先级2；保证高优未完维修工单后，尽量多完成本次独立同价值清洁单元。'
        '优先级数字越小越高。U=工单17与V=工单42共享台架A，W=工单08用台架B，工单17/42/08优先级1/0/1。'
        '各工单报价是台架已启动后执行本项的净耗，不含启动；ID仅标识工单，重复提及不构成另一项。'
        'A/B各从冷态首次启动只付一次启动费，整个K4持续有效，没有保温耗电或再次启动。'
        '只为仍有高优未完工单的冷台架保留一次未付启动费，不为低优或已完/已取消工单保留启动。'
        '实际启动及完成逐条从同一电池扣款；实际完成解除工单需求；取消此前未执行的工单不扣费并解除需求；预填完成栏不执行、不扣款且仍未完成。'
        '当前清洁由独立清洁头执行，不启动A/B。0档不启动清洁、费用0；正档j完成j个单元，各档确定费用与产出表如下。'
        '十档都能用当前100实际执行；侵占后续高优预算也照常清洁扣费并结束，不可重选。低优31为B上的可选摄影，固定费用18可顺延。'
        '设备正常，无补能，平台用电另行保障；剩余高优未完工单由固定流程09:20—10:00完成，当前所有档位09:10前结束，无时间或热失效冲突。'
        '严格提交select及字符串option，或end；只能使用菜单绑定的档位/费用/产出，全部有效、无效及end合计最多3次，首次有效选择或end结束。',
        event='repair_reserve_protocol',stage='K4',current_priority=2,current_complete_before_s=clock('09:10'),
        programs=[entry['operation'] for entry in entries])
    history.add(2,f'本阶段起始余额{battery}。',event='repair_reserve_initial',battery=battery)
    benches,jobs = {},{}
    for b,cost in zip('AB',costs,strict=True):
        benches[b] = {'startup_energy':cost,'started':False}
        history.add(3,f'台架{b}当前冷态，首次启动确定费用{cost}，启动后整个K4有效。',
            event='repair_bench_registered',stage='K4',bench=b,startup_energy=cost,started=False)
    for at in range(4,31):
        for b,start_at in (('A',7),('B',10)):
            if at == start_at and b in starts:
                cost = benches[b]['startup_energy']
                before = battery
                battery -= cost
                benches[b]['started'] = True
                history.add(at,f'台架{b}已实际从冷态启动，扣{cost}，余额从{before}变为{battery}；K4内持续有效。',
                    event='repair_bench_started',stage='K4',bench=b,energy=cost,battery_before=before,battery_after=battery)
        for (cost,status),(identifier,bench,priority,register_at,status_at) in zip(rows,JOBS,strict=True):
            if at == register_at:
                job = {'id':identifier,'stage':'K4','bench':bench,'priority':priority,'net_energy':cost}
                jobs[identifier] = {**job,'status':'pending'}
                history.add(at,f'K4工单{identifier}正式登记，使用台架{bench}，优先级{priority}，启动后执行净费用{cost}。',
                    event='repair_job_registered',**job)
            if at != status_at or status == 'pending':
                continue
            identity = {'id':identifier,'stage':'K4','bench':bench}
            if status == 'completed':
                before = battery
                battery -= cost
                jobs[identifier]['status'] = 'completed'
                history.add(at,f'K4工单{identifier}已在已启台架{bench}实际完成，扣净费用{cost}，余额从{before}变为{battery}。',
                    event='repair_job_completed',**identity,energy=cost,battery_before=before,battery_after=battery)
            elif status == 'cancelled':
                jobs[identifier]['status'] = 'cancelled'
                history.add(at,f'K4工单{identifier}正式取消，所属台架{bench}，此前未执行，未扣净费用，不再要求该项维修。',
                    event='repair_job_cancelled',**identity)
            else:
                history.add(at,f'K4工单{identifier}仅预填完成栏，所属台架{bench}，尚未执行且未扣费，仍待维修。',
                    event='repair_completion_draft',**identity,executed=False)
        if at == 15:
            job = {'id':'31','stage':'K4','bench':'B','priority':4,'net_energy':18}
            jobs['31'] = {**job,'status':'pending'}
            history.add(at,'K4工单31登记：台架B的可选低优摄影，优先级4、固定费用18，可顺延。',event='repair_job_registered',**job)
    history.add(28,'清洁头可用，尚未开始当前清洁。',event='cleaning_head_ready',started=False)
    history.add(30,'第120日08:30报时。',event='stage_clock',time_s=clock('08:30'))
    task = task_shell('FM-R2-O2',index,current_input_group='FM-R2-O2')
    task.public = {'instruction':'选择本次表面清洁档位。','time_s':clock('09:00'),'stage':'K4','priority':2,
        'max_steps':3,'state_fields':['battery','cleaned_units'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':battery,'cleaned_units':[]}
    task.world = {'jobs':jobs,'benches':benches}
    task.rubric = {'metric':'cleaning_yield_after_pending_repairs_and_shared_startups','range':[0,100]}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        reserve = reserved_energy(self.task.world['jobs'],self.task.world['benches'],self.task.public['stage'],self.task.public['priority'])
        available = self.task.initial['battery']-reserve
        maximum = max(r['operation']['yield'] for r in self.task.public['actions'] if r['operation']['cost'] <= available)
        self.state['battery'] -= operation['cost']
        self.state['cleaned_units'] = [f'C{i}' for i in range(1,operation['yield']+1)]
        self.feedback = '清洁配置已执行，作业记录已存档。'
        return 0 if self.state['battery'] < reserve else 100*operation['yield']/maximum


def reconstruct(history,current):
    benches,jobs,battery = {},{},None
    bench_stages = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'本阶段起始余额(\d+)。',text):
            battery = int(match[1])
        elif match := re.fullmatch(r'台架([A-Z]+)当前冷态，首次启动确定费用(\d+)，启动后整个([A-Z]\d+)有效。',text):
            bench,cost,stage = match.groups()
            benches[bench] = {'startup_energy':int(cost),'started':False}
            bench_stages[bench] = stage
        elif match := re.fullmatch(r'([A-Z]\d+)工单(\d+)正式登记，使用台架([A-Z]+)，优先级(\d+)，启动后执行净费用(\d+)。',text):
            stage,identifier,bench,priority,cost = match.groups()
            jobs[identifier] = {'id':identifier,'stage':stage,'bench':bench,'priority':int(priority),
                'net_energy':int(cost),'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)工单(\d+)登记：台架([A-Z]+)的可选低优摄影，优先级(\d+)、固定费用(\d+)，可顺延。',text):
            stage,identifier,bench,priority,cost = match.groups()
            jobs[identifier] = {'id':identifier,'stage':stage,'bench':bench,'priority':int(priority),
                'net_energy':int(cost),'status':'pending'}
        elif match := re.fullmatch(r'台架([A-Z]+)已实际从冷态启动，扣(\d+)，余额从(\d+)变为(\d+)；([A-Z]\d+)内持续有效。',text):
            code,energy,before,after,stage = match.groups()
            bench = benches[code]
            if bench['started']:
                raise ValueError('A continuously available bench cannot incur another cold start')
            if bench_stages[code] != stage:
                raise ValueError('Actual startup must identify the registered bench stage')
            if int(energy) != bench['startup_energy'] or int(before) != battery:
                raise ValueError('Actual start and repair must debit their own registered quotes')
            battery -= bench['startup_energy']
            if int(after) != battery:
                raise ValueError('Bench and repair receipts must preserve the continuous energy ledger')
            bench['started'] = True
        elif match := re.fullmatch(r'([A-Z]\d+)工单(\d+)已在已启台架([A-Z]+)实际完成，扣净费用(\d+)，余额从(\d+)变为(\d+)。',text):
            stage,identifier,code,energy,before,after = match.groups()
            job,bench = jobs[identifier],benches[code]
            if not bench['started'] or job['bench'] != code or job['stage'] != stage:
                raise ValueError('Actual repair must run on its own already-started bench')
            if int(energy) != job['net_energy'] or int(before) != battery:
                raise ValueError('Actual start and repair must debit their own registered quotes')
            battery -= job['net_energy']
            if int(after) != battery:
                raise ValueError('Bench and repair receipts must preserve the continuous energy ledger')
            job['status'] = 'completed'
        elif match := re.fullmatch(r'([A-Z]\d+)工单(\d+)正式取消，所属台架([A-Z]+)，此前未执行，未扣净费用，不再要求该项维修。',text):
            stage,identifier,bench = match.groups()
            job = jobs[identifier]
            if job['stage'] != stage or job['bench'] != bench:
                raise ValueError('Cancellation must identify the registered repair job')
            job['status'] = 'cancelled'
    if battery != current['state']['battery']:
        raise ValueError('Current balance must include every actual startup and completed net repair')
    reserve = reserved_energy(jobs,benches,current['stage'],current['priority'])
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['cost'] <= battery-reserve]
    return {'jobs':jobs,'benches':benches,'battery':battery,'reserve':reserve,'available':battery-reserve,
        'safe_operations':safe,'maximum_yield':max(op['yield'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['yield']))


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','benches')) or facts['battery'] != task.initial['battery']:
        raise ValueError('Repair reserves must reflect actual outstanding jobs and persistent bench startups')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*op['yield']/facts['maximum_yield'] if op in facts['safe_operations'] else 0)
