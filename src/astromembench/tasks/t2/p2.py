"""FM-T2-P2: honor timed sample obligations while continuing registration."""
import re

from ..common import ArchiveHistory, clock, fixed_options, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

# Appointments: action, start, end, priority, cycle, state, optional acquisition/delay/width.
CONFIGS = (
    ('10:18','w',(('CA','10:16','10:21',1,'Q22','',None),),'CA'),
    ('10:18','w',(('CA','10:22','10:27',1,'Q22','',None),),'w'),
    ('11:09','c',(('SB','11:08','11:12',0,'Q22','',None),),'SB'),
    ('09:30','r',(('FB','09:30','09:34',1,'Q22','',('08:10',80,4)),),'FB'),
    ('10:02','c',(('TA','10:00','10:05',2,'Q22','',('08:40',80,5)),),'TA'),
    ('10:02','c',(('TA','10:06','10:11',2,'Q22','',('08:40',86,5)),),'c'),
    ('12:24','r',(('FA','12:22','12:27',1,'Q22','',None),('CB','12:30','12:36',0,'Q22','',None)),'FA'),
    ('13:41','c',(('SA','13:45','13:49',0,'Q22','',None),('CB','13:50','13:55',1,'Q22','',None)),'c'),
    ('14:12','w',(('TB','14:10','14:15',2,'Q22','',None),('FA','14:12','14:18',3,'Q22','',None)),'TB'),
    ('09:10','w',(('CB','09:08','09:13',1,'Q22','',('07:40',88,5)),('SA','09:10','09:14',0,'Q22','',('07:35',95,4))),'SA'),
    ('13:05','w',(('SB','13:05','13:09',2,'Q22','',('11:30',95,4)),('CA','13:04','13:10',0,'Q22','',('11:25',99,6))),'CA'),
    ('13:05','w',(('SB','13:05','13:09',2,'Q22','',('11:30',95,4)),('CA','13:09','13:15',0,'Q22','',('11:25',104,6))),'SB'),
    ('15:06','r',(('CB','15:00','15:10',0,'Q21','',None),('CB','15:04','15:09',0,'Q22','X',None),('SA','15:05','15:08',1,'Q22','',None)),'SA'),
    ('16:20','c',(('FA','16:18','16:22',1,'Q22','D',None),('TB','16:24','16:29',0,'Q22','',None)),'c'),
    ('11:12','r',(('CB','11:10','11:15',0,'Q22','D',('09:30',100,5)),('FA','11:12','11:16',1,'Q22','',('09:35',97,4))),'FA'),
    ('11:12','r',(('CB','11:10','11:15',0,'Q22','D',('09:30',100,5)),('FA','11:16','11:20',1,'Q22','',('09:35',101,4))),'r'),
)
FIXED_MENUS = {
    0:('SB','TB','CB','r','FA','FB','c','CA','w','z','TA','SA'),
    1:('c','SA','r','w','FB','TB','SB','CA','CB','TA','FA','z'),
    2:('SA','z','SB','FB','TB','r','FA','CB','w','TA','CA','c'),
    6:('w','CB','c','z','CA','SB','TB','FA','SA','r','FB','TA'),
    7:('CA','FA','TA','TB','z','FB','r','w','c','SB','CB','SA'),
    8:('CB','FB','TB','c','CA','FA','SA','w','z','SB','r','TA'),
    12:('w','FA','r','TB','CB','FB','TA','SB','SA','z','CA','c'),
    13:('SB','z','r','SA','TB','CA','FB','CB','c','TA','w','FA'),
}
FIXED_ROUNDS = {0:(4,),1:(4,),2:(5,),6:(3,12),7:(4,13),8:(3,14),12:(3,9,22),13:(3,18)}
FIXED_WORK = {
    0:(20,'此前一组已登记入库，本组标识刚读完、正文尚未写。'),
    1:(20,'此前一组已登记入库，本组标识刚读完、正文尚未写。'),
    2:(21,'本组正文已写完，等待登记提交。'),
    6:(24,'上组提交完、本组未读标识、登记序列准备继续。'),
    7:(25,'当前正文已写完，只余提交；两个预约均尚未到开始时刻。'),
    8:(25,'本组标识已读、正文待写，普通登记优先级4。'),
    12:(28,'登记进入新一组、标识未读。'),
    13:(27,'本组正文已写完、提交未执行。'),
}
STEPS = {'r':'read','w':'write','c':'commit'}
WORK = {'r':'读取样品标识','w':'写入样品登记表','c':'提交登记'}
PRESERVATIONS = {'C':('cool','启动冷却'),'S':('shade','关闭避光盖'),
                 'F':('seal_check','复核封口'),'T':('temperature_check','复查保温箱温度')}


def _operation(code):
    if code == 'z':
        return {'kind':'wait'}
    if code in STEPS:
        return {'kind':'registration','step':STEPS[code]}
    return {'kind':'preservation','sample':code[1],'operation':PRESERVATIONS[code[0]][0]}


def _description(code):
    if code == 'z':
        return '等候。'
    if code in WORK:
        return WORK[code]+'。'
    return f'对样品{code[1]}{PRESERVATIONS[code[0]][1]}。'


def build(index):
    now,next_step,config,correct = CONFIGS[index]
    now = clock(now)
    retained = index in FIXED_MENUS
    history = ArchiveHistory(now,spacing_s=120)
    history.add(1,'当前Q22，样品均已取得、设备正常，所有接口都可受理；保全动作均是明确授权预约，不需诊断好坏或按材料常识改方案。'
                '预约含起点不含终点，不得提前，不跨周期重复，每项只履行一次，完成或取消后不再执行。'
                '当前可执行、未完成未取消的预约中先做等级数最小者，等级0最高、普通登记4，当前可执行预约等级不同。'
                '没有当前预约则继续普通登记，按读取标识、写正文、提交循环；不是有未知过期补救方案的许可任务。'
                '普通作业后至当前为被动交接期，无新增主动普通操作；只有明记的预约实际履约构成例外控制机会。'
                '重复保全仍可物理执行，但不会再次履行同一预约，完整菜单不按到时、完成或取消状态隐藏。'
                '有效/无效提交总计3次，首个有效选择后结束，end为放弃，推理和记忆检索不推进故事时钟。',
                event='preservation_protocol',cycle='Q22',ordinary_priority=4)
    appointments,completed,cancelled = [],[],[]
    acquisitions = {}
    for position,(code,start,end,priority,cycle,status,relative) in enumerate(config):
        identifier = f'A{position+1}'
        operation = _operation(code)
        appointment = {'id':identifier,'cycle':cycle,'operation':operation,'start_s':clock(start),'end_s':clock(end),'priority':priority}
        appointments.append(appointment)
        at = FIXED_ROUNDS[index][position] if retained else (4,12,20)[position]
        common = {'id':identifier,'cycle':cycle,'operation':operation,'priority':priority}
        if relative is None:
            history.add(at,f'{cycle}预约{identifier}：对样品{code[1]}{PRESERVATIONS[code[0]][1]}，'
                        f'从{story_timestamp(clock(start))}至{story_timestamp(clock(end))}，起点含、终点不含，优先级{priority}，一次性履行。',
                        event='absolute_appointment',**common,start_s=clock(start),end_s=clock(end))
        else:
            acquired,delay,width = relative
            acquired = clock(acquired)
            acquisitions[code[1]] = acquired
            history.add(at,f'{cycle}预约{identifier}：样品{code[1]}实际取得于{story_timestamp(acquired)}，等待{delay}分钟后'
                        f'{PRESERVATIONS[code[0]][1]}，应做窗口宽{width}分钟，含起点不含终点，优先级{priority}，一次性履行。',
                        event='relative_appointment',**common,acquired_s=acquired,delay_minutes=delay,width_minutes=width)
        if status == 'X':
            cancelled.append(identifier)
            history.add(16,f'地面批准取消{cycle}预约{identifier}、未执行、以后不再启动。',
                        event='appointment_cancelled',cycle=cycle,id=identifier)
        elif status == 'D':
            completed.append(identifier)
            history.add(30,f'{story_timestamp(clock(start))}，先按优先级执行并完成{cycle}预约{identifier}，回执归档，不重复；此后被动同步至当前。',
                        occurred=clock(start),event='appointment_completed',cycle=cycle,id=identifier,operation=operation)
    if retained:
        at,text = FIXED_WORK[index]
        history.add(at,text,event='registration_work',cycle='Q22',next_work_step=STEPS[next_step])
    else:
        history.add(2,'普通登记任务优先级4。',event='ordinary_priority',priority=4)
        for sample,acquired in acquisitions.items():
            history.add(3,f'{story_timestamp(acquired)}，Q22样品{sample}实际取得。',occurred=acquired,
                        event='sample_acquired',cycle='Q22',sample=sample,acquired_s=acquired)
        history.add(24,'前一组样品登记已提交。',event='previous_group_submitted',cycle='Q22')
        if next_step == 'r':
            history.add(27,'前组提交后的自动新组界面切换开始，无新的主动登记操作。',event='group_switch_started',cycle='Q22')
            history.add(30,'自动切组完成，本组标识未读；继续被动界面同步，到当前才交回主体控制。',
                        event='group_switch_completed',cycle='Q22',next_work_step='read')
        else:
            previous = 'read' if next_step == 'w' else 'write'
            history.add(27,'开始本组'+('读取标识' if previous == 'read' else '写正文')+'，完整操作30秒，之后进入被动交接。',
                        event='registration_started',cycle='Q22',step=previous)
            history.add(30,'收到本组'+('标识读取' if previous == 'read' else '正文写入')+'完成回执；继续被动界面同步，到当前才交回控制。',
                        occurred=now-8*60+30,event='registration_completed',cycle='Q22',step=previous,next_work_step=STEPS[next_step])
    entries = {code:{'operation':_operation(code),'description':_description(code)}
               for code in ('CA','CB','SA','SB','FA','FB','TA','TB','r','w','c','z')}
    group = f'FM-T2-P2-fixed-{index+1:02d}' if retained else f'FM-T2-P2-{now}-{next_step}'
    actions = fixed_options([entries[code] for code in FIXED_MENUS[index]]) if retained else ordered_options(entries.values(),group)
    task = task_shell('FM-T2-P2',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q22','current_work':WORK[next_step],'next_work_step':STEPS[next_step],
                   'max_steps':3,'state_fields':[],
                   'instruction':'请执行下一步操作。' if retained else
                                 f'{story_timestamp(now)}，周期Q22；当前处理本组样品登记；'+
                                 {'r':'本组标识未读','w':'本组标识已读、正文未写','c':'本组正文已写、未提交'}[next_step]+'；请执行下一步操作。',
                   'actions':actions}
    samples = {s:{'cooling':False,'shade_closed':False,'seal_checks':0,'temperature_checks':0} for s in 'AB'}
    for appointment in appointments:
        if appointment['cycle'] == 'Q22' and appointment['id'] in completed:
            _apply_preservation(samples,appointment['operation'])
    task.initial = {'time_s':now,'samples':samples,'registration':{'identifier_read':next_step != 'r','body_written':next_step == 'c','submission':None},
                    'operations':[]}
    task.world = {'appointments':appointments,'completed':completed,'cancelled':cancelled,'acquired_s':acquisitions,
                  'simulate_registration_duration':not retained,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for lowest-priority-number currently due unfinished uncancelled Q22 appointment, otherwise next registration step'}
    return history.finish(task)


def _apply_preservation(samples,operation):
    sample = samples[operation['sample']]
    kind = operation['operation']
    if kind == 'cool':
        sample['cooling'] = True
    elif kind == 'shade':
        sample['shade_closed'] = True
    elif kind == 'seal_check':
        sample['seal_checks'] += 1
    else:
        sample['temperature_checks'] += 1


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['operations'].append({**operation,'started_s':self.state['time_s']})
        if operation['kind'] == 'preservation':
            _apply_preservation(self.state['samples'],operation)
        elif operation['kind'] == 'registration':
            step = operation['step']
            if step == 'read':
                self.state['registration']['identifier_read'] = True
            elif step == 'write':
                self.state['registration']['body_written'] = True
            else:
                r = self.state['registration']
                r['submission'] = {'identifier_present':r['identifier_read'],'body_present':r['body_written']}
            if self.task.world['simulate_registration_duration']:
                self.state['time_s'] += 30
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    appointments = {}
    completed,cancelled = set(),set()
    acquired = {}
    operations = {label:operation for operation,label in PRESERVATIONS.values()}
    labels = '|'.join(operations)
    scope = re.escape(current['cycle'])
    for text in paragraphs(history):
        absolute = re.fullmatch(rf'(Q\d+)预约(A\d+)：对样品([AB])({labels})，从({STORY_STAMP})至({STORY_STAMP})，起点含、终点不含，优先级(\d+)，一次性履行。',text)
        relative = re.fullmatch(rf'(Q\d+)预约(A\d+)：样品([AB])实际取得于({STORY_STAMP})，等待(\d+)分钟后({labels})，应做窗口宽(\d+)分钟，含起点不含终点，优先级(\d+)，一次性履行。',text)
        if absolute or relative:
            if absolute:
                cycle,identifier,sample,label,start,end,priority = absolute.groups()
                start,end = seconds(start),seconds(end)
            else:
                cycle,identifier,sample,acquired_at,delay,label,width,priority = relative.groups()
                start = seconds(acquired_at)+60*int(delay)
                end = start+60*int(width)
            appointments[(cycle,identifier)] = {'id':identifier,'cycle':cycle,'priority':int(priority),
                'operation':{'kind':'preservation','sample':sample,'operation':operations[label]},'start_s':start,'end_s':end}
        fulfilled = re.fullmatch(rf'{STORY_STAMP}，先按优先级执行并完成{scope}预约(A\d+)，回执归档，不重复；此后被动同步至当前。',text)
        cancelled_row = re.fullmatch(rf'地面批准取消{scope}预约(A\d+)、未执行、以后不再启动。',text)
        acquisition = re.fullmatch(rf'({STORY_STAMP})，{scope}样品([AB])实际取得。',text)
        if fulfilled:
            completed.add(fulfilled[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
        if acquisition:
            acquired[acquisition[2]] = seconds(acquisition[1])
    ordered = sorted(appointments.values(),key=lambda row:row['id'])
    due = [r for r in ordered if r['cycle'] == current['cycle'] and r['id'] not in completed|cancelled
           and r['start_s'] <= current['time_s'] < r['end_s']]
    first = min(due,key=lambda row:row['priority']) if due else None
    operation = first['operation'] if first else {'kind':'registration','step':current['next_work_step']}
    return {'appointments':ordered,'completed':sorted(completed),'cancelled':sorted(cancelled),'acquired_s':acquired,'correct_operation':operation}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('appointments','completed','cancelled','acquired_s','correct_operation')):
        raise ValueError('Preservation decision differs from original appointments, actual fulfillment and current work')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
