"""FM-C2-P2: scoped full quotas and relative planned sample transfers."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

CONFIGS = (
    (((4,'F4(2,4,6)'),(16,'F6(6,4,2)')),'F5(4,6,2)',(6,4,2)),
    (((4,'F4(2,4,6)'),(16,'F6(4,2,6)')),'F5(4,6,2)',(4,2,6)),
    (((5,'F3(6,2,4)'),(18,'X7')),'F6(4,6,2)',None),
    (((4,'F2(4,4,4)'),(15,'X5')),'F6(8,2,2)',(8,2,2)),
    (((4,'F2(6,6,0)'),(17,'X6')),'F7(10,0,2)',(10,0,2)),
    (((5,'F3(2,2,8)'),(18,'F7(0,2,10)')),'F6(4,4,4)',(0,2,10)),
    (((5,'F3(2,6,4)'),(14,'D8(C,A,2)'),(22,'Q4:F50(12,0,0)')),'D6(B,C,4)',(4,2,6)),
    (((4,'F2(4,4,4)'),(13,'D7(A,C,2)'),(23,'K8:F21(0,12,0)')),'F6(6,4,2)',(4,4,4)),
    (((5,'F3(4,4,4)'),(17,'X7'),(23,'Q4:F60(0,0,12)')),'D8(A,B,2)',None),
    (((5,'F3(6,4,2)'),(14,'D8(A,B,4)'),(23,'Q4:F55(4,4,4)')),'F7(4,4,4)',(0,8,4)),
    (((4,'F2(4,6,2)'),(13,'D7(B,C,2)'),(22,'K8:F20(0,0,12)')),'D8(C,A,4)',(8,4,0)),
    (((5,'F3(8,2,2)'),(17,'X8'),(23,'K8:F22(2,8,2)')),'F9(0,6,6)',(0,6,6)),
    (((4,'F2(4,4,4)'),(10,'D12(B,A,2)'),(24,'X10'),(27,'K8:F31(0,0,12)')),'F11(2,6,4)',(4,4,4)),
    (((5,'F3(6,2,4)'),(11,'D12(A,C,2)'),(25,'X10'),(28,'Q4:F90(4,4,4)')),'D11(B,A,2)',None),
    (((4,'F2(4,4,4)'),(10,'D9(C,A,4)'),(21,'F7(2,2,8)'),(27,'K8:X28')),'D8(C,B,2)',(6,4,2)),
    (((4,'F2(6,4,2)'),(9,'D11(B,C,4)'),(18,'F8(4,6,2)'),(25,'D10(A,B,2)')),'D9(C,A,2)',(4,4,4)),
)
TUBES = {'A':'留档管','B':'成分分析管','C':'复验管'}
OPERATIONS = tuple({'operation':{'volumes_ml':dict(zip(TUBES,(a,b,12-a-b)))},
                    'description':f'一次分装：A留档管{a} mL、B成分分析管{b} mL、C复验管{12-a-b} mL，三管封管。'}
                   for a in range(0,13,2) for b in range(0,13-a,2)) + (
    {'operation':{'sealed':True},'description':'保持整批12 mL封存，不分装。'},)


def _message(code):
    site,batch = 'K7','Q5'
    if ':' in code:
        scope,code = code.split(':')
        if scope.startswith('K'):
            site = scope
        else:
            batch = scope
    match = re.fullmatch(r'([FDX])(\d+)(?:\(([^)]+)\))?',code)
    if match is None:
        raise ValueError('Invalid authored sample quota')
    kind,version,fields = match.groups()
    message = {'event':'sample_quota','site':site,'batch':batch,'version':int(version)}
    if kind == 'F':
        volumes = dict(zip(TUBES,map(int,fields.split(',')),strict=True))
        message.update(kind='full',volumes_ml=volumes)
        text = '完整配额替换并授权：' + '、'.join(f'{t}{TUBES[t]}{v} mL' for t,v in volumes.items()) + '。'
    elif kind == 'D':
        source,destination,amount = fields.split(',')
        message.update(kind='transfer',source=source,destination=destination,amount_ml=int(amount))
        text = f'相对修订：从计划中{source}{TUBES[source]}配额转出{amount} mL给{destination}{TUBES[destination]}，不是立即倒液。'
    else:
        message.update(kind='revoke')
        text = '撤销本批分装，清空授权及计划配额。'
    message['text'] = f'收到采样点{site}、采集批{batch}指示，签发序号{version}。' + text
    return message


def build(index):
    rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'K7采集批Q5有12 mL均匀混合样品尚未分装，A留档管/B成分分析管/C复验管各容量12 mL，'
                '均正常洁净，精确计量，无蒸发和残留。允许用途管为空或独占全部样品。'
                '同采样点/采集批由单一控制方独立编号，已收指示按签发序号升序重放，不能按接收顺序。'
                '完整配额替换所有计划并授权；相对修订只转移指定两管的计划配额，未指明管不变，不是实际倒液。'
                '撤销清空授权及配额，之后相对修订不能重启，只有更高序号完整指示可重新授权。'
                '不同范围不能混算；无隐藏指令、同号冲突或额外期限，缺号无需等待。'
                '每个授权链内有效转出均有足够配额，始终非负2 mL倍数且总量12。'
                '准备只做均质校验，不分走样品；收到新消息后一次选择完整配方或保持整批封存，不可纠错重分。'
                '首个有效选择终结，总最多4次提交，累计3次格式错误终止。保持封存是业务决定，主动放弃计未完成。',
                event='sample_protocol',tubes=TUBES,operations=list(OPERATIONS))
    for at,code in ((2,'F1(4,4,4)'),*rows):
        message = _message(code)
        history.add(at,message.pop('text'),**message)
    history.add(30,'整批12 mL样品仍未分装，均质校验尚待完成。',event='sample_ready')
    task = task_shell('FM-C2-P2',index,background_group='FM-C2-P2-pair01' if index < 2 else None,
                      current_input_group='FM-C2-P2')
    task.public = {'time_s':clock('09:00'),'site':'K7','batch':'Q5','max_steps':4,
                   'instruction':'处理K7/Q5的本次分装任务，分装器正常，请完成均质校验。',
                   'state_fields':['prepared','format_errors','batch_ml','tube_volumes_ml','tubes_sealed'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-P2') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00'),
                    'batch_ml':12,'tube_volumes_ml':dict.fromkeys(TUBES,0),'tubes_sealed':False}
    message = _message(arrival)
    message.update(record_id='ARR01',occurred_s=clock('09:01'),received_s=clock('09:01'),
                   occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],
                  'correct_operation':{'volumes_ml':dict(zip(TUBES,expected))} if expected else {'sealed':True}}
    task.rubric = {'score':'100 iff the actual complete allocation or sealed batch matches the scoped replay'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    def submit(self,action):
        super().submit(action)
        operation = self.facts.get('executed_operation',{})
        if 'volumes_ml' in operation:
            self.state.update(batch_ml=0,tube_volumes_ml=deepcopy(operation['volumes_ml']),tubes_sealed=True)


def _replay(messages,site,batch):
    relevant = {}
    for message in messages:
        if (message['site'],message['batch']) != (site,batch):
            continue
        fields = {k:message[k] for k in ('kind','volumes_ml','source','destination','amount_ml') if k in message}
        version = message['version']
        if version in relevant and relevant[version] != fields:
            raise ValueError('Conflicting same-version sample quotas')
        relevant[version] = fields
    state = None
    for _,message in sorted(relevant.items()):
        if message['kind'] == 'full':
            state = deepcopy(message['volumes_ml'])
        elif message['kind'] == 'revoke':
            state = None
        elif state is not None:
            state[message['source']] -= message['amount_ml']
            state[message['destination']] += message['amount_ml']
        if state is not None and (sum(state.values()) != 12 or any(v < 0 or v % 2 for v in state.values())):
            raise ValueError('Invalid authored quota chain')
    return {'volumes_ml':state} if state is not None else {'sealed':True}


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'收到采样点(K\d+)、采集批(Q\d+)指示，签发序号(\d+)。(.*)',text)
        if header is None:
            continue
        site,batch,version,body = header.groups()
        message = {'site':site,'batch':batch,'version':int(version)}
        full = re.fullmatch(r'完整配额替换并授权：A留档管(\d+) mL、B成分分析管(\d+) mL、C复验管(\d+) mL。',body)
        transfer = re.fullmatch(r'相对修订：从计划中(A留档管|B成分分析管|C复验管)配额转出(\d+) mL给'
                                r'(A留档管|B成分分析管|C复验管)，不是立即倒液。',body)
        if full:
            message.update(kind='full',volumes_ml=dict(zip('ABC',map(int,full.groups()),strict=True)))
        elif transfer:
            message.update(kind='transfer',source=transfer[1][0],destination=transfer[3][0],
                           amount_ml=int(transfer[2]))
        elif body == '撤销本批分装，清空授权及计划配额。':
            message.update(kind='revoke')
        else:
            raise ValueError('Incomplete public sample quota')
        messages.append(message)
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['site'],current['batch'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Allocation differs from the scoped quota chain')
