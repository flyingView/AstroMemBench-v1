"""FM-I1-P2: preserve port occupancy and select one next migration operation."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import decision_cases, decision_command
from ..prose import paragraphs
from ...environment import SingleChoiceRuntime

CONVENTION = ('采样工装G为吹扫支路、S为采集支路。把S迁移到指定接口时，先释放被G占据的目标口，再拔除S的旧接口，最后将S接入目标口；目标口空闲则无需动G。'
    '两线路初始均未接入；每条线一次只接一口，每口一次只接一线。实际成功回执才改变连接，失败和计划均不改变。收回仍连接的线会拉伤接口。'
    '当前只提交迁移/撤离流程的下一项物理操作，误拔其他线或无效动作不能完成此步。')
IDENTITIES = ('M09-S2-0','M09-S2-1','M09-S2-2','J11','J23','J31','M09-S2-4','M09-S2-5',
              'J26','J15','J01','J24','M09-S2-6','J19','J28','J10')
TARGETS = ('K2','K2','K1','K3','K2','K3','K1','K2','K1','K3','K2','K1','K3','K2','K3','K2')
# These six histories retain the original prose and record fields verbatim.
PRESERVED = {
    0: ((4,'CG2','吹扫支路G连接K2完成，该口吹扫结束后准备接采集支路。'),
        (16,'N','采集支路S尚在停放位，未连接任何接口。'),
        (26,'N','下一样点要求把S接到K2；吹扫记录已经结束但没有拔除回执。')),
    1: ((4,'CG2','G接入K2并完成吹扫。'),(18,'DG2','G在K2的插头已实际拔除，S仍在停放位。'),
        (26,'N','下一样点需将S接到K2；接口机械条件已满足。')),
    2: ((5,'CS2','S原在K2采集，插接完成。'),(17,'CG3','G接入K3吹扫另一支路，独立于K1。'),
        (26,'N','现在把采集支路S切换到K1，不能带着旧接头直接接新口。')),
    6: ((4,'CS3','S连接K3保留样品接口。'),(12,'CG1','G实际接入K1并完成吹扫。'),
        (20,'N','需把S改到K1。迁移规程先释放目标口，再拔除S旧接口，最后接入。'),
        (27,'P:RG','G回收计划尚未执行，未出现拔除回执。')),
    7: ((3,'CG3','G接入K3完成吹扫连接。'),(11,'F:CS3','S尝试K3被占用拒绝，仍处于未连接状态。'),
        (19,'N','将下一采集目标明确为K2，旧K3尝试不再重试。'),
        (27,'P:CS2','K2接口已准备；S改接方案还未执行。')),
    12: ((3,'CG2','G曾连接K2。'),(8,'DG2','G从K2实际拔除。'),(13,'CG3','G改接K3并吹扫完成。'),
         (18,'CS1','S连接K1，保留上一样点接口。'),
         (23,'F:CS3','S尝试连接K3未成功，原因是仍接着K1且K3被占用，没有发生任何改接。'),
         (28,'N','目标改接仍为S到K3；按先释放目标口的顺序执行。')),
}
# Each new row was reviewed against both line ownership and port exclusion.
EXTENDED = {
    3: ((5,'CS1'),(14,'CG3'),(25,'N','吹扫已经完成，G与S的现有接头均保持连接，没有执行拔除。')),
    4: ((5,'CS1'),(15,'CG3'),(26,'P:CG2')),
    5: ((4,'CS1'),(13,'DS1'),(20,'CG2'),(26,'N','其他样点的吹扫工艺阶段已经结束，G接头尚未拔除。')),
    8: ((4,'CG1'),(9,'CS3'),(15,'DG1'),(21,'CG2'),(27,'P:CG1')),
    9: ((3,'CS1'),(9,'CG2'),(14,'DS1'),(19,'F:CS2','K2已被G占用，接入被拒绝'),(23,'CS1'),(28,'P:CG3')),
    10: ((4,'CG1'),(9,'CS3'),(14,'DG1'),(18,'CG2'),(23,'DS3'),(27,'P:DG2')),
    11: ((3,'CS2'),(8,'CG3'),(14,'DS2'),(18,'F:CS3','K3已被G占用，接入被拒绝'),(24,'P:CG1')),
    13: ((3,'CG2'),(7,'CS1'),(12,'F:DG2','卡扣未松开，拔除没有发生'),(17,'DG2'),(22,'DS1'),(26,'P:CG2')),
    14: ((3,'CG1'),(8,'CS2'),(12,'DG1'),(17,'F:CG3','接头未锁合，未建立连接'),(21,'CG1'),
         (25,'F:DS2','锁扣未松开，拔除没有发生'),(28,'P:CG3')),
    15: ((4,'CS3'),(9,'CG1'),(14,'F:DS3','锁扣未松开，拔除没有发生'),(18,'DS3'),
         (23,'F:CS2','接头未锁合，未建立连接'),(27,'P:CS1')),
}


def required_operation(connections,target):
    if connections['G'] == target:
        return {'action':'disconnect','line':'G','port':target}
    if connections['S'] is not None:
        return {'action':'disconnect','line':'S','port':connections['S']}
    return {'action':'connect','line':'S','port':target}


def transition(connections,line,port,connected):
    if connected:
        if connections[line] is not None or port in connections.values():
            raise ValueError('Successful connection needs a free line and a free port')
        connections[line] = port
    else:
        if connections[line] != port:
            raise ValueError('Successful disconnection needs that actual line-port connection')
        connections[line] = None


def build(index):
    preserved = index in PRESERVED
    target = TARGETS[index]
    history = History(times=[clock('09:00')+120*r+(0 if preserved else 59) for r in range(30)])
    history.add(1,CONVENTION,record_id='H01',event='convention')
    connections = {'G':None,'S':None}
    rows = PRESERVED[index] if preserved else EXTENDED[index]
    for ordinal,row in enumerate(rows,2):
        at,code,*prose = row
        fields = {}
        if code == 'N':
            fields['event'] = 'note'
            text = prose[0]
        else:
            status,operation = code.split(':',1) if ':' in code else ('success',code)
            line,port = operation[1],('K'+operation[2] if len(operation) == 3 else None)
            verb = {'C':'接入','D':'拔除','R':'收回'}[operation[0]]
            if status == 'P':
                fields = {'event':'connection_plan','line':line,'port':port}
                text = prose[0] if preserved else f'提出{verb}{line}在{port}接头的计划，尚未执行，两线连接不变。'
                if not preserved:
                    fields.update(planned_action={'C':'connect','D':'disconnect'}[operation[0]],executed=False)
            else:
                connected,success = operation[0] == 'C',status != 'F'
                fields = {'event':'connection','line':line,'port':port,'connected':connected,'success':success}
                if success:
                    transition(connections,line,port,connected)
                if preserved:
                    text = prose[0]
                elif success:
                    text = f'{line}在{port}的接头{verb}实际成功，'+(f'{line}现在连接{port}。' if connected else f'{line}现在悬空，未连接任何接口。')
                    fields['connection_after'] = connections[line]
                else:
                    outcome = '；'.join(f'{l}仍连接{p}' if p is not None else f'{l}仍悬空、未连接任何接口' for l,p in connections.items())
                    text = f'{line}尝试在{port}{verb}接头失败：{prose[0]}。{outcome}，两线物理连接均没有变化。'
                    fields.update(reason=prose[0],unchanged_connections=deepcopy(connections))
        history.add(at,text,record_id=f'H{ordinal:02d}',**fields)
    if connections['S'] == target:
        raise ValueError('Every authored case requires a pending migration step')
    entries = [{'description':f'{"接入" if action == "connect" else "拔除"}{line}在{port}的接头',
                'operation':{'action':action,'line':line,'port':port}}
               for action in ('connect','disconnect') for line in ('G','S') for port in ('K1','K2','K3')]
    entries += [{'description':f'将未连接的{line}收回卷盘','operation':{'action':'retract','line':line,'port':None}} for line in ('G','S')]
    task = task_shell('FM-I1-P2',index)
    task.public = {'time_s':clock('10:00'),'max_steps':3,'instruction':f'请执行将S迁移到{target}的下一步。',
                   'target':target,'actions':ordered_options(entries,IDENTITIES[index])}
    task.initial = {}
    task.world = {'connections':connections,'correct_operation':required_operation(connections,target)}
    task.rubric = {'score':'100 only for the exact next operation under the public target-port-first migration order'}
    return history.finish(task)


Runtime = SingleChoiceRuntime


def reconstruct(history,current):
    connections = {}
    for text in paragraphs(history):
        if text.startswith('采样工装G为吹扫支路、S为采集支路。') and '两线路初始均未接入；' in text:
            connections = {'G':None,'S':None}
            continue
        match = re.fullmatch(r'([GS])在(K[123])的接头(接入|拔除)实际成功，(.*)。',text)
        if match:
            line,port,verb,outcome = match.groups()
            connected = verb == '接入'
            transition(connections,line,port,connected)
            expected = f'{line}现在连接{port}' if connected else f'{line}现在悬空，未连接任何接口'
            if outcome != expected:
                raise ValueError('Connection receipt disagrees with its actual result')
            continue
        match = re.fullmatch(r'[GS]尝试在K[123](?:接入|拔除)接头失败：[^。]+。(.*)，两线物理连接均没有变化。',text)
        if match:
            unchanged = {}
            for entry in match[1].split('；'):
                result = re.fullmatch(r'([GS])仍(?:连接(K[123])|悬空、未连接任何接口)',entry)
                if result is None or result[1] in unchanged:
                    raise ValueError('Failed operation must preserve both existing connections')
                unchanged[result[1]] = result[2]
            if unchanged != connections:
                raise ValueError('Failed operation must preserve both existing connections')
            continue
        match = re.fullmatch(r'(?:吹扫支路)?([GS])(?:实际接入|接入|连接|曾连接|改接)(K[123])'
            r'(?:完成，该口吹扫结束后准备接采集支路|并完成吹扫|吹扫另一支路，独立于K[123]|'
            r'保留样品接口|完成吹扫连接|并吹扫完成|，保留上一样点接口|)。',text)
        if match:
            transition(connections,match[1],match[2],True)
            continue
        match = re.fullmatch(r'([GS])原在(K[123])采集，插接完成。',text)
        if match:
            transition(connections,match[1],match[2],True)
            continue
        match = re.fullmatch(r'([GS])(?:在|从)(K[123])(?:的插头已实际拔除，([GS])仍在停放位|实际拔除)。',text)
        if match:
            line,port,parked = match.groups()
            transition(connections,line,port,False)
            if parked is not None and connections[parked] is not None:
                raise ValueError('A parked line cannot retain a port connection')
            continue
        match = re.fullmatch(r'([GS])尝试(K[123])被占用拒绝，仍处于未连接状态。',text)
        if match:
            if connections[match[1]] is not None or match[2] not in connections.values():
                raise ValueError('Rejected connection must keep a free line and an occupied port')
            continue
        match = re.fullmatch(r'([GS])尝试连接(K[123])未成功，原因是仍接着(K[123])且(K[123])被占用，没有发生任何改接。',text)
        if match:
            line,port,previous,occupied = match.groups()
            if connections[line] != previous or port != occupied or port not in connections.values():
                raise ValueError('Rejected migration must retain its old line and the occupied target')
    if set(connections) != {'G','S'}:
        raise ValueError('The public convention must identify both initially disconnected lines')
    if connections['S'] == current['target']:
        raise ValueError('This task requires an uncompleted migration')
    return {'connections':connections}


def next_action(facts,current):
    return decision_command(current,required_operation(facts['connections'],current['target']))


def check_world(task,facts):
    if facts['connections'] != task.world['connections'] or required_operation(facts['connections'],task.public['target']) != task.world['correct_operation']:
        raise ValueError('Private migration state must agree with actual public connection receipts')


def audit_cases(task,facts,solution):
    correct = required_operation(facts['connections'],task.public['target'])
    return decision_cases(task,solution,lambda op:100 if op == correct else 0)
