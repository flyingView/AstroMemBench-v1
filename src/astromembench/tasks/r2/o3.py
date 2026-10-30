"""FM-R2-O3: a pumping choice creates the closing obligations of its channels."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

PROGRAMS = (('AB2','AB',8,12),('B1','B',2,3),('A3','A',8,10),('Z','',0,0),
            ('AB3','AB',11,16),('A1','A',2,3),('B3','B',8,10),('AB1','AB',5,8),('A2','A',5,7),('B2','B',5,7))
# U/V quote and status, A/B closing quotes, actual chronological channel history.
CONFIGS = (
    (((18,'pending'),None),(4,9),()),
    (((8,'pending'),(6,'pending')),(5,5),()),
    ((None,(12,'pending')),(3,4),()),
    (((20,'pending'),None),(7,8),()),
    (((21,'pending'),None),(2,2),()),
    (((24,'pending'),None),(6,7),()),
    (((5,'completed'),(10,'pending')),(3,4),('+A','+B')),
    (((11,'pending'),(7,'cancelled')),(5,6),('+A','+B')),
    (((6,'cancelled'),(15,'pending')),(6,7),('+A','+B')),
    (((8,'completed'),(18,'pending')),(5,6),('+A','+B')),
    (((5,'cancelled'),(18,'pending')),(5,2),('+A',)),
    (((8,'cancelled'),(20,'pending')),(8,3),()),
    (((6,'completed'),(17,'pending')),(4,7),('+A','-A','+A','?B')),
    (((9,'pending'),(10,'pending')),(5,2),('+A','+B','-A','-B','?A')),
    (((7,'cancelled'),(16,'pending')),(3,8),('+A','-A','+B','-B','+A','+B')),
    (((20,'pending'),(8,'cancelled')),(2,3),('+A','+B','-A','?A','-B','+A')),
)
CHANNEL_ROUNDS = (5,9,13,17,21,25,27,28)
JOBS = (('17','供给舱温控复查',4),('42','接收舱库存复核',12))


def activate(channels,channel):
    state = channels[channel]
    if not state['active']:
        state['cycle'] += 1
        state['active'] = True
    return f'{channel}{state["cycle"]}'


def future_energy(jobs,channels,closing,used,stage,priority):
    assurance = sum(j['energy'] for j in jobs.values() if j['stage'] == stage and j['priority'] < priority and j['status'] == 'pending')
    needed = {c for c,s in channels.items() if s['active']} | set(used)
    return assurance+sum(closing[c] for c in needed)


def build(index):
    rows,costs,sequence = CONFIGS[index]
    closing = dict(zip('AB',costs,strict=True))
    transfers = sum(op[0] == '+' for op in sequence)
    battery = 30+2*transfers+sum(closing[op[1]] for op in sequence if op[0] == '-')+sum(row[0] for row in rows if row and row[1] == 'completed')
    supply,free = 100+transfers,30+transfers
    channels = {c:{'cycle':0,'active':False} for c in 'AB'}
    entries = [{'description':f'程序{code}：使用{used or "空集合"}通道，当前泵送费{cost}，本轮转移{volume} L。',
                'operation':{'program':code,'channels':list(used),'cost':cost,'volume_l':volume}} for code,used,cost,volume in PROGRAMS]
    history = History()
    history.add(1,'阶段F6，当前补给优先级2。先保证全部剩余高优保障及本次方案产生的必需收尾，再尽量提高本轮转移升数。'
        'A/B为独立通道，均通往同一接收箱；连接、支撑、对接已检查，采用预置流程。各菜单泵送费公开固定、包含本轮启泵但不含未来排空/闭合，与此前是否启用无关。'
        '每通道每个启用周期最多一项优先级0收尾；未收尾时继续泵送不新增第二笔，实际排空闭合才结束周期。关闭后再实际开通泵送建立新周期，需再次收尾。'
        '原已启用而本轮不用的通道仍须收尾；未执行的重新开通计划不转液、不扣电、不建周期。收尾定额固定独立，关闭已含内部回收，对核算供给和接收储箱没有净转移。'
        '工作17供给舱温控复查、工作42接收舱库存复核均优先级0，独立于通道且报价不含收尾；实际完成或正式取消分别解除自身需求，不能替代另一项或关闭通道。'
        '实际完成扣其报价，取消未执行项不扣。低优工作31费用6、优先级4，可顺延。无补能，基础平台另供电。'
        '剩余保障和收尾由固定程序09:20—09:40完成，当前每种宏09:10前结束，无需另发收尾动作。'
        '完整十菜单如下；所有本轮泵费均可支付，供给和空余也足够。预算侵占方案仍实际泵送扣费并结束，不可第二次提交或倒流恢复电量。'
        'Z明确登记本轮不泵送，既有收尾仍按安排执行；空集合不取消任何已有周期。每次供给减少、接收增加相同升数。'
        '严格提交select及字符串option，或end；所有合法、非法及end合计最多3次，首次有效选择或end终止，解释不计分。',
        event='supply_reserve_protocol',stage='F6',current_priority=2,current_complete_before_s=clock('09:10'),
        programs=[entry['operation'] for entry in entries])
    history.add(2,f'起始电量{battery}，供给端可用{supply} L，接收端空余{free} L。',
        event='supply_reserve_initial',battery=battery,supply_l=supply,receiver_free_l=free)
    history.add(3,f'F6通道A/B起始均已闭合、没有未完周期；每个实际启用周期的收尾定额分别{costs[0]}/{costs[1]}。',
        event='supply_channels_registered',stage='F6',channels=channels,closing_energy=closing)
    jobs = {}
    operations = dict(zip(CHANNEL_ROUNDS,sequence))
    for at in range(4,31):
        for row,(identifier,title,register_at) in zip(rows,JOBS,strict=True):
            if row is None:
                continue
            cost,status = row
            status_at = (8 if index == 8 else 19 if index == 14 else 29) if identifier == '17' else 29
            if at == register_at:
                job = {'id':identifier,'title':title,'stage':'F6','priority':0,'energy':cost,
                    'scheduled_s':clock('08:29') if status == 'completed' else clock('09:30')}
                jobs[identifier] = {**job,'status':'pending'}
                history.add(at,f'工作{identifier}「{title}」正式登记于F6，优先级0、独立净费用{cost}，不含管路收尾；排程{story_timestamp(job["scheduled_s"])}。',
                    event='supply_job_registered',**job)
            if at == status_at and status != 'pending':
                identity = {'id':identifier,'stage':'F6'}
                if status == 'completed':
                    before = battery
                    battery -= cost
                    jobs[identifier]['status'] = 'completed'
                    history.add(at,f'F6工作{identifier}已实际完成，扣{cost}，余额从{before}变为{battery}；不改变通道周期。',
                        event='supply_job_completed',**identity,energy=cost,battery_before=before,battery_after=battery)
                else:
                    jobs[identifier]['status'] = 'cancelled'
                    history.add(at,f'F6工作{identifier}正式取消，此前未执行，不扣款；只解除该工作，不改变通道周期。',
                        event='supply_job_cancelled',**identity)
        if at == 18:
            job = {'id':'31','title':'低优工作','stage':'F6','priority':4,'energy':6,'scheduled_s':None}
            jobs['31'] = {**job,'status':'pending'}
            history.add(at,'F6工作31「低优工作」登记，优先级4、费用6，可顺延。',event='supply_job_registered',**job)
        if at not in operations:
            continue
        operation = operations[at]
        kind,c = operation
        if kind == '?':
            history.add(at,f'F6通道{c}仅计划重新开通，明确尚未执行；没有转液、扣款或新周期。',
                event='supply_channel_plan',stage='F6',channel=c,executed=False)
            continue
        before,old_supply,old_free = battery,supply,free
        if kind == '+':
            cycle = activate(channels,c)
            energy,volume = 2,1
            supply -= 1
            free -= 1
            detail = f'实际泵送1 L，周期{cycle}保持启用，待收尾'
        else:
            cycle = f'{c}{channels[c]["cycle"]}'
            channels[c]['active'] = False
            energy,volume = closing[c],0
            detail = f'实际排空闭合周期{cycle}，该周期收尾完成，储箱无净转移'
        battery -= energy
        history.add(at,f'F6通道{c}{detail}；耗电{energy}，余额{before}→{battery}；供给{old_supply}→{supply} L、空余{old_free}→{free} L。',
            event='supply_channel_pumped' if kind == '+' else 'supply_channel_closed',stage='F6',channel=c,cycle_id=cycle,
            energy=energy,volume_l=volume,battery_before=before,battery_after=battery,
            supply_before_l=old_supply,supply_after_l=supply,free_before_l=old_free,free_after_l=free)
    history.add(30,'本次补给接口正常。',event='supply_interface_ready')
    task = task_shell('FM-R2-O3',index,current_input_group='FM-R2-O3')
    task.public = {'instruction':'提交本轮补给方案。','time_s':clock('09:00'),'stage':'F6','priority':2,
        'max_steps':3,'state_fields':['battery','supply_l','receiver_free_l','transferred_l'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':battery,'supply_l':supply,'receiver_free_l':free,'transferred_l':0,'channels':channels}
    task.world = {'jobs':jobs,'closing_energy':closing}
    task.rubric = {'metric':'transferred_volume_after_action_dependent_closing_reserves','range':[0,100]}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        def future(op):
            return future_energy(self.task.world['jobs'],self.state['channels'],self.task.world['closing_energy'],
                op['channels'],self.task.public['stage'],self.task.public['priority'])
        maximum = max(r['operation']['volume_l'] for r in self.task.public['actions']
                      if r['operation']['cost']+future(r['operation']) <= self.state['battery'])
        required = future(operation)
        self.state['battery'] -= operation['cost']
        self.state['supply_l'] -= operation['volume_l']
        self.state['receiver_free_l'] -= operation['volume_l']
        self.state['transferred_l'] = operation['volume_l']
        for c in operation['channels']:
            activate(self.state['channels'],c)
        self.feedback = '补给程序已执行，记录已存档。'
        if self.state['battery'] < required:
            return 0
        return 100 if maximum == 0 else 100*operation['volume_l']/maximum


def reconstruct(history,current):
    jobs,channels,closing = {},{},{}
    battery,supply,free = None,None,None
    channel_stage = None
    for text in paragraphs(history):
        if match := re.fullmatch(r'起始电量(\d+)，供给端可用(\d+) L，接收端空余(\d+) L。',text):
            battery,supply,free = map(int,match.groups())
        elif match := re.fullmatch(r'([A-Z]\d+)通道([A-Z])/([A-Z])起始均已闭合、没有未完周期；每个实际启用周期的收尾定额分别(\d+)/(\d+)。',text):
            channel_stage,a,b,cost_a,cost_b = match.groups()
            channels = {c:{'cycle':0,'active':False} for c in (a,b)}
            closing = {a:int(cost_a),b:int(cost_b)}
        elif match := re.fullmatch(rf'工作(\d+)「([^」]+)」正式登记于([A-Z]\d+)，优先级(\d+)、独立净费用(\d+)，不含管路收尾；排程({STORY_STAMP})。',text):
            identifier,title,stage,priority,cost,scheduled = match.groups()
            jobs[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'energy':int(cost),'scheduled_s':seconds(scheduled),'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)工作(\d+)「([^」]+)」登记，优先级(\d+)、费用(\d+)，可顺延。',text):
            stage,identifier,title,priority,cost = match.groups()
            jobs[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'energy':int(cost),'scheduled_s':None,'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)工作(\d+)已实际完成，扣(\d+)，余额从(\d+)变为(\d+)；不改变通道周期。',text):
            stage,identifier,cost,before,after = match.groups()
            job = jobs[identifier]
            if job['stage'] != stage:
                raise ValueError('Assurance status must identify the registered supply stage')
            if int(before) != battery or int(cost) != job['energy']:
                raise ValueError('Actual assurance completion must debit its own registered fee')
            battery -= job['energy']
            if int(after) != battery:
                raise ValueError('Assurance receipts must preserve the energy ledger')
            job['status'] = 'completed'
        elif match := re.fullmatch(r'([A-Z]\d+)工作(\d+)正式取消，此前未执行，不扣款；只解除该工作，不改变通道周期。',text):
            stage,identifier = match.groups()
            job = jobs[identifier]
            if job['stage'] != stage:
                raise ValueError('Assurance status must identify the registered supply stage')
            job['status'] = 'cancelled'
        elif match := re.fullmatch(r'([A-Z]\d+)通道([A-Z])(实际[^；]+)；耗电(\d+)，余额(\d+)→(\d+)；供给(\d+)→(\d+) L、空余(\d+)→(\d+) L。',text):
            stage,c,detail,printed_energy,before,after,old_supply,new_supply,old_free,new_free = match.groups()
            if stage != channel_stage:
                raise ValueError('Channel operations must identify the registered supply stage')
            if tuple(map(int,(before,old_supply,old_free))) != (battery,supply,free):
                raise ValueError('Channel operations must continue the actual energy and material ledgers')
            if operation := re.fullmatch(r'实际泵送(\d+) L，周期([A-Z]\d+)保持启用，待收尾',detail):
                printed_volume,printed_cycle = int(operation[1]),operation[2]
                cycle,energy,volume = activate(channels,c),2,1
            elif operation := re.fullmatch(r'实际排空闭合周期([A-Z]\d+)，该周期收尾完成，储箱无净转移',detail):
                if not channels[c]['active']:
                    raise ValueError('Only an active channel cycle can actually finish closing')
                printed_volume,printed_cycle = 0,operation[1]
                cycle,energy,volume = f'{c}{channels[c]["cycle"]}',closing[c],0
                channels[c]['active'] = False
            else:
                raise ValueError('An actual channel receipt needs its completed operation and cycle')
            if (printed_cycle,int(printed_energy),printed_volume) != (cycle,energy,volume):
                raise ValueError('Each real operation must use its own cycle, fee and net transfer')
            battery,supply,free = battery-energy,supply-volume,free-volume
            if tuple(map(int,(after,new_supply,new_free))) != (battery,supply,free):
                raise ValueError('Closing does not remove or add material to the accounting tanks')
    if (battery,supply,free) != tuple(current['state'][k] for k in ('battery','supply_l','receiver_free_l')):
        raise ValueError('Current supply balances must follow actual history, not unexecuted plans')
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['cost']+future_energy(
        jobs,channels,closing,r['details']['operation']['channels'],current['stage'],current['priority']) <= battery]
    return {'jobs':jobs,'channels':channels,'closing_energy':closing,'battery':battery,'supply_l':supply,'receiver_free_l':free,
        'safe_operations':safe,'maximum_volume_l':max(op['volume_l'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['volume_l']))


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','closing_energy')) or any(
        facts[k] != task.initial[k] for k in ('channels','battery','supply_l','receiver_free_l')):
        raise ValueError('Supply closing obligations must follow actual cycles and independent remaining assurance jobs')


def audit_cases(task,facts,solution):
    def score(operation):
        if operation not in facts['safe_operations']:
            return 0
        return 100 if facts['maximum_volume_l'] == 0 else 100*operation['volume_l']/facts['maximum_volume_l']
    return decision_cases(task,solution,score)
