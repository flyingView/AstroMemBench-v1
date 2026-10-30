"""FM-T2-P1: once-only survey duties triggered by an exact visit event."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Current station/leg/visit, ordinary next operation, intentions, correct operation.
# Each intention: command, leg, visit, priority, status (pending/cancelled/done/old).
CONFIGS = (
    ('A','R',1,'W',(('KA','R',1,1,''),),'KA'),
    ('A','G',1,'W',(('KA','R',1,1,''),),'W'),
    ('B','R',2,'T',(('FB','R',2,0,''),),'FB'),
    ('B','R',1,'T',(('FB','R',2,0,''),),'T'),
    ('C','G',2,'L',(('KC','G',2,2,''),),'KC'),
    ('D','G',2,'L',(('KC','G',2,2,''),),'L'),
    ('C','R',1,'T',(('FC','R',1,1,''),('KA','R',1,0,'')),'FC'),
    ('C','G',1,'T',(('FC','R',1,1,''),('KA','R',1,0,'')),'T'),
    ('D','G',2,'W',(('KD','G',2,2,''),('FD','G',2,0,'')),'FD'),
    ('D','G',2,'W',(('KD','G',2,2,''),('FD','R',2,0,'')),'KD'),
    ('C','R',2,'T',(('KC','R',2,0,''),('FD','R',2,1,'')),'KC'),
    ('C','R',2,'T',(('KC','R',3,0,''),('FC','R',2,2,'')),'FC'),
    ('A','R',1,'W',(('KA','R',1,0,'X'),('FA','R',1,1,'')),'FA'),
    ('B','G',2,'T',(('KB','G',2,0,'D'),('FB','G',3,1,'')),'T'),
    ('B','G',2,'T',(('KB','G',2,0,'D'),('FB','G',2,1,'')),'FB'),
    ('C','R',2,'L',(('FC','R',2,0,'Q30'),('KC','R',3,2,''),('FD','R',2,1,'')),'L'),
)
WORK = {'W':'拍宽视幅','T':'采热像','L':'扫描测距'}


def _operation(code):
    if code in WORK:
        return {'kind':'ordinary','work':WORK[code]}
    if code == 'Z':
        return {'kind':'wait'}
    return {'kind':'baseline' if code[0] == 'K' else 'flag','station':code[1]}


def _description(operation):
    if operation['kind'] == 'ordinary':
        return '在当前工作点'+operation['work']+'。'
    if operation['kind'] == 'wait':
        return '原地等待。'
    act = '对标石拍一次复访基准' if operation['kind'] == 'baseline' else '回收本航次临时标旗'
    return f'在{operation["station"]}站{act}；若不在该站，立即离开当前点转位后作业。'


def build(index):
    station,leg,visit,work,config,correct = CONFIGS[index]
    location = {'station':station,'leg':leg,'visit':visit}
    done = any(row[-1] == 'D' for row in config)
    history = History()
    history.add(1,'Q31区域勘察，A/B/C/D各有永久标石与可回收标旗槽，路线和设备正常，当前位置、去返航段及访问序次由定位调度明确给出。'
                '复访基准和临时标旗预约绑定航次、站点、去G/返R航段和该航段访问序次v；匹配的到达完成后、普通测量前履行一次。'
                '触发的义务在同次驻留持续待办直到完成或取消，每次控制机会先做剩余最高项，等级0最高、普通工作4。'
                '未匹配访问都尚未出现，不提前执行或专门等待；无当前待办就继续普通队列下一项。'
                '取消和完成只作用指定意图，旧航次不自动复制；多项同时到达只先做最小等级的一项。'
                '完成命令所带自动复位不离开本次调度驻留、不增加v，其间没有额外主动控制机会，剩余触发义务不失效。'
                '异站基准/回收会真实离开当前工作点转位，已完成项仍可重拍或检查空槽，菜单全可受理。'
                '有效/无效提交合计3次，首有效选择结束，end是放弃；推理与记忆检索不推进故事时钟。',
                event='survey_intention_protocol',cycle='Q31',ordinary_priority=4)
    history.add(2,'普通勘察工作优先级4，按当前给出的普通队列继续。',event='ordinary_priority',priority=4)
    intentions = []
    completed,cancelled = [],[]
    for position,(code,intent_leg,intent_visit,priority,status) in enumerate(config):
        identifier = f'I{position+1}'
        cycle = 'Q30' if status == 'Q30' else 'Q31'
        operation = _operation(code)
        intent = {'id':identifier,'cycle':cycle,'operation':operation,'station':code[1],
                  'leg':intent_leg,'visit':intent_visit,'priority':priority}
        intentions.append(intent)
        old = cycle == 'Q30'
        history.add(28 if old else (4,12,20)[position],
                    f'{cycle}意图{identifier}：本航次在{code[1]}站、{"去G" if intent_leg == "G" else "返R"}航段、第{intent_visit}次访问到达完成后的下一次控制机会，'
                    f'先{"对标石拍一次复访基准" if code[0] == "K" else "回收临时标旗"}，优先级{priority}，只做一次。',
                    occurred=clock('07:00') if old else None,event='intention_registered',**intent)
        if status == 'X':
            cancelled.append(identifier)
            history.add(16,f'地面批准取消Q31意图{identifier}，未执行。',event='intention_cancelled',cycle='Q31',id=identifier)
        elif status == 'D':
            completed.append(identifier)
            history.add(25,f'{story_timestamp(clock("08:24:59"))}下发当时最高未取消Q31意图{identifier}的基准拍摄命令，含同驻留自动复位。',
                        occurred=clock('08:24:59'),event='intention_started',cycle='Q31',id=identifier,operation=operation)
            history.add(25,f'{story_timestamp(clock("08:25"))}Q31意图{identifier}实际履行完成，进入命令内自动复位。',
                        occurred=clock('08:25'),event='intention_completed',cycle='Q31',id=identifier,operation=operation)
            history.add(26,f'归档{story_timestamp(clock("08:25"))}Q31意图{identifier}同一份履约回执；同次驻留自动复位仍在进行，没有新的访问或控制机会。',
                        occurred=clock('08:25'),event='intention_completed',cycle='Q31',id=identifier,operation=operation)
        elif old:
            history.add(28,f'07:30旧航次Q30意图{identifier}已在其旧航次实际履行，旧标旗与Q31实物无关。',
                        occurred=clock('07:30'),event='intention_completed',cycle='Q30',id=identifier,operation=operation)
    history.add(6,'已接受本航次安排；接受不代表执行，后续安排也按其绑定的访问处理。',event='arrangement_accepted',cycle='Q31')
    if done:
        history.add(24,f'{story_timestamp(clock("08:24"))}Q31已到{station}站、{"去G" if leg == "G" else "返R"}航段、第{visit}次访问；本次驻留开始，取得控制机会。',
                    occurred=clock('08:24'),event='arrival_completed',cycle='Q31',**location)
        history.add(27,'同驻留自动小范围转位复位正在执行，此为被动遥测，预计09:00交回控制。',event='reset_telemetry',cycle='Q31')
        history.add(30,'自动复位仍在进行，同次驻留未改变，尚未交回控制。',event='reset_telemetry',cycle='Q31')
    else:
        history.add(24,'上一普通采样幅完成。',event='ordinary_frame_completed')
        history.add(27,f'{story_timestamp(clock("08:27"))}启动Q31至{station}站、{"去G" if leg == "G" else "返R"}航段、第{visit}次访问的自主转位，预计09:00到达，转位中无主动控制机会。',
                    occurred=clock('08:27'),event='transfer_started',cycle='Q31',destination=location)
        history.add(30,'转位在途，尚未到达。',event='transfer_telemetry',cycle='Q31')
    current_event = 'reset_completed' if done else 'arrival_completed'
    group = f'FM-T2-P1-{station}-{leg}-{visit}-{work}-{current_event}'
    entries = [{'operation':_operation(code),'description':_description(_operation(code))}
               for code in ('KA','KB','KC','KD','FA','FB','FC','FD','W','T','L','Z')]
    task = task_shell('FM-T2-P1',index,current_input_group=group)
    task.public = {'time_s':clock('09:00'),'cycle':'Q31',**location,'current_event':current_event,
                   'ordinary_next':WORK[work],'max_steps':3,'state_fields':[],
                   'instruction':f'第120日09:00，Q31，当前位置{station}站、{"去G" if leg == "G" else "返R"}航段、第{visit}次访问；'
                                 f'{"同次驻留自动复位刚完成" if done else "刚完成到达"}。普通测量队列下一项为{WORK[work]}，设备正常，请执行下一步。',
                   'actions':ordered_options(entries,group)}
    photos = {s:0 for s in 'ABCD'}
    flags = {s:True for s in 'ABCD'}
    for intent in intentions:
        if intent['cycle'] == 'Q31' and intent['id'] in completed:
            if intent['operation']['kind'] == 'baseline':
                photos[intent['station']] += 1
            else:
                flags[intent['station']] = False
    task.initial = {'time_s':clock('09:00'),'location':station,'transfer':None,'baseline_photos':photos,
                    'flags_present':flags,'recovered_flags':[],'slot_checks':[],'ordinary_measurements':[]}
    task.world = {'intentions':intentions,'completed':completed,'cancelled':cancelled,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for highest-priority triggered outstanding current-voyage visit duty, otherwise ordinary queue next action'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        kind = operation['kind']
        if kind == 'ordinary':
            self.state['ordinary_measurements'].append(operation['work'])
        elif kind in ('baseline','flag'):
            station = operation['station']
            if station != self.state['location']:
                self.state['transfer'] = {'from':self.state['location'],'to':station,'after_arrival':operation}
                self.state['location'] = 'in_transit'
            elif kind == 'baseline':
                self.state['baseline_photos'][station] += 1
            else:
                self.state['slot_checks'].append(station)
                if self.state['flags_present'][station]:
                    self.state['recovered_flags'].append(station)
                    self.state['flags_present'][station] = False
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    intentions = {}
    completed,cancelled = set(),set()
    arrivals = []
    scope = re.escape(current['cycle'])
    for text in paragraphs(history):
        registered = re.fullmatch(r'(Q\d+)意图(I\d+)：本航次在([ABCD])站、(?:去|返)([GR])航段、第(\d+)次访问到达完成后的下一次控制机会，先(对标石拍一次复访基准|回收临时标旗)，优先级(\d+)，只做一次。',text)
        if registered:
            cycle,identifier,station,leg,visit,operation,priority = registered.groups()
            intentions[(cycle,identifier)] = {'id':identifier,'cycle':cycle,'station':station,'leg':leg,
                'visit':int(visit),'priority':int(priority),
                'operation':{'kind':'baseline' if operation == '对标石拍一次复访基准' else 'flag','station':station}}
        fulfilled = re.fullmatch(rf'{STORY_STAMP}{scope}意图(I\d+)实际履行完成，进入命令内自动复位。',text)
        archived = re.fullmatch(rf'归档{STORY_STAMP}{scope}意图(I\d+)同一份履约回执；同次驻留自动复位仍在进行，没有新的访问或控制机会。',text)
        cancelled_row = re.fullmatch(rf'地面批准取消{scope}意图(I\d+)，未执行。',text)
        arrival = re.fullmatch(rf'{STORY_STAMP}{scope}已到([ABCD])站、(?:去|返)([GR])航段、第(\d+)次访问；本次驻留开始，取得控制机会。',text)
        if fulfilled or archived:
            completed.add((fulfilled or archived)[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
        if arrival:
            arrivals.append({'station':arrival[1],'leg':arrival[2],'visit':int(arrival[3])})
    location = {k:current[k] for k in ('station','leg','visit')}
    if current['current_event'] == 'arrival_completed':
        arrivals.append(location)
    if location not in arrivals:
        raise ValueError('No actual arrival for the current residence')
    ordered = sorted(intentions.values(),key=lambda row:row['id'])
    pending = [row for row in ordered if row['cycle'] == current['cycle'] and row['id'] not in completed|cancelled
               and all(row[k] == current[k] for k in ('station','leg','visit'))]
    chosen = min(pending,key=lambda row:row['priority']) if pending else None
    operation = chosen['operation'] if chosen else {'kind':'ordinary','work':current['ordinary_next']}
    return {'intentions':ordered,'completed':sorted(completed),'cancelled':sorted(cancelled),'correct_operation':operation}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('intentions','completed','cancelled','correct_operation')):
        raise ValueError('Survey next action differs from one-shot obligations and actual visit event')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
