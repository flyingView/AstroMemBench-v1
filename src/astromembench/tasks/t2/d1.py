"""FM-T2-D1: interrupt continuous report work for a due cruise obligation."""
import re

from ..common import History, clock, fixed_options, round_times, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('LA',0,3,'08:12','08:10','08:14','r','LA'),
    ('LA',0,3,'08:12','08:16','08:20','r','r'),
    ('PA',2,5,'10:32','10:30','10:34','c','PA'),
    ('PA',2,5,'10:32','10:37','10:41','c','c'),
    ('HA',1,4,'12:12','12:10','12:15','w','HA'),
    ('HA',1,4,'12:12','12:18','12:23','w','w'),
    ('LA',0,3,'08:42','08:41','08:44','r','LA'),
    ('LA',0,3,'08:42','08:47','08:50','r','r'),
    ('TA',1,4,'12:42','12:40','12:43','w','TA'),
    ('TA',1,4,'12:42','12:46','12:49','w','w'),
    ('TB',2,5,'15:32','15:31','15:35','c','TB'),
    ('TB',2,5,'15:32','15:37','15:41','c','c'),
    ('PB',1,4,'09:50:01','09:50','09:53','w','PB'),
    ('PB',1,4,'09:50:01','09:54','09:57','w','w'),
    ('HB',2,5,'10:50','10:49:30','10:51:30','c','HB'),
    ('HB',2,5,'10:50','10:54','10:56','c','c'),
)
MENUS = (
    ('PB','LB','r','HA','PA','c','TB','HB','w','TA','z','LA'),
    ('HB','LA','w','LB','r','PA','TB','c','TA','HA','PB','z'),
    ('r','LB','w','TB','LA','PB','TA','c','HB','z','PA','HA'),
    ('HA','z','PA','TB','TA','c','w','PB','r','LA','LB','HB'),
    ('TB','c','TA','PA','LB','HB','PB','LA','w','z','r','HA'),
    ('HB','w','PA','TB','TA','r','LB','c','PB','HA','z','LA'),
    ('PA','c','w','HA','PB','TB','r','LB','LA','HB','TA','z'),
    ('z','w','TA','HA','LA','TB','PA','r','LB','PB','c','HB'),
)
KINDS = {'L':'low_power','P':'pause_selftest','H':'health_check','T':'thermal_log'}
STEPS = {'r':'read_summary','w':'write_report','c':'register_report'}
LABELS = {'L':'将巡航监测单元切到低功耗','P':'暂停非关键自检','H':'启动存储区健康检查','T':'开启热控区状态记录',
          'r':'读取R17检查摘要','w':'写入R17报告正文','c':'登记R17报告','z':'等待，不下发操作'}


def _operation(code):
    if code == 'z':
        return {'kind':'wait'}
    if code in STEPS:
        return {'kind':STEPS[code],'report':'R17'}
    return {'kind':KINDS[code[0]],'target':code[1]}


def _description(code):
    return LABELS[code]+'。' if len(code) == 1 else f'{LABELS[code[0]]}，对象{code[1]}。'


def build(index):
    main,p,q,now,start,end,next_step,correct = CONFIGS[index]
    now = clock(now)
    anchors = {1:now-123*60,4:now-120*60,5:now-119*60,8:now-118*60,12:now-116*60,
               16:now-110*60,20:now-90*60,25:now-40*60,28:now-4*60,30:now}
    if index >= 12:
        anchors.update({1:now-86400-300,2:now-86400})
    times = round_times(anchors)
    history = History(times=times)

    def add(at,text,**facts):
        history.add(at,text,occurred=times[at-1],received=times[at-1],**facts)

    add(1,'巡航保障任务，设备全正常、接口已准备。优先级0—5，数字越小越高；只在当前可执行任务中选最高优先级。'
          '预约窗口含开始不含结束，不得提前，只对注明周期有效，需要主体主动执行。'
          '连续报告按读取摘要、写入正文、登记推进，每份报告不重新分配优先级；当前只决定下一步，普通步骤不阻断未来窗口。'
          '监测A/B、自检A/B、存储A/B、热控A/B独立；所有十二选项均可下发，合法错误也实际操作并结束。'
          '有效与无效提交共3次，首有效选择终止，end放弃；检索和推理不推进故事时间。',event='cruise_protocol')
    appointments = []

    def appointment(at,identifier,code,cycle,begin,finish,priority):
        row = {'id':identifier,'cycle':cycle,'operation':_operation(code),'start_s':begin,'end_s':finish,'priority':priority}
        appointments.append(row)
        add(at,f'{cycle}预约{identifier}：{_description(code)} 窗口{story_timestamp(begin)}至{story_timestamp(finish)}，起点含终点不含，优先级{priority}。',
            event='appointment_registered',**row)

    appointment(4,'A1',main,'Q08',clock(start),clock(end),p)
    add(5,'已收到上述任务安排，接受不是已经执行。',event='arrangement_accepted',cycle='Q08')
    other = 'B' if main[1] == 'A' else 'A'
    category = 'LPHT'.index(main[0])
    if index >= 6:
        offsets = (0,1) if index >= 12 else (1,2)
        for position,offset in enumerate(offsets):
            code = 'LPHT'[(category+offset)%4]+other
            minute = (48,78)[position]
            appointment((8,12)[position],f'A{position+2}',code,'Q08',now+minute*60,now+(minute+4)*60,(p+position+1)%3)
    if index >= 12:
        appointment(2,'OLD',main[0]+other,'Q07',now-86400-120,now-86400+120,p)
    add(16,f'Q08连续报告整理优先级{q}，每份按读取摘要→写入正文→登记推进。',event='report_priority',cycle='Q08',priority=q)
    add(20,'R15报告登记完成，继续后续报告。',event='report_registered',cycle='Q08',report='R15')
    add(25,'R16报告登记完成，继续R17。',event='report_registered',cycle='Q08',report='R16')
    previous = {'r':'cache_sync','w':'read_summary','c':'write_report'}[next_step]
    add(28,'开始R17'+{'r':'缓存同步','w':'读取摘要','c':'写入正文'}[next_step]+'；此前一步完成前没有新主动决策。',
        event='report_step_started',cycle='Q08',report='R17',step=previous)
    plan = [STEPS[c] for c in {'r':'rwc','w':'wc','c':'c'}[next_step]]
    add(30,'R17此前一步完成，继续正常报告流程。',event='report_step_completed',cycle='Q08',report='R17',step=previous,next_plan=plan)
    group = f'FM-T2-D1-pair{index//2+1:02d}'
    task = task_shell('FM-T2-D1',index,group=group,background_group=group,current_input_group=group)
    devices = {'monitor':{s:'normal' for s in 'AB'},'selftest':{s:'running' for s in 'AB'},
               'health_check':{s:False for s in 'AB'},'thermal_log':{s:False for s in 'AB'}}
    task.public = {'time_s':now,'cycle':'Q08','current_work':'整理R17','next_work_step':STEPS[next_step],'next_plan':plan,
                   'device_status':devices,'max_steps':3,'state_fields':[],
                   'instruction':f'{story_timestamp(now)}，周期Q08，当前作业整理R17；'+
                   {'r':'摘要未读，后续计划读取→写入→登记','w':'摘要已读正文未写，后续计划写入→登记','c':'正文已写尚未登记，后续计划登记'}[next_step]
                   +'；请执行下一步操作。',
                   'actions':fixed_options([{'operation':_operation(code),'description':_description(code)} for code in MENUS[index//2]])}
    task.initial = {'time_s':now,'devices':devices,'report':{'summary_read':next_step != 'r','body_written':next_step == 'c','registration':None}}
    task.world = {'appointments':sorted(appointments,key=lambda row:row['id']),'report_priority':q,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for the highest-priority currently executable Q08 task, including the ordinary report step'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        kind = operation['kind']
        if kind == 'low_power':
            self.state['devices']['monitor'][operation['target']] = 'low_power'
        elif kind == 'pause_selftest':
            self.state['devices']['selftest'][operation['target']] = 'paused'
        elif kind in ('health_check','thermal_log'):
            self.state['devices'][kind][operation['target']] = True
        elif kind == 'read_summary':
            self.state['report']['summary_read'] = True
        elif kind == 'write_report':
            self.state['report']['body_written'] = True
        elif kind == 'register_report':
            r = self.state['report']
            r['registration'] = {'summary_present':r['summary_read'],'body_present':r['body_written']}
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    appointments,priority = {},None
    kinds = {LABELS[code]:kind for code,kind in KINDS.items()}
    labels = '|'.join(kinds)
    for text in paragraphs(history):
        appointment = re.fullmatch(rf'(Q\d+)预约(A\d+|OLD)：({labels})，对象([AB])。 窗口({STORY_STAMP})至({STORY_STAMP})，起点含终点不含，优先级(\d+)。',text)
        if appointment:
            cycle,identifier,label,target,start,end,rank = appointment.groups()
            appointments[identifier] = {'id':identifier,'cycle':cycle,'operation':{'kind':kinds[label],'target':target},
                'start_s':seconds(start),'end_s':seconds(end),'priority':int(rank)}
        ordinary = re.fullmatch(rf'{re.escape(current["cycle"])}连续报告整理优先级(\d+)，每份按读取摘要→写入正文→登记推进。',text)
        if ordinary:
            priority = int(ordinary[1])
    if priority is None:
        raise ValueError('Missing continuous report priority')
    ordered = sorted(appointments.values(),key=lambda row:row['id'])
    available = [r for r in ordered if r['cycle'] == current['cycle'] and r['start_s'] <= current['time_s'] < r['end_s']]
    available.append({'priority':priority,'operation':{'kind':current['next_work_step'],'report':'R17'}})
    return {'appointments':ordered,'report_priority':priority,'correct_operation':min(available,key=lambda r:r['priority'])['operation']}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('appointments','report_priority','correct_operation')):
        raise ValueError('Cruise decision differs from original appointments and continuous report priority')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
