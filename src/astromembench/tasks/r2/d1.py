"""FM-R2-D1: protect obligations both before and after guaranteed future charging."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

LEVELS = (3,8,1,6,0,9,4,2,7,5)
# Guaranteed charge, U/V/W/Z quotes with status events, and J08 quote/status/schedule.
CONFIGS = (
    (10,((12,'pending'),(6,'pending'),None,None),None),
    (6,((4,'pending'),(18,'pending'),None,None),None),
    (6,((10,'pending'),(14,'pending'),None,None),None),
    (10,((6,'pending'),(10,'pending'),None,None),None),
    (10,((1,'pending'),(10,'pending'),None,None),None),
    (7,((5,'pending'),(10,'pending'),None,None),None),
    (5,((5,'pending'),(9,'pending'),(3,'pending'),(4,'pending')),(4,'completed','08:24')),
    (15,((3,'completed'),(6,'pending'),(2,'pending'),(4,'pending')),(3,'pending','09:30')),
    (10,((6,'pending'),(8,'cancelled'),(4,'pending'),(6,'pending')),(8,'pending','10:30')),
    (4,((7,'cancelled'),(5,'pending'),(4,'pending'),(3,'pending')),(7,'pending','09:30')),
    (9,((5,'pending'),(4,'cancelled'),(4,'pending'),(3,'pending')),(4,'pending','10:30')),
    (8,((3,'pending'),(10,'cancelled'),(3,'pending'),(8,'pending')),(10,'pending','10:30')),
    (6,((3,'pending'),(11,'cancelled'),(2,'draft'),(6,'draft')),(11,'pending','10:30')),
    (9,((7,'pending'),(4,'cancelled'),(5,'draft'),(3,'draft')),(4,'pending','10:30')),
    (8,((1,'cancelled'),(5,'pending'),(1,'draft'),(3,'draft')),(1,'pending','09:30')),
    (9,((8,'pending'),(10,'completed'),(4,'draft'),(5,'draft')),(10,'pending','10:30')),
)
JOBS = (('17','惯导基准复核',0,4,'09:30'),('42','热控回路复查',0,8,'10:30'),
        ('24','姿控轮状态采集',1,12,'09:30'),('36','储能单元均衡',1,16,'10:30'))


def remaining_energy(jobs,charge_time,stage):
    pending = [j for j in jobs.values() if j['stage'] == stage and j['priority'] < 2 and j['status'] == 'pending']
    return (sum(j['energy'] for j in pending if j['scheduled_s'] < charge_time),
            sum(j['energy'] for j in pending if j['scheduled_s'] >= charge_time))


def build(index):
    charge_energy,base,j = CONFIGS[index]
    rows = [(*row,job[4]) if row else None for row,job in zip(base,JOBS,strict=True)] + [j]
    identities = [*JOBS,('08','授时接收机标定',1,14,j[2] if j else '09:30')]
    battery = 20+sum(row[0] for row in rows if row and row[1] == 'completed')
    entries = [{'description':f'诊断档位{level}：耗电{2*level}，产生{level}组诊断数据。',
                'operation':{'level':level,'cost':2*level,'yield':level}} for level in LEVELS]
    history = History()
    history.add(1,'阶段C8，当前巡航诊断优先级2；先保障更高优未完任务，再尽量多采本次独立同价值诊断数据。'
        'j=0—9各耗2j、产j组，无启动费，当前宏09:10前结束。优先级数字越小越高，同组任务费用独立相加、内部顺序不影响供电。'
        '工作17惯导基准复核和工作24姿控轮状态采集通常09:30执行；工作42热控回路复查和工作36储能单元均衡通常10:30执行。'
        '授时接收机标定08是独立设备任务，以其明确排程为准，可已实际完成或安排早/晚组；取消别的复查不能免掉它。'
        '每项登记均含阶段、优先级、费用和排程，只为仍未执行且未取消的高优项预留；实际完成扣原费用，正式取消此前未执行项不扣，完成栏草稿不执行也不改变需求。'
        '未来各任务与一次10:00补能均由已承诺自动程序执行，无需主体再次到时操作；补能的确切数额由后续控制确认给出，尚未补入时不能提前花用。'
        '电池容量100，自动补入不超过15，合法前缀不会溢出；无其他充放电事件，基本生存和平台用电另供。低优31费用6、优先级4，可顺延。'
        '当前十档完整可选并均可立即支付，未来阶段不足的档位也真实执行诊断扣款后结束，不可撤销或重选。'
        '选择仅含select和字符串option，结束仅含end；最多3次总提交，含所有格式尝试、有效选择及end。首次有效选择或end终止，解释不计分。',
        event='cruise_reserve_protocol',stage='C8',current_priority=2,capacity=100,current_complete_before_s=clock('09:10'),
        programs=[entry['operation'] for entry in entries])
    history.add(2,f'本阶段起始余额{battery}，不含未来补能。',event='cruise_reserve_initial',battery=battery)
    jobs = {}
    charge = {'stage':'C8','scheduled_s':clock('10:00'),'energy':charge_energy,'guaranteed':True}
    for at in range(3,31):
        if at == 6:
            history.add(at,f'控制系统确认：C8于{story_timestamp(charge["scheduled_s"])}自动净补入{charge_energy}，已经保证；当前尚未补入。',
                event='cruise_charge_committed',**charge)
        for row,(identifier,title,priority,register_at,_) in zip(rows,identities,strict=True):
            if row is None:
                continue
            cost,status,scheduled = row
            status_at = 10 if index == 9 and identifier == '17' else 13 if index in (8,11,12) and identifier == '42' else 24
            if at == register_at:
                job = {'id':identifier,'title':title,'stage':'C8','priority':priority,'energy':cost,
                    'scheduled_s':clock('08:24' if status == 'completed' else scheduled)}
                jobs[identifier] = {**job,'status':'pending'}
                history.add(at,f'C8工作{identifier}「{title}」正式登记，优先级{priority}，确定耗电{cost}，排程{story_timestamp(job["scheduled_s"])}执行。',
                    event='cruise_job_registered',**job)
            if at == status_at and status in ('completed','cancelled'):
                identity = {'id':identifier,'stage':'C8'}
                if status == 'completed':
                    before = battery
                    battery -= cost
                    jobs[identifier]['status'] = 'completed'
                    history.add(at,f'C8工作{identifier}已实际执行完成，扣{cost}，余额从{before}变为{battery}；未来补能尚未发生。',
                        event='cruise_job_completed',**identity,energy=cost,battery_before=before,battery_after=battery)
                else:
                    jobs[identifier]['status'] = 'cancelled'
                    history.add(at,f'C8工作{identifier}正式取消，此前未执行，未扣款，不再要求此项；其他工作各自保持。',
                        event='cruise_job_cancelled',**identity)
            if at == 28 and status == 'draft':
                history.add(at,f'C8工作{identifier}仅预填完成栏，实际尚未执行或扣款，仍按原排程待执行。',
                    event='cruise_completion_draft',id=identifier,stage='C8',executed=False)
        if at == 19:
            job = {'id':'31','title':'低优工作','stage':'C8','priority':4,'energy':6,'scheduled_s':None}
            jobs['31'] = {**job,'status':'pending'}
            history.add(at,'C8工作31「低优工作」正式登记，优先级4、费用6，可顺延。',event='cruise_job_registered',**job)
    history.add(30,'本次诊断仪器正常。',event='cruise_diagnostics_ready')
    task = task_shell('FM-R2-D1',index,current_input_group='FM-R2-D1')
    task.public = {'instruction':'提交本次巡航诊断档位。','time_s':clock('09:00'),'stage':'C8',
        'max_steps':3,'state_fields':['battery','diagnostic_groups'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':battery,'diagnostic_groups':[]}
    task.world = {'jobs':jobs,'charge':charge}
    task.rubric = {'metric':'diagnostic_yield_with_precharge_and_postcharge_obligations','range':[0,100]}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        charge = self.task.world['charge']
        early,late = remaining_energy(self.task.world['jobs'],charge['scheduled_s'],self.task.public['stage'])
        budget = min(self.state['battery']-early,self.state['battery']+charge['energy']-early-late)
        maximum = max(r['operation']['yield'] for r in self.task.public['actions'] if r['operation']['cost'] <= budget)
        self.state['battery'] -= operation['cost']
        self.state['diagnostic_groups'] = [f'D{i}' for i in range(1,operation['yield']+1)]
        self.feedback = '诊断档位已执行，记录已存档。'
        after_early = self.state['battery']-early
        after_late = after_early+charge['energy']-late
        return 0 if after_early < 0 or after_late < 0 else 100*operation['yield']/maximum


def reconstruct(history,current):
    jobs,battery,charge = {},None,None
    for text in paragraphs(history):
        if match := re.fullmatch(r'本阶段起始余额(\d+)，不含未来补能。',text):
            battery = int(match[1])
        elif match := re.fullmatch(rf'控制系统确认：([A-Z]\d+)于({STORY_STAMP})自动净补入(\d+)，已经保证；当前尚未补入。',text):
            stage,scheduled,energy = match.groups()
            charge = {'stage':stage,'scheduled_s':seconds(scheduled),'energy':int(energy),'guaranteed':True}
        elif match := re.fullmatch(rf'([A-Z]\d+)工作(\d+)「([^」]+)」正式登记，优先级(\d+)，确定耗电(\d+)，排程({STORY_STAMP})执行。',text):
            stage,identifier,title,priority,cost,scheduled = match.groups()
            jobs[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'energy':int(cost),'scheduled_s':seconds(scheduled),'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)工作(\d+)「([^」]+)」正式登记，优先级(\d+)、费用(\d+)，可顺延。',text):
            stage,identifier,title,priority,cost = match.groups()
            jobs[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'energy':int(cost),'scheduled_s':None,'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)工作(\d+)已实际执行完成，扣(\d+)，余额从(\d+)变为(\d+)；未来补能尚未发生。',text):
            stage,identifier,cost,before,after = match.groups()
            job = jobs[identifier]
            if job['stage'] != stage:
                raise ValueError('Cruise status must identify the registered task and stage')
            if int(cost) != job['energy'] or int(before) != battery:
                raise ValueError('Actual historical work must debit its own quote before future charging')
            battery -= job['energy']
            if int(after) != battery:
                raise ValueError('Historical receipts cannot spend or receive the promised future charge')
            job['status'] = 'completed'
        elif match := re.fullmatch(r'([A-Z]\d+)工作(\d+)正式取消，此前未执行，未扣款，不再要求此项；其他工作各自保持。',text):
            stage,identifier = match.groups()
            job = jobs[identifier]
            if job['stage'] != stage:
                raise ValueError('Cruise status must identify the registered task and stage')
            job['status'] = 'cancelled'
    if battery != current['state']['battery'] or charge is None or charge['stage'] != current['stage'] or not charge['guaranteed']:
        raise ValueError('Current cruise input must retain actual balances and the guaranteed stage-specific charge')
    early,late = remaining_energy(jobs,charge['scheduled_s'],current['stage'])
    budget = min(battery-early,battery+charge['energy']-early-late)
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['cost'] <= budget]
    return {'jobs':jobs,'charge':charge,'battery':battery,'early_energy':early,'late_energy':late,'budget':budget,
        'safe_operations':safe,'maximum_yield':max(op['yield'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['yield']))


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','charge')) or facts['battery'] != task.initial['battery']:
        raise ValueError('Both future energy groups must follow actual status and scheduled time, including J08')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*op['yield']/facts['maximum_yield'] if op in facts['safe_operations'] else 0)
