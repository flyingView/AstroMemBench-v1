"""FM-T2-O2: reinspection windows anchored to actual construction instances."""
import re

from ..common import ArchiveHistory, clock, fixed_options, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

# Appointment: action, start, end, priority, cycle, state, (plan, actual, delay, width, prior J1 check).
CONFIGS = (
    ('10:27','w',(('HB','10:25','10:30',1,'Q22','',None),),'HB'),
    ('10:27','w',(('HB','10:31','10:36',1,'Q22','',None),),'w'),
    ('11:16','r',(('IA','11:15','11:19',0,'Q22','',None),),'IA'),
    ('09:20','c',(('QB','09:20','09:25',1,'Q22','',('07:45','07:50',90,5,False)),),'QB'),
    ('09:20','c',(('QB','09:24','09:29',1,'Q22','',('07:50','07:54',90,5,False)),),'c'),
    ('11:40','r',(('HA','11:44','11:48',0,'Q22','',('10:00','10:04',100,4,False)),),'r'),
    ('12:38','c',(('QB','12:36','12:42',1,'Q22','',None),('HA','12:45','12:51',0,'Q22','',None)),'QB'),
    ('13:14','w',(('LA','13:18','13:24',1,'Q22','',None),('IB','13:22','13:28',0,'Q22','',None)),'w'),
    ('14:31','r',(('HA','14:30','14:36',3,'Q22','',None),('LB','14:29','14:34',1,'Q22','',None)),'LB'),
    ('09:40','r',(('IA','09:39','09:44',2,'Q22','',('07:50','07:59',100,5,False)),('HB','09:40','09:46',0,'Q22','',('07:55','08:00',100,6,False))),'HB'),
    ('09:40','r',(('IA','09:39','09:44',2,'Q22','',('07:50','07:59',100,5,False)),('HB','09:44','09:50',0,'Q22','',('08:00','08:04',100,6,False))),'IA'),
    ('12:00','c',(('HA','12:04','12:09',0,'Q22','',('10:20','10:24',100,5,False)),('IB','12:00','12:05',2,'Q22','',('10:15','10:20',100,5,False))),'IB'),
    ('15:42','c',(('QA','15:40','15:47',0,'Q21','',None),('LA','15:41','15:46',0,'Q22','X',None),('IB','15:42','15:46',1,'Q22','',None)),'IB'),
    ('16:08','w',(('HA','16:06','16:11',1,'Q22','D',None),('QB','16:12','16:17',0,'Q22','',None)),'w'),
    ('09:50','r',(('LB','09:50','09:55',1,'Q22','',('08:00','08:10',100,5,True)),('HA','09:54','09:59',0,'Q22','',('08:05','08:14',100,5,False))),'LB'),
    ('13:12','w',(('HB','13:10','13:15',0,'Q22','D',('11:20','11:30',100,5,False)),('LA','13:12','13:18',1,'Q22','',('11:20','11:32',100,6,True))),'LA'),
)
FIXED_MENUS = {
    0:('QA','LB','IA','HB','LA','w','r','QB','c','z','HA','IB'),
    1:('QB','z','IA','IB','LA','r','LB','HA','QA','c','HB','w'),
    2:('c','z','w','QB','IA','QA','HB','IB','HA','LA','r','LB'),
    6:('IB','r','c','IA','HB','QB','QA','z','LB','LA','w','HA'),
    7:('z','HB','IB','LB','LA','w','r','QB','c','QA','IA','HA'),
    8:('LB','IA','z','w','LA','IB','HA','c','QB','HB','r','QA'),
    12:('QB','IB','QA','LA','HB','c','LB','HA','z','IA','r','w'),
    13:('IA','HA','w','z','r','IB','HB','QB','LA','QA','LB','c'),
}
FIXED_ROUNDS = {0:(4,),1:(4,),2:(5,),6:(3,13),7:(4,15),8:(3,14),12:(3,9,22),13:(3,19)}
FIXED_WORK = {
    0:(21,'普通工单故障摘要已读、正文未整理。'),
    1:(21,'普通工单故障摘要已读、正文未整理。'),
    2:(23,'上一工单已归档、新工单摘要未读。'),
    6:(25,'正文已整理、尚未归档提交。'),
    7:(26,'摘要读取结束、准备整理正文。'),
    8:(25,'刚切换下一工单、摘要未读、普通工单等级4。'),
    12:(28,'正文完成、等待归档。'),
    13:(27,'普通摘要已读、正文未整理。'),
}
FIXED_CONSTRUCTION = {(0,0):'B粘接完成，',(1,0):'B粘接完成，',(2,0):'A更换线束结束，',
                      (6,0):'B紧固结束，',(8,1):'B密封件装好，'}
STEPS = {'r':'read','w':'write','c':'commit'}
WORK = {'r':'读取工单摘要','w':'整理工单正文','c':'归档工单'}
INSPECTIONS = {'H':('thermal','热稳定复检'),'I':('insulation','绝缘复测'),
               'Q':('torque','二次扭矩检查'),'L':('leak','泄漏复检')}


def _operation(code):
    if code == 'z':
        return {'kind':'wait'}
    if code in STEPS:
        return {'kind':'work_order','step':STEPS[code]}
    return {'kind':'reinspection','device':code[1],'mode':INSPECTIONS[code[0]][0]}


def _description(code):
    if code == 'z':
        return '等候。'
    if code in WORK:
        return WORK[code]+'。'
    return f'对设备{code[1]}当前施工实例启动{INSPECTIONS[code[0]][1]}。'


def build(index):
    now,next_step,config,correct = CONFIGS[index]
    now = clock(now)
    retained = index in FIXED_MENUS
    history = ArchiveHistory(now,spacing_s=120)
    history.add(1,'当前Q22，复检设备和连接前提满足；以下物性等待时间均为题内简化工艺，不需诊断或另作维修规划。'
                '预约含起点不含终点，不得提前、不跨周期，每项只做一次；完成或取消后不重复。'
                '当前到时、未完成未取消者先做优先级数最小项，0最高，普通工单4，到时预约没有同级。'
                '规定实际施工完成后δ分钟起的w分钟复检，以实际完成回执为锚，计划时刻不产生义务。'
                '每次施工实例独立，新一次重做形成新实例；旧实例已检不能抵消新实例，复检接口操作设备当前施工实例。'
                '无当前到时预约则继续普通摘要读取、正文整理、归档；末次普通工作后为被动交接至当前，'
                '仅明记预约履约有额外授权控制机会，不推断未给出的施工时长。'
                '十二接口始终可受理，提前、重复或错误对象也会实际启动检查，不隐藏按钮，不反馈待办/正确性。'
                '有效无效共3次，首有效选择结束，end放弃；推理与检索不推进故事时间。',
                event='reinspection_protocol',cycle='Q22',ordinary_priority=4)
    appointments,completed,cancelled,constructions,prior_checks = [],[],[],[],[]
    for position,(code,start,end,priority,cycle,status,process) in enumerate(config):
        identifier = f'A{position+1}'
        op = _operation(code)
        instance = 'current' if retained else 'J2'
        row = {'id':identifier,'cycle':cycle,'operation':op,'instance':instance,'start_s':clock(start),'end_s':clock(end),'priority':priority}
        appointments.append(row)
        at = FIXED_ROUNDS[index][position] if retained else (4,12,20)[position]
        if process is None:
            history.add(at,FIXED_CONSTRUCTION.get((index,position),'')+f'发布{cycle}预约{identifier}：设备{code[1]}{INSPECTIONS[code[0]][1]}，'
                        f'{story_timestamp(clock(start))}至{story_timestamp(clock(end))}，含起点不含终点，等级{priority}，一次。',
                        event='absolute_appointment',id=identifier,cycle=cycle,operation=op,start_s=clock(start),end_s=clock(end),priority=priority)
        else:
            planned,actual,delay,width,prior = process
            planned,actual = clock(planned),clock(actual)
            construction = {'device':code[1],'instance':'J2','planned_s':planned,'completed_s':actual}
            constructions.append(construction)
            if prior:
                old_check = {'device':code[1],'instance':'J1','mode':op['mode'],'completed_s':now-130*60}
                prior_checks.append(old_check)
                history.add(3,f'{story_timestamp(now-130*60)}，Q22设备{code[1]}旧施工J1的{INSPECTIONS[code[0]][1]}已完成，归档只针对J1。',
                            occurred=now-130*60,event='prior_instance_checked',cycle='Q22',**old_check)
            history.add(3,f'归档Q22设备{code[1]}施工J2的计划完成时刻{story_timestamp(planned)}；计划不是实际完成。',
                        event='construction_plan',cycle='Q22',device=code[1],instance='J2',planned_s=planned)
            history.add(at,f'Q22预约{identifier}：设备{code[1]}J2实际施工完成后等{delay}分钟起，'
                        f'在宽{width}分钟的窗口启动{INSPECTIONS[code[0]][1]}，含起点不含终点，等级{priority}。',
                        event='relative_appointment',id=identifier,cycle='Q22',operation=op,instance='J2',delay_minutes=delay,width_minutes=width,priority=priority)
            history.add((5,13,21)[position],f'{story_timestamp(actual)}Q22设备{code[1]}施工J2实际完成；当前接口绑定该J2实例。',
                        occurred=actual,event='construction_completed',cycle='Q22',device=code[1],instance='J2',completed_s=actual)
        if status == 'X':
            cancelled.append(identifier)
            history.add(16,f'正式取消{cycle}预约{identifier}，未复检。',event='appointment_cancelled',cycle=cycle,id=identifier)
        elif status == 'D':
            completed.append(identifier)
            history.add(30,f'{story_timestamp(clock(start))}先执行当时最高优先级{cycle}预约{identifier}、复检完成并归档，随后被动同步至当前。',
                        occurred=clock(start),event='appointment_completed',cycle=cycle,id=identifier,operation=op,instance=instance)
    if retained:
        at,text = FIXED_WORK[index]
        history.add(at,text,event='ordinary_work',cycle='Q22',next_work_step=STEPS[next_step])
    else:
        history.add(2,'普通工单优先级4。',event='ordinary_priority',priority=4)
        history.add(24,'上一普通工单已归档，下一单为W17。',event='previous_order_archived',cycle='Q22')
        if next_step == 'r':
            history.add(27,'前单归档后的自动工单界面切换开始，无新增主动归档或读取。',event='order_switch_started',cycle='Q22',order='W17')
            history.add(30,'自动切换到W17完成，摘要未读；被动同步至当前才交回控制。',
                        event='order_switch_completed',cycle='Q22',order='W17',next_work_step='read')
        else:
            previous = 'read' if next_step == 'w' else 'write'
            history.add(27,'开始W17'+('摘要读取' if previous == 'read' else '正文整理')+'，完整30秒后进入被动交接。',
                        event='ordinary_work_started',cycle='Q22',order='W17',step=previous)
            history.add(30,'W17'+('摘要读取' if previous == 'read' else '正文整理')+'完成回执迟收；随后被动同步至当前。',
                        occurred=now-8*60+30,event='ordinary_work_completed',cycle='Q22',order='W17',step=previous,next_work_step=STEPS[next_step])
    entries = {code:{'operation':_operation(code),'description':_description(code)} for code in ('HA','HB','IA','IB','QA','QB','LA','LB','r','w','c','z')}
    group = f'FM-T2-O2-fixed-{index+1:02d}' if retained else f'FM-T2-O2-{now}-{next_step}'
    actions = fixed_options([entries[c] for c in FIXED_MENUS[index]]) if retained else ordered_options(entries.values(),group)
    task = task_shell('FM-T2-O2',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q22','current_work':WORK[next_step],'next_work_step':STEPS[next_step],
                   'max_steps':3,'state_fields':[],'instruction':'请执行下一步操作。' if retained else
                   f'{story_timestamp(now)}，Q22，普通工单W17，'+{'r':'摘要未读','w':'摘要已读、正文未整理','c':'正文已整理、未归档'}[next_step]
                   +'，设备接口可用，请执行下一步操作。','actions':actions}
    checks = [{**r,'source':'prior_instance'} for r in prior_checks]
    for row in appointments:
        if row['cycle'] == 'Q22' and row['id'] in completed:
            checks.append({'device':row['operation']['device'],'instance':row['instance'],'mode':row['operation']['mode'],
                           'completed_s':row['start_s'],'source':'appointment'})
    task.initial = {'time_s':now,'current_instances':{d:'current' if retained else 'J2' for d in 'AB'},'checks':checks,'started_checks':[],
                    'work_order':{'summary_read':next_step != 'r','body_written':next_step == 'c','archived':None}}
    task.world = {'appointments':appointments,'completed':completed,'cancelled':cancelled,'constructions':constructions,'prior_checks':prior_checks,
                  'simulate_work_duration':not retained,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for the highest-priority due unfinished current-instance appointment, otherwise next ordinary work step'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'reinspection':
            self.state['started_checks'].append({'device':operation['device'],'mode':operation['mode'],
                                                'instance':self.state['current_instances'][operation['device']],'started_s':self.state['time_s']})
        elif operation['kind'] == 'work_order':
            work = self.state['work_order']
            if operation['step'] == 'read':
                work['summary_read'] = True
            elif operation['step'] == 'write':
                work['body_written'] = True
            else:
                work['archived'] = {'summary_present':work['summary_read'],'body_present':work['body_written']}
            if self.task.world['simulate_work_duration']:
                self.state['time_s'] += 30
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    raw,constructions,prior_checks = {},{},{}
    completed,cancelled = set(),set()
    modes = {label:mode for mode,label in INSPECTIONS.values()}
    labels = '|'.join(modes)
    scope = re.escape(current['cycle'])
    for text in paragraphs(history):
        absolute = re.search(rf'发布(Q\d+)预约(A\d+)：设备([AB])({labels})，({STORY_STAMP})至({STORY_STAMP})，含起点不含终点，等级(\d+)，一次。$',text)
        relative = re.fullmatch(rf'(Q\d+)预约(A\d+)：设备([AB])(J\d+)实际施工完成后等(\d+)分钟起，在宽(\d+)分钟的窗口启动({labels})，含起点不含终点，等级(\d+)。',text)
        if absolute or relative:
            if absolute:
                cycle,identifier,device,label,start,end,priority = absolute.groups()
                timing = {'instance':'current','start_s':seconds(start),'end_s':seconds(end)}
            else:
                cycle,identifier,device,instance,delay,width,label,priority = relative.groups()
                timing = {'instance':instance,'delay_minutes':int(delay),'width_minutes':int(width)}
            raw[(cycle,identifier)] = {'id':identifier,'cycle':cycle,'priority':int(priority),
                'operation':{'kind':'reinspection','device':device,'mode':modes[label]},**timing}
        fulfilled = re.fullmatch(rf'{STORY_STAMP}先执行当时最高优先级{scope}预约(A\d+)、复检完成并归档，随后被动同步至当前。',text)
        cancelled_row = re.fullmatch(rf'正式取消{scope}预约(A\d+)，未复检。',text)
        planned = re.fullmatch(rf'归档{scope}设备([AB])施工(J\d+)的计划完成时刻({STORY_STAMP})；计划不是实际完成。',text)
        actual = re.fullmatch(rf'({STORY_STAMP}){scope}设备([AB])施工(J\d+)实际完成；当前接口绑定该\3实例。',text)
        prior = re.fullmatch(rf'({STORY_STAMP})，{scope}设备([AB])旧施工(J\d+)的({labels})已完成，归档只针对\3。',text)
        if fulfilled:
            completed.add(fulfilled[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
        if planned or actual:
            device,instance,stamp = planned.groups() if planned else (actual[2],actual[3],actual[1])
            entry = constructions.setdefault((device,instance),{'device':device,'instance':instance})
            entry['planned_s' if planned else 'completed_s'] = seconds(stamp)
        if prior:
            stamp,device,instance,label = prior.groups()
            prior_checks[(device,instance,modes[label])] = {'device':device,'instance':instance,'mode':modes[label],'completed_s':seconds(stamp)}
    ordered = []
    for record in sorted(raw.values(),key=lambda r:r['id']):
        row = {k:record[k] for k in ('id','cycle','operation','priority')}
        if 'delay_minutes' in record:
            row['instance'] = record['instance']
            actual = constructions[(row['operation']['device'],row['instance'])]['completed_s']
            start = actual+60*record['delay_minutes']
            row.update(start_s=start,end_s=start+60*record['width_minutes'])
        else:
            row.update(instance='current',start_s=record['start_s'],end_s=record['end_s'])
        ordered.append(row)
    due = [r for r in ordered if r['cycle'] == current['cycle'] and r['id'] not in completed|cancelled
           and r['start_s'] <= current['time_s'] < r['end_s']]
    first = min(due,key=lambda r:r['priority']) if due else None
    op = first['operation'] if first else {'kind':'work_order','step':current['next_work_step']}
    # Preserve appointment order for the independently specified private construction table.
    construction_rows = [constructions[(r['operation']['device'],r['instance'])] for r in ordered if r['instance'] != 'current']
    return {'appointments':ordered,'completed':sorted(completed),'cancelled':sorted(cancelled),'constructions':construction_rows,
            'prior_checks':list(prior_checks.values()),'correct_operation':op}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('appointments','completed','cancelled','constructions','prior_checks','correct_operation')):
        raise ValueError('Reinspection decision differs from actual construction instance and public commitments')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
