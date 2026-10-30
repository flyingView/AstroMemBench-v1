"""FM-C2-P3: noncommuting destination swaps keyed by immutable cargo IDs."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

CONFIGS = (
    (((4,'F4ABCD'),(16,'F6BADC')),'F5CDAB','BADC'),
    (((4,'F4ABCD'),(16,'F6DCBA')),'F5CDAB','DCBA'),
    (((5,'F3ADBC'),(18,'X7')),'F6CBAD',None),
    (((4,'F2BDAC'),(15,'X5')),'F8CADB','CADB'),
    (((4,'F2BACD'),(16,'S6(1,2)')),'F5DCBA','CDBA'),
    (((5,'F3BCDA'),(17,'S7(1,4)')),'S8(2,3)','ADCB'),
    (((4,'F2ABCD'),(13,'S6(2,3)'),(23,'K7:X20')),'S5(1,2)','BCAD'),
    (((5,'F3DCBA'),(14,'S8(1,2)'),(22,'V2:F50ABCD')),'S7(2,4)','ADBC'),
    (((5,'F3CDAB'),(17,'X8'),(23,'V2:F60ABCD')),'S9(1,2)',None),
    (((4,'F2CADB'),(13,'S7(1,3)'),(22,'K7:F20ABCD')),'S8(2,4)','DBCA'),
    (((5,'F3DACB'),(13,'S7(2,4)'),(22,'K7:F29DCBA')),'K7:F30ACBD','DBCA'),
    (((5,'F3ADBC'),(17,'X8'),(23,'K7:F22BCDA')),'F9DCAB','DCAB'),
    (((4,'F2DCAB'),(10,'S12(2,4)'),(24,'X10'),(27,'K7:F31ABCD')),'F11ACBD','ADBC'),
    (((5,'F3CBAD'),(11,'S12(1,3)'),(25,'X10'),(28,'V2:F90ABCD')),'S11(2,4)',None),
    (((4,'F2ACBD'),(10,'S9(2,4)'),(21,'F7DBAC'),(27,'K7:X28')),'S8(1,2)','BCAD'),
    (((4,'F2CADB'),(9,'S11(1,2)'),(18,'F8BDAC'),(25,'S10(3,4)')),'S9(2,3)','ABCD'),
)
CARGO = {'C1':'电源包','C2':'净水包','C3':'滤芯包','C4':'工具包'}
PERMUTATIONS = ('ABCD','ABDC','ACBD','ACDB','ADBC','ADCB','BACD','BADC','BCAD','BCDA','BDAC','BDCA',
                'CABD','CADB','CBAD','CBDA','CDAB','CDBA','DABC','DACB','DBAC','DBCA','DCAB','DCBA')
OPERATIONS = tuple({'operation':{'destinations':dict(zip(CARGO,permutation))},
                    'description':'按C1至C4次序完成交付：' + '、'.join(f'{c}{CARGO[c]}→舱{d}' for c,d in zip(CARGO,permutation)) + '。'}
                   for permutation in PERMUTATIONS) + (
    {'operation':{'sealed':True},'description':'保持四箱在站内封存，不出发。'},)


def _message(code):
    order,cycle = 'K6','V3'
    if ':' in code:
        scope,code = code.split(':')
        if scope.startswith('K'):
            order = scope
        else:
            cycle = scope
    match = re.fullmatch(r'([FSX])(\d+)(.*)',code)
    if match is None:
        raise ValueError('Invalid authored delivery instruction')
    kind,version,fields = match.groups()
    message = {'event':'delivery_instruction','order':order,'cycle':cycle,'version':int(version)}
    if kind == 'F':
        destinations = dict(zip(CARGO,fields,strict=True))
        message.update(kind='full',destinations=destinations)
        text = '完整清单替换并授权：' + '、'.join(f'{c}{CARGO[c]}→舱{d}' for c,d in destinations.items()) + '。'
    elif kind == 'S':
        first,second = ('C' + n for n in fields.removeprefix('(').removesuffix(')').split(','))
        message.update(kind='swap',first=first,second=second)
        text = f'交换{first}{CARGO[first]}和{second}{CARGO[second]}在当前计划中的目的舱，不移动实物。'
    else:
        message.update(kind='revoke')
        text = '撤销本轮运输并清空交付清单。'
    message['text'] = f'收到运单{order}、运输轮{cycle}指示，签发序号{version}。' + text
    return message


def build(index):
    rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'K6运单V3轮有C1电源包/C2净水包/C3滤芯包/C4工具包各一箱，已装车但仍在装载站。'
                'A/B/C/D目的舱各接收一箱，均空置可达，运输程序预置，无路线或资源取舍。'
                '同运单/运输轮独立编号，由单一地面控制方签发，已收记录按签发序号升序重放，不按接收顺序。'
                '完整清单替换全部分配并授权；互换按不变货物ID交换其在当前计划中的目的舱，不是交换消息显示位置或移动实物。'
                '相交互换通常不可交换。撤销清空授权及清单，其后互换不能重启，只有更高序号完整清单可重新授权。'
                '外运单和旧轮独立，无隐藏指示或同号冲突，缺号无需等待，不能猜测未收消息。'
                '准备做封装校验，接收消息后选择一次完整四箱程序或保持站内封存。所有24排列均可执行，'
                '按C1至C4实际交付，没有免费试探或纠错。第一有效选择终结，总最多4次提交，累计3次格式错误终止。'
                '正常封存为业务决定，放弃任务计未完成。',event='delivery_protocol',cargo=CARGO,operations=list(OPERATIONS))
    for at,code in ((2,'F1ABCD'),*rows):
        message = _message(code)
        history.add(at,message.pop('text'),**message)
    history.add(30,'四箱仍在站内运输车中，出发前封装校验尚未完成。',event='delivery_ready')
    task = task_shell('FM-C2-P3',index,background_group='FM-C2-P3-pair01' if index < 2 else None,
                      current_input_group='FM-C2-P3')
    task.public = {'time_s':clock('09:00'),'order':'K6','cycle':'V3','max_steps':4,
                   'instruction':'继续K6运单V3轮任务，四箱已装载，请完成出发前封装校验。',
                   'state_fields':['prepared','format_errors','cargo_locations'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-P3') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00'),'cargo_locations':dict.fromkeys(CARGO,'装载站')}
    message = _message(arrival)
    message.update(record_id='ARR01',occurred_s=clock('09:01'),received_s=clock('09:01'),
                   occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],
                  'correct_operation':{'destinations':dict(zip(CARGO,expected))} if expected else {'sealed':True}}
    task.rubric = {'score':'100 iff all actual delivery destinations or station storage match scoped replay'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    def submit(self,action):
        super().submit(action)
        operation = self.facts.get('executed_operation',{})
        if 'destinations' in operation:
            self.state['cargo_locations'] = deepcopy(operation['destinations'])


def _replay(messages,order,cycle):
    relevant = {}
    for message in messages:
        if (message['order'],message['cycle']) != (order,cycle):
            continue
        fields = {k:message[k] for k in ('kind','destinations','first','second') if k in message}
        version = message['version']
        if version in relevant and relevant[version] != fields:
            raise ValueError('Conflicting same-version delivery instructions')
        relevant[version] = fields
    state = None
    for _,message in sorted(relevant.items()):
        if message['kind'] == 'full':
            state = deepcopy(message['destinations'])
        elif message['kind'] == 'revoke':
            state = None
        elif state is not None:
            a,b = message['first'],message['second']
            state[a],state[b] = state[b],state[a]
        if state is not None and sorted(state.values()) != list('ABCD'):
            raise ValueError('Delivery chain is not a permutation')
    return {'destinations':state} if state is not None else {'sealed':True}


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'收到运单(K\d+)、运输轮(V\d+)指示，签发序号(\d+)。(.*)',text)
        if header is None:
            continue
        order,cycle,version,body = header.groups()
        message = {'order':order,'cycle':cycle,'version':int(version)}
        full = re.fullmatch(r'完整清单替换并授权：C1电源包→舱([ABCD])、C2净水包→舱([ABCD])、'
                            r'C3滤芯包→舱([ABCD])、C4工具包→舱([ABCD])。',body)
        swap = re.fullmatch(r'交换(C1电源包|C2净水包|C3滤芯包|C4工具包)和'
                            r'(C1电源包|C2净水包|C3滤芯包|C4工具包)在当前计划中的目的舱，不移动实物。',body)
        if full:
            message.update(kind='full',destinations=dict(zip(('C1','C2','C3','C4'),full.groups(),strict=True)))
        elif swap:
            message.update(kind='swap',first=swap[1][:2],second=swap[2][:2])
        elif body == '撤销本轮运输并清空交付清单。':
            message.update(kind='revoke')
        else:
            raise ValueError('Incomplete public delivery instruction')
        messages.append(message)
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['order'],current['cycle'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Delivery differs from the scoped instruction chain')
