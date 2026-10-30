"""FM-T2-O1: prospective inspections at individual count milestones."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

# Counts A/B/C/D, next ordinary group, (operation, first count, interval, priority, state), answer.
CONFIGS = (
    ((3,2,4,1),'W',(('DA',3,0,1,''),),'DA'),
    ((2,2,4,1),'W',(('DA',3,0,1,''),),'W'),
    ((2,4,1,3),'N',(('RB',4,0,0,''),),'RB'),
    ((2,3,1,3),'N',(('RB',4,0,0,''),),'N'),
    ((2,6,4,3),'T',(('DB',6,0,0,''),),'DB'),
    ((2,5,4,3),'T',(('DB',6,0,0,''),),'T'),
    ((3,4,2,5),'W',(('DA',3,0,2,''),('RB',4,0,0,'')),'RB'),
    ((3,3,2,5),'W',(('DA',3,0,2,''),('RB',4,0,0,'')),'DA'),
    ((4,2,5,3),'N',(('RC',5,0,1,''),('DD',4,0,0,'')),'RC'),
    ((4,2,4,3),'N',(('RC',5,0,1,''),('DD',4,0,0,'')),'N'),
    ((3,2,6,4),'N',(('DC',6,0,2,''),('RD',4,0,0,'')),'RD'),
    ((3,2,6,3),'N',(('DC',6,0,2,''),('RD',4,0,0,'')),'DC'),
    ((6,4,3,3),'W',(('DA',3,3,0,'P'),('RB',5,0,1,'')),'DA'),
    ((5,4,3,2),'W',(('DA',3,3,0,'P'),('RB',5,0,1,'')),'W'),
    ((4,3,5,2),'T',(('RC',5,0,0,'X'),('DC',5,0,1,'D'),('RA',4,0,2,'')),'RA'),
    ((3,2,4,6),'W',(('DD',6,0,0,'Q50'),('RD',6,0,2,''),('DB',3,0,1,'')),'RD'),
)
GROUP_NAMES = {'W':'宽视','N':'窄视','T':'热像'}
REFERENCE_NAMES = {'dark':'遮光参考','recess':'凹部复看'}


def _operation(code):
    if code == 'Z':
        return {'kind':'wait'}
    if code in GROUP_NAMES:
        return {'kind':'ordinary_group','group':GROUP_NAMES[code]}
    return {'kind':'reference','component':code[1],'mode':'dark' if code[0] == 'D' else 'recess'}


def _description(operation):
    if operation['kind'] == 'wait':
        return '原地等待。'
    if operation['kind'] == 'ordinary_group':
        return f'对A/B/C/D各采一帧{operation["group"]}图像，完成一个普通巡检组。'
    return f'为部件{operation["component"]}采集一帧{REFERENCE_NAMES[operation["mode"]]}图像，不增加普通组计数。'


def build(index):
    values,next_group,config,correct = CONFIGS[index]
    counts = dict(zip('ABCD',values,strict=True))
    periodic = any(r[-1] == 'P' for r in config)
    reset = any(r[-1] == 'D' for r in config)
    initial_values = (3,1,0,0) if index == 12 else (3,2,1,0) if index == 13 else tuple(c-1 for c in values)
    previous_counts = dict(zip('ABCD',initial_values,strict=True))
    history = History()
    history.add(1,'巡检批Q51，部件A/B/C/D各有普通组计数；一个普通组给四部件各采一帧且全部成功时各加1。'
                '遮光参考和凹部复看不增加此计数；设备参数、姿态、成像质量均已保证，不需视觉判断。'
                '单次预约在指定部件计数首次达到k后下一控制机会履行。周期预约从b开始每隔d组、j=0,1,2…各有独立里程碑；'
                '完成m不等于完成m+d，登记时已在起始里程碑也立即履行。已触发项持续待办，取消仅针对声明的当前里程碑，旧Q50不迁移。'
                '等级0最高，普通组4，只在当前已达到且未完成未取消里程碑内选最小等级。未到下个里程碑就继续普通组，不提前拍或等待。'
                '自动流水线不插入预约；参考完成附带姿态复位期间没有其他主动控制机会，复位不加计数。'
                '十二命令始终可受理，错误或重复参考仍真实成像；有效无效共3次，首有效选择终止，end放弃。'
                '推理与检索不推进故事时间。',event='milestone_protocol',cycle='Q51',ordinary_priority=4)
    history.add(2,'普通巡检工作等级4。',event='ordinary_priority',priority=4)
    history.add(3,f'{story_timestamp(clock("08:03"))}，Q51当前批起始普通组计数为'+
                '、'.join(f'{b}={c}' for b,c in previous_counts.items())+'。'+('A已到3，但此前尚无DA预约。' if periodic else ''),
                event='initial_counts',cycle='Q51',counts=previous_counts)
    intentions,completed,cancelled = [],[],[]
    for position,(code,first,interval,priority,status) in enumerate(config):
        identifier = f'I{position+1}'
        cycle = 'Q50' if status == 'Q50' else 'Q51'
        operation = _operation(code)
        intention = {'id':identifier,'cycle':cycle,'operation':operation,'first':first,'interval':interval,'priority':priority}
        intentions.append(intention)
        milestone_text = f'{first}+{interval}×j，j=0,1,2…' if interval else str(first)
        history.add(28 if cycle == 'Q50' else (4,12,20)[position],
                    f'{cycle}预约{identifier}：部件{code[1]}普通组计数到{milestone_text}时，采集{REFERENCE_NAMES[operation["mode"]]}，等级{priority}。',
                    occurred=clock('07:00') if cycle == 'Q50' else None,event='milestone_registered',**intention)
        if status == 'X':
            cancelled.append([identifier,first])
            history.add(16,f'正式取消Q51预约{identifier}的当前里程碑{first}，未执行。',
                        event='milestone_cancelled',cycle='Q51',id=identifier,milestone=first)
        elif status in ('P','D'):
            completed.append([identifier,first])
            at = '08:04:10' if status == 'P' else '08:25'
            if status == 'D':
                history.add(25,'08:24:59开始当时最高未取消DC里程碑5，命令附带完成后自动姿态复位。',
                            occurred=clock('08:24:59'),received=clock('08:25'),event='reference_started',cycle='Q51',id=identifier,milestone=first,operation=operation)
            history.add(4 if status == 'P' else 25,f'{story_timestamp(clock(at))}，Q51预约{identifier}里程碑{first}实际成像完成。',
                        occurred=clock(at),received=clock(at)+(1 if status == 'D' else 0),event='milestone_completed',cycle='Q51',id=identifier,milestone=first,operation=operation)
            history.add(24 if status == 'P' else 26,f'归档{story_timestamp(clock(at))}，Q51预约{identifier}已完成的同一里程碑{first}回执，不是现在才履行。',
                        occurred=clock(at),event='milestone_completed',cycle='Q51',id=identifier,milestone=first,operation=operation)
    history.add(6,'已收到本批预约安排，接受不表示已经拍摄。',event='arrangement_accepted',cycle='Q51')
    if periodic:
        for minute in ((10,18) if index == 12 else (18,)):
            previous_counts = {b:c+1 for b,c in previous_counts.items()}
            history.add(minute,f'{story_timestamp(clock(f"08:{minute:02d}"))}，Q51普通巡检组实际完成，四计数各加1，现为'+
                        '、'.join(f'{b}={c}' for b,c in previous_counts.items())+'。',occurred=clock(f'08:{minute:02d}'),
                        event='ordinary_group_completed',cycle='Q51',counts=previous_counts)
    if reset:
        history.add(21,'08:21开始普通热像巡检组。',occurred=clock('08:21'),event='ordinary_group_started',cycle='Q51',group=GROUP_NAMES[next_group])
        history.add(24,f'{story_timestamp(clock("08:24"))}，Q51普通巡检组实际完成，四计数各加1，现为'+
                    '、'.join(f'{b}={c}' for b,c in counts.items())+'。',occurred=clock('08:24'),event='ordinary_group_completed',cycle='Q51',counts=counts)
        history.add(27,'预约内置的自动姿态复位仍在进行，09:00归还控制，计数不变。',event='reset_telemetry',cycle='Q51')
        history.add(30,'仍在自动复位，没有新普通组、没有新的主动控制机会。',event='reset_telemetry',cycle='Q51')
    else:
        history.add(27,f'08:27开始一组普通{GROUP_NAMES[next_group]}巡检，09:00完成归还控制。',
                    occurred=clock('08:27'),event='ordinary_group_started',cycle='Q51',group=GROUP_NAMES[next_group])
        history.add(30,'普通组采集中，尚未完成，暂无新的主动控制机会。',event='ordinary_group_telemetry',cycle='Q51')
    current_event = 'reset_completed' if reset else 'ordinary_group_completed'
    group = f'FM-T2-O1-{values}-{next_group}-{current_event}'
    entries = [{'operation':_operation(code),'description':_description(_operation(code))}
               for code in ('DA','DB','DC','DD','RA','RB','RC','RD','W','N','T','Z')]
    task = task_shell('FM-T2-O1',index,current_input_group=group)
    task.public = {'time_s':clock('09:00'),'cycle':'Q51','counts':counts,'ordinary_next':GROUP_NAMES[next_group],
                   'current_event':current_event,'max_steps':3,'state_fields':[],
                   'instruction':'第120日09:00，Q51，'+('自动姿态复位刚完成，计数未改变' if reset else '普通巡检组刚完成')
                                 +f'；A/B/C/D计数{values}，下一普通组为{GROUP_NAMES[next_group]}，设备正常。请执行下一步操作。',
                   'actions':ordered_options(entries,group)}
    references = {b:{mode:0 for mode in REFERENCE_NAMES} for b in 'ABCD'}
    for identifier,milestone in completed:
        row = next(r for r in intentions if r['cycle'] == 'Q51' and r['id'] == identifier)
        op = row['operation']
        references[op['component']][op['mode']] += 1
    task.initial = {'time_s':clock('09:00'),'counts':counts,'references':references,'new_groups':[],'new_references':[]}
    task.world = {'intentions':intentions,'completed':completed,'cancelled':cancelled,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for the highest-priority reached outstanding milestone, otherwise the next ordinary group'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'ordinary_group':
            self.state['counts'] = {b:c+1 for b,c in self.state['counts'].items()}
            self.state['new_groups'].append(operation['group'])
        elif operation['kind'] == 'reference':
            self.state['references'][operation['component']][operation['mode']] += 1
            self.state['new_references'].append(operation)
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    intentions,completed,cancelled = {},set(),set()
    count_events = []
    scope = re.escape(current['cycle'])
    for text in paragraphs(history):
        registered = re.fullmatch(r'(Q\d+)预约(I\d+)：部件([ABCD])普通组计数到(\d+)(?:\+(\d+)×j，j=0,1,2…)?时，采集(遮光参考|凹部复看)，等级(\d+)。',text)
        if registered:
            cycle,identifier,component,first,interval,mode,priority = registered.groups()
            intentions[(cycle,identifier)] = {'id':identifier,'cycle':cycle,'first':int(first),'interval':int(interval) if interval else 0,
                'priority':int(priority),'operation':{'kind':'reference','component':component,'mode':'dark' if mode == '遮光参考' else 'recess'}}
        fulfilled = re.fullmatch(rf'{STORY_STAMP}，{scope}预约(I\d+)里程碑(\d+)实际成像完成。',text)
        archived = re.fullmatch(rf'归档{STORY_STAMP}，{scope}预约(I\d+)已完成的同一里程碑(\d+)回执，不是现在才履行。',text)
        cancelled_row = re.fullmatch(rf'正式取消{scope}预约(I\d+)的当前里程碑(\d+)，未执行。',text)
        initial = re.fullmatch(rf'({STORY_STAMP})，{scope}当前批起始普通组计数为A=(\d+)、B=(\d+)、C=(\d+)、D=(\d+)。(?:A已到3，但此前尚无DA预约。)?',text)
        group = re.fullmatch(rf'({STORY_STAMP})，{scope}普通巡检组实际完成，四计数各加1，现为A=(\d+)、B=(\d+)、C=(\d+)、D=(\d+)。',text)
        if fulfilled or archived:
            matched = fulfilled or archived
            completed.add((matched[1],int(matched[2])))
        if cancelled_row:
            cancelled.add((cancelled_row[1],int(cancelled_row[2])))
        if initial or group:
            matched = initial or group
            count_events.append((seconds(matched[1]),'initial_counts' if initial else 'ordinary_group_completed',
                                 dict(zip('ABCD',map(int,matched.groups()[1:]),strict=True))))
    count_events.sort()
    if not count_events or count_events[0][1] != 'initial_counts':
        raise ValueError('Initial ordinary-group counts missing from public history')
    counts = count_events[0][2]
    for _,_,actual in count_events[1:]:
        if actual != {b:c+1 for b,c in counts.items()}:
            raise ValueError('Historical ordinary-group counts are not actual single increments')
        counts = actual
    if current['current_event'] == 'ordinary_group_completed':
        counts = {b:c+1 for b,c in counts.items()}
    if counts != current['counts']:
        raise ValueError('Current raw counts differ from actual public group completions')
    ordered = sorted(intentions.values(),key=lambda row:row['id'])
    due = []
    for row in ordered:
        if row['cycle'] != current['cycle']:
            continue
        milestone = row['first']
        while (row['id'],milestone) in completed|cancelled and row['interval']:
            milestone += row['interval']
        if (row['id'],milestone) not in completed|cancelled and current['counts'][row['operation']['component']] >= milestone:
            due.append(row)
    first = min(due,key=lambda r:r['priority']) if due else None
    operation = first['operation'] if first else {'kind':'ordinary_group','group':current['ordinary_next']}
    return {'intentions':ordered,'completed':[list(r) for r in sorted(completed)],'cancelled':[list(r) for r in sorted(cancelled)],'correct_operation':operation}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('intentions','completed','cancelled','correct_operation')):
        raise ValueError('Milestone next action differs from public counts and individual fulfillment records')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
