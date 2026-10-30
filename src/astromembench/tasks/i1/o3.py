"""FM-I1-O3: recover supply-line connections from thirty native receipt rounds."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import decision_cases, decision_command
from ..prose import paragraphs
from ...environment import SingleChoiceRuntime

MINUTES = (1,3,5,7,8,10,12,14,16,18,20,22,24,26,28,29,30,31,32,33,34,35,36,37,38,40,42,44,47,50)
# Paired histories have the same current request and the original neutral menu.
PAIRS = (
    ('A','H1',(1,2,3,4,5),'M09-easy-01'),
    ('B','H1',(4,5,1,2,3),'M09-easy-04'),
    ('B','H2',(1,3,2,5,4),'M09-easy-06'),
    ('A','H2',(2,4,3,1,5),'M09-medium-01'),
    ('A','H1',(4,1,5,3,2),'M09-medium-03'),
    ('B','H2',(5,2,1,4,3),'M09-medium-04'),
    ('A','H2',(5,3,1,2,4),'M09-hard-03'),
    ('B','H1',(1,5,2,3,4),'M09-hard-04'),
)


def transition(connections,line,port,connected):
    if connected:
        if connections[line] is not None or port in connections.values():
            raise ValueError('A successful connection requires a free line and port')
        connections[line] = port
    else:
        if connections[line] != port:
            raise ValueError('A successful disconnection must remove that existing connection')
        connections[line] = None


def required_operation(connections,line):
    if connections[line] is None:
        return {'action':'stow','line':line}
    return {'action':'disconnect','line':line,'port':connections[line]}


def build(index):
    chain,target,numbers,menu_identity = PAIRS[index//2]
    other = 'H2' if target == 'H1' else 'H1'
    ports = dict(zip('pqurv',(f'P{n:02d}' for n in numbers),strict=True))
    first = index%2 == 0
    if index < 6:
        if chain == 'A':
            events = [(5,'Dp'),(7,'Cq' if first else 'P:Cq'),(10,'P:Cv'),(27,'P:Cv')]
        else:
            events = [(5,'Dp'),(7,'Cq'),(10,'P:Cp'),(16,'Dq' if first else 'P:Dq'),
                      (20,'Cp' if first else 'P:Cp'),(27,'A:Cp')]
        other_events = [(12,'Dr'),(14,'Cu'),(19,'Du'),(23,'Cp' if chain == 'A' else 'Cv')]
    else:
        events = [(5,'Dp'),(7,'Cu')]
        if index >= 12:
            events.append((9,'F:Du'))
        events.append((10,'Du'))
        if chain == 'A':
            if index >= 12:
                events += [(12,'F:Cq'),(15,'Cq' if first else 'F:Cq')]
            else:
                events.append((12,'Cq' if first else 'P:Cq'))
            events += [(21,'P:Cu'),(27,'P:Cu')]
        else:
            events += [(12,'Cq'),(21,'P:Cp')]
            if index >= 12:
                events += [(23,'F:Dq'),(25,'Dq' if first else 'F:Dq')]
            else:
                events.append((25,'Dq' if first else 'P:Dq'))
            events.append((27,'Cp' if first else 'P:Cp'))
        other_events = [(6,'Dr'),(8,'Cv'),(14,'Dv'),(17,'Cp' if chain == 'A' else 'Cr')]
    history = History(times=[clock(f'08:{minute:02d}:59') for minute in MINUTES])
    history.add(1,'补给管路H1/H2固定端不变，各自另一端最多接P01—P05中的一个接口，每口最多接一条管路。'
        '成功断开后该管悬空；成功连接要求管路悬空、接口空闲。失败按明确回执保留状态，本次所有失败均未产生连接变化。'
        '待执行计划及计划归档不是物理操作。收回指定管路的下一步：仍连接则断开其实际接口，悬空则直接收纳；另一管继续保留。'
        '停泵、隔离、泄压均已满足，不评价低层机械操控。所有12项动作完整展示，不按当前状态过滤。'
        '提交select和字符串option或end；最多3次总提交，格式错误也占额度，首个有效选择即终止，不能重选。'
        '额外字段、数值型与范围外编号无效。此次仅记录结构化操作请求，不返回操作后连接真值。',event='supply_line_protocol')
    connections = {target:ports['p'],other:ports['r']}
    history.add(2,f'初始{target}连接{ports["p"]}，{other}连接{ports["r"]}，其余接口空闲。',
                event='supply_initial',connections=connections)
    for at,line,code in sorted([(at,target,code) for at,code in events]+[(at,other,code) for at,code in other_events]):
        status,operation = code.split(':',1) if ':' in code else ('success',code)
        port,connected = ports[operation[1]],operation[0] == 'C'
        action,verb = ('connect','连接') if connected else ('disconnect','断开')
        if status == 'A':
            history.add(at,f'归档记录：曾提出{line}返回{port}的计划；本条归档未开展任何物理操作。',
                event='supply_plan_archive',line=line,port=port,physical_operation=False)
        elif status == 'P':
            history.add(at,f'提出{verb}{line}与{port}的计划，尚未开展该项物理操作，现有连接保持不变。',
                event='supply_plan',planned_operation={'action':action,'line':line,'port':port},executed=False)
        else:
            success = status != 'F'
            if success:
                transition(connections,line,port,connected)
            consequence = f'{line}当前连接{connections[line]}' if connections[line] is not None else f'{line}当前未接任何接口'
            history.add(at,f'执行{verb}{line}与{port}；回执{"成功" if success else "失败"}；{consequence}。',
                event='supply_connection',line=line,port=port,connected=connected,success=success,connection_after=connections[line])
    history.add(30,'补给管路收回准备完成：停泵、隔离和泄压均已完成。',event='supply_recovery_ready')
    entries = []
    for line in ('H1','H2'):
        entries += [{'description':f'断开{line}与P{n:02d}的连接','operation':{'action':'disconnect','line':line,'port':f'P{n:02d}'}} for n in range(1,6)]
        entries.append({'description':f'收纳{line}','operation':{'action':'stow','line':line}})
    group = f'FM-I1-O3-pair-{index//2+1:02d}'
    task = task_shell('FM-I1-O3',index,group=group,current_input_group=group,background_group=group)
    task.public = {'instruction':f'请开始收回补给管路{target}，提交下一项操作。停泵、隔离和泄压均已完成。',
        'target_line':target,'time_s':clock('09:00'),'max_steps':3,'actions':ordered_options(entries,menu_identity)}
    task.initial = {}
    task.world = {'correct_operation':required_operation(connections,target),'connections':connections}
    task.rubric = {'correct':100,'incorrect':0}
    return history.finish(task)


class Runtime(SingleChoiceRuntime):
    def submit(self,action):
        super().submit(action)
        if self.done:
            self.feedback = '本次操作请求已记录。'


def reconstruct(history,current):
    connections = {}
    for text in paragraphs(history):
        match = re.fullmatch(r'初始(H[12])连接(P0[1-5])，(H[12])连接(P0[1-5])，其余接口空闲。',text)
        if match:
            first,a,second,b = match.groups()
            if first == second or a == b:
                raise ValueError('Initial supply lines must occupy two distinct ports')
            connections = {first:a,second:b}
            continue
        match = re.fullmatch(r'执行(连接|断开)(H[12])与(P0[1-5])；回执(成功|失败)；'
            r'(H[12])当前(?:连接(P0[1-5])|未接任何接口)。',text)
        if match:
            verb,line,port,outcome,reported_line,after = match.groups()
            if outcome == '成功':
                transition(connections,line,port,verb == '连接')
            if line != reported_line or connections[line] != after:
                raise ValueError('Supply receipt must state the actual unchanged or successfully changed connection')
    if set(connections) != {'H1','H2'}:
        raise ValueError('Both supply lines must be initialized in the received history')
    return {'connections':connections}


def next_action(facts,current):
    return decision_command(current,required_operation(facts['connections'],current['target_line']))


def check_world(task,facts):
    if facts['connections'] != task.world['connections'] or required_operation(facts['connections'],task.public['target_line']) != task.world['correct_operation']:
        raise ValueError('Private current connection and scoring operation must follow the physical history')


def audit_cases(task,facts,solution):
    correct = required_operation(facts['connections'],task.public['target_line'])
    return decision_cases(task,solution,lambda op:100 if op == correct else 0)
