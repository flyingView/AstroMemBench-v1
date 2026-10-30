"""FM-T2-O3: delayed duties after actual replenishment completion."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

# Action, actual event time, delay/width minutes, priority, FIN/PAUSE, cancellation/fulfillment.
CONFIGS = (
    ('10:00','CIII','FB',(('WA','08:40',80,5,1,'FIN',''),),'WA'),
    ('10:00','CIII','FB',(('WA','08:40',84,5,1,'FIN',''),),'FB'),
    ('10:30','ICII','FC',(('PB','09:00',89,5,0,'FIN',''),),'PB'),
    ('10:30','IPII','FB',(('PB','09:00',89,5,0,'PAUSE',''),),'FB'),
    ('12:30','ICII','FD',(('WB','11:00',89,5,0,'FIN',''),),'WB'),
    ('12:30','IPII','FB',(('WB','11:00',89,5,0,'PAUSE',''),),'FB'),
    ('13:00','CCII','FC',(('WA','11:30',90,5,2,'FIN',''),('PB','11:35',85,5,0,'FIN','')),'PB'),
    ('13:00','CCII','FC',(('WA','11:30',90,5,2,'FIN',''),('PB','11:35',89,5,0,'FIN','')),'WA'),
    ('14:00','CICI','FB',(('PA','12:30',90,4,0,'FIN',''),('WC','12:35',85,5,2,'FIN','')),'PA'),
    ('14:00','CICI','FB',(('PA','12:30',94,4,0,'FIN',''),('WC','12:35',85,5,2,'FIN','')),'WC'),
    ('15:00','CCII','FD',(('PB','13:30',90,5,0,'FIN',''),('WA','13:35',85,5,1,'FIN','')),'PB'),
    ('15:00','PCII','FA',(('PB','13:30',94,5,0,'FIN',''),('WA','13:35',85,5,1,'PAUSE','')),'FA'),
    ('16:00','CCII','FC',(('WA','14:30',90,5,0,'FIN','X'),('PB','14:35',85,5,1,'FIN','')),'PB'),
    ('16:00','CCII','FC',(('WA','14:30',90,5,0,'FIN',''),('PB','14:35',89,5,1,'FIN','')),'WA'),
    ('17:30','ICIP','FD',(('WB','16:00',88,5,0,'FIN','D'),('PD','16:05',85,5,1,'PAUSE','')),'FD'),
    ('17:30','ICIC','FA',(('WB','16:00',88,5,0,'FIN','D'),('PD','16:05',85,5,1,'FIN','')),'PD'),
)
KINDS = {'W':'witness_sample','P':'pressure_reading','F':'inject'}
NAMES = {'W':'抽取1mL见证样','P':'记录一次压力回弹','F':'继续注入固定2L段（30秒）'}


def _operation(code):
    return {'kind':'wait'} if code == 'Z' else {'kind':KINDS[code[0]],'receiver':code[1]}


def _description(code):
    return '等候，不执行操作。' if code == 'Z' else f'对接收器{code[1]}{NAMES[code[0]]}。'


def build(index):
    now,statuses,next_step,config,correct = CONFIGS[index]
    now = clock(now)
    status = dict(zip('ABCD',statuses,strict=True))
    done = any(r[-1] == 'D' for r in config)
    history = ArchiveHistory(now,spacing_s=120)
    history.add(1,'批Q61，当前各接收器供给单B2；义务绑定接收器、本供给单、动作、实际FIN后等待分钟及窗口宽度。'
                '只有实际FIN完成启动计时，PAUSE只是中断，计划完成不计；窗口含起点不含终点，未到不得提前。'
                '等级0最高、普通注入4，当前到时、未完成未取消者按最小等级先执行；每项一次，旧B1已做不抵消B2义务。'
                '无到时义务就继续正常队列。当前状态C为本单已完成，P为暂停准备继续，I为下一段准备中，不表示此前从未输液。'
                '各接收器容量100L，目前本单各已有20L，供给罐可供100L；每个接收器两只1mL空瓶，共8只。'
                '每次留样从对应接收器移1mL到下一空瓶，重复留样也实际转移；读压力不转移物质。'
                '任何注入从供给罐转2L到所选接收器，完整30秒；接口始终受理，错误对象仍真实操作。'
                '所有阀、连接、安全和数量充分，数值为题内简化工艺，数量不决定义务优先级。'
                '供给侧自动准备不向接收器输液且无净损失，期间无主动控制机会；明记完成项后自动复位/界面同步至当前。'
                '有效无效共3次，首有效选择终止，end放弃；推理与检索不推进故事时间。',
                event='replenishment_protocol',cycle='Q61',order='B2',ordinary_priority=4,
                material_baseline={'supply_ml':100000,'receivers_ml':{r:20000 for r in 'ABCD'},'bottles_per_receiver':2,'bottle_capacity_ml':1})
    history.add(2,'正常继续注入等级4。',event='ordinary_priority',priority=4)
    first_op = _operation(config[0][0])
    history.add(3,f'归档：{story_timestamp(now-100*60)}旧B1对接收器{config[0][0][1]}已完成{NAMES[config[0][0][0]]}。'
                '此为旧单，早于本单物料基线，不抵消新B2义务。',occurred=now-100*60,
                event='obligation_completed',cycle='Q61',order='B1',id='I1',operation=first_op)
    appointments,events,completed,cancelled = [],[],[],[]
    for position,(code,at,delay,width,priority,event_type,condition) in enumerate(config):
        identifier = f'I{position+1}'
        op = _operation(code)
        row = {'id':identifier,'cycle':'Q61','order':'B2','operation':op,'delay_minutes':delay,'width_minutes':width,'priority':priority}
        appointments.append(row)
        history.add((4,12,20)[position],f'Q61/B2预约{identifier}：接收器{code[1]}实际FIN后等待{delay}分钟起，'
                    f'在宽{width}分钟窗口内{NAMES[code[0]]}，等级{priority}，只做一次。',event='obligation_registered',**row)
        supply_event = {'receiver':code[1],'event_type':event_type,'occurred_s':clock(at)}
        events.append(supply_event)
        history.add((5,13,21)[position],f'{story_timestamp(clock(at))}，Q61/B2接收器{code[1]}实际'
                    +('FIN完成本单供给。' if event_type == 'FIN' else 'PAUSE中断供给，仍待继续，尚未完成本单。'),
                    occurred=clock(at),event='supply_event',cycle='Q61',order='B2',receiver=code[1],event_type=event_type)
        if condition == 'X':
            cancelled.append(identifier)
            history.add(16,f'取消Q61/B2预约{identifier}，未履行。',event='obligation_cancelled',cycle='Q61',order='B2',id=identifier)
        elif condition == 'D':
            completed.append(identifier)
    history.add(24,f'正常队列下一段给接收器{next_step[1]}。',event='ordinary_queue',receiver=next_step[1])
    history.add(27,'供给侧泵路完整自动准备开始，内循环不向接收器输液、无净损失，结束前没有主体控制机会。',
                event='preparation_started',expected_end_s=now-120 if done else now)
    if done:
        history.add(30,'供给侧自动准备结束，归还一次控制；没有向接收器注入。',event='preparation_completed')
        for row in appointments:
            if row['id'] in completed:
                history.add(30,f'{story_timestamp(now-120)}优先执行当前最高Q61/B2预约{row["id"]}并完成，随后自动采样器复位/界面同步至当前。',
                            event='obligation_completed',cycle='Q61',order='B2',id=row['id'],operation=row['operation'])
        history.add(30,'仍在被动复位/界面同步，当前前没有另一主动控制机会。',event='reset_telemetry')
    else:
        history.add(30,'供给侧自动准备仍在进行，无接收器输液、无净损失。',event='preparation_telemetry')
    group = f'FM-T2-O3-{now}-{statuses}-{next_step}'
    entries = [{'operation':_operation(code),'description':_description(code)}
               for code in ('WA','WB','WC','WD','PA','PB','PC','PD','FA','FB','FC','FD','Z')]
    task = task_shell('FM-T2-O3',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q61','order':'B2','receiver_status':status,'ordinary_next':next_step[1],
                   'max_steps':3,'state_fields':[],'instruction':f'{story_timestamp(now)}，Q61/B2，A/B/C/D原始状态{statuses}，'
                   f'正常队列下一项给{next_step[1]}注入，自动流程已归还控制；请执行下一步操作。',
                   'actions':ordered_options(entries,group)}
    receivers = {r:20000 for r in 'ABCD'}
    bottles = {r:[0,0] for r in 'ABCD'}
    readings = {r:0 for r in 'ABCD'}
    for row in appointments:
        if row['id'] in completed:
            receiver = row['operation']['receiver']
            if row['operation']['kind'] == 'witness_sample':
                receivers[receiver] -= 1
                bottles[receiver][0] = 1
            else:
                readings[receiver] += 1
    task.initial = {'time_s':now,'supply_ml':100000,'receivers_ml':receivers,'bottles_ml':bottles,'pressure_readings':readings,'injections':[],'samples':[]}
    task.world = {'appointments':appointments,'supply_events':events,'completed':completed,'cancelled':cancelled,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for highest-priority due unfinished B2 duty after actual FIN, otherwise next normal injection'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        kind = operation['kind']
        if kind != 'wait':
            receiver = operation['receiver']
            if kind == 'inject':
                self.state['supply_ml'] -= 2000
                self.state['receivers_ml'][receiver] += 2000
                self.state['injections'].append({'receiver':receiver,'volume_ml':2000,'started_s':self.state['time_s'],'finished_s':self.state['time_s']+30})
                self.state['time_s'] += 30
            elif kind == 'witness_sample':
                bottle = self.state['bottles_ml'][receiver].index(0)
                self.state['receivers_ml'][receiver] -= 1
                self.state['bottles_ml'][receiver][bottle] = 1
                self.state['samples'].append({'receiver':receiver,'bottle':bottle+1,'volume_ml':1})
            else:
                self.state['pressure_readings'][receiver] += 1
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    appointments,events = {},{}
    completed,cancelled = set(),set()
    scope = re.escape(f'{current["cycle"]}/{current["order"]}')
    for text in paragraphs(history):
        registered = re.fullmatch(rf'{scope}预约(I\d+)：接收器([ABCD])实际FIN后等待(\d+)分钟起，在宽(\d+)分钟窗口内(抽取1mL见证样|记录一次压力回弹)，等级(\d+)，只做一次。',text)
        if registered:
            identifier,receiver,delay,width,operation,priority = registered.groups()
            appointments[identifier] = {'id':identifier,'cycle':current['cycle'],'order':current['order'],
                'operation':{'kind':'witness_sample' if operation == '抽取1mL见证样' else 'pressure_reading','receiver':receiver},
                'delay_minutes':int(delay),'width_minutes':int(width),'priority':int(priority)}
        supply = re.fullmatch(rf'({STORY_STAMP})，{scope}接收器([ABCD])实际(FIN完成本单供给|PAUSE中断供给，仍待继续，尚未完成本单)。',text)
        fulfilled = re.fullmatch(rf'{STORY_STAMP}优先执行当前最高{scope}预约(I\d+)并完成，随后自动采样器复位/界面同步至当前。',text)
        cancelled_row = re.fullmatch(rf'取消{scope}预约(I\d+)，未履行。',text)
        if supply:
            events[supply[2]] = {'receiver':supply[2],'event_type':'FIN' if supply[3].startswith('FIN') else 'PAUSE','occurred_s':seconds(supply[1])}
        if fulfilled:
            completed.add(fulfilled[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
    ordered = sorted(appointments.values(),key=lambda r:r['id'])
    due = []
    for row in ordered:
        event = events[row['operation']['receiver']]
        expected = 'C' if event['event_type'] == 'FIN' else 'P'
        if current['receiver_status'][event['receiver']] != expected:
            raise ValueError('Raw receiver status contradicts actual FIN/PAUSE history')
        start = event['occurred_s']+row['delay_minutes']*60
        if event['event_type'] == 'FIN' and row['id'] not in completed|cancelled and start <= current['time_s'] < start+row['width_minutes']*60:
            due.append(row)
    first = min(due,key=lambda r:r['priority']) if due else None
    op = first['operation'] if first else {'kind':'inject','receiver':current['ordinary_next']}
    return {'appointments':ordered,'supply_events':[events[r['operation']['receiver']] for r in ordered],
            'completed':sorted(completed),'cancelled':sorted(cancelled),'correct_operation':op}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('appointments','supply_events','completed','cancelled','correct_operation')):
        raise ValueError('Supply duty differs from actual order completion, delay and fulfillment')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
