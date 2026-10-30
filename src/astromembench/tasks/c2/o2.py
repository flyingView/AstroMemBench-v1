"""FM-C2-O2: highest work order, explicit base tree and root authorization."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

CONFIGS = (
    (((4,'F2A4'),(16,'F6B8')),'F5C6',('B',8)),
    (((4,'F2A4'),(16,'F6C10')),'F5C6',('C',10)),
    (((5,'F3C4'),(18,'X7')),'F6B8',None),
    (((4,'F2A6'),(15,'X5')),'F8C4',('C',4)),
    (((4,'F2A4'),(16,'P6<2:T8')),'F5C10',('A',8)),
    (((4,'F2C10'),(16,'F6A6')),'P7<2:T4',('C',4)),
    (((4,'F2A4'),(11,'P8<2:T10'),(21,'F5C6')),'P7<5:PB',('A',10)),
    (((5,'F3B8'),(14,'P9<7:PC'),(23,'U8/F30B10')),'F7A4',('C',4)),
    (((4,'F2C6'),(13,'P8<5:T10'),(22,'U8/F5B4')),'F4B8',None),
    (((4,'F2A8'),(14,'P9<7:T4'),(22,'Q3/F60C10')),'P7<2:PB',('B',4)),
    (((4,'F2B10'),(13,'P8<6:T6'),(22,'U8/F4C4')),'P6<4:PA',None),
    (((4,'F2C8'),(12,'X6'),(21,'F7B4')),'P9<7:T10',('B',10)),
    (((4,'F2B4'),(10,'P12<8:T8'),(21,'F7C6'),(26,'Q3/F5A10')),'P8<5:PA',None),
    (((4,'F2A6'),(10,'P13<10:PC'),(20,'X9'),(27,'F10B4')),'P12<2:T10',('C',4)),
    (((5,'F3B4'),(10,'P14<11:PC'),(18,'F10A8'),(25,'P11<10:T6')),'X12',None),
    (((5,'F3C6'),(9,'P15<12:PB'),(18,'X10'),(26,'P12<11:T8')),'F11A4',('B',8)),
)
OPERATIONS = tuple({'operation':{'part':part,'torque_nm':torque},
                    'description':f'装入备件{part}并以{torque} N·m锁固。'}
                   for part in 'ABC' for torque in (4,6,8,10)) + (
    {'operation':{'standby':True},'description':'保持设备待命，不开始更换。'},)


def _message(code):
    unit,cycle = 'U7','Q4'
    if '/' in code:
        scope,code = code.split('/')
        if scope.startswith('U'):
            unit = scope
        else:
            cycle = scope
    match = re.fullmatch(r'([FPX])(\d+)(.*)',code)
    kind,version,fields = match.groups()
    message = {'event':'repair_order','unit':unit,'cycle':cycle,'version':int(version)}
    if kind == 'F':
        part,torque = fields[0],int(fields[1:])
        message.update(kind='full',fields={'part':part,'torque_nm':torque})
        text = f'完整作业配置：备件{part}，扭矩{torque} N·m。'
    elif kind == 'P':
        base,change = fields.removeprefix('<').split(':')
        field,value = ('part',change[1:]) if change[0] == 'P' else ('torque_nm',int(change[1:]))
        message.update(kind='patch',base_version=int(base),fields={field:value})
        text = f'明确引用本范围第{base}号底稿，只把' + (f'备件改为{value}。' if field == 'part' else f'扭矩改为{value} N·m。')
    else:
        message.update(kind='revoke',fields={})
        text = '撤销本范围维修授权。'
    message['text'] = f'收到设备{unit}、维修轮{cycle}工单，签发序号{version}。' + text
    return message


def build(index):
    rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'U7维修轮Q4需更换锁固组件，尚未拆换。备件A/B/C、扭矩4/6/8/10 N·m全部组合均可正常执行。'
                '每设备/维修轮单一签发方独立编号。完整单给齐配置；修订单明确引用同范围更低版本，'
                '从该底稿完整配置改一个字段，不是对最近所见任意配置打补丁。底稿可为完整单或修订单。'
                '控制候选是已收到的最高序号记录，不是最高可解析记录。候选撤销则待命；否则沿明确引用回溯完整单，'
                '缺任一底稿则待命，不降级执行旧单，不猜缺页，无索取接口。'
                '本范围已收撤销最大序号为c，无则0；链根完整单序号必须大于c，否则仍待命，修订单不重新授权。'
                '只沿候选链恢复两个字段，其他分支不能拼接，外设备/轮次不能替代底稿、参加候选或撤销比较。'
                '编号缺口无隐含消息，同号无冲突，无期限或硬件状态变化。准备只清点工具，不拆件。'
                '准备后收信再选择一次更换或待命，首个有效决定终结，总最多4次提交、累计3次格式错误终止。'
                '主动放弃计未完成。',event='repair_protocol',operations=list(OPERATIONS))
    for at,code in ((2,'F1A4'),*rows):
        message = _message(code)
        history.add(at,message.pop('text'),**message)
    history.add(30,'本次组件更换尚未开始，工具清点尚待完成。',event='repair_ready')
    task = task_shell('FM-C2-O2',index,background_group='FM-C2-O2-pair01' if index < 2 else None,
                      current_input_group='FM-C2-O2')
    task.public = {'time_s':clock('09:00'),'unit':'U7','cycle':'Q4','max_steps':4,
                   'instruction':'继续U7在Q4的本次锁固组件更换，设备正常，请完成工具清点。',
                   'state_fields':['prepared','format_errors','replacement'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-O2') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00'),'replacement':None}
    message = _message(arrival)
    message.update(record_id='ARR01',occurred_s=clock('09:01'),received_s=clock('09:01'),
                   occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],
                  'correct_operation':{'part':expected[0],'torque_nm':expected[1]} if expected else {'standby':True}}
    task.rubric = {'score':'100 iff the actual complete repair or standby matches the authorized candidate tree'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    def submit(self,action):
        super().submit(action)
        operation = self.facts.get('executed_operation',{})
        if 'part' in operation:
            self.state['replacement'] = deepcopy(operation)


def _replay(messages,unit,cycle):
    versions = {}
    for message in messages:
        if (message['unit'],message['cycle']) != (unit,cycle):
            continue
        content = {k:message[k] for k in ('kind','fields','base_version') if k in message}
        if message['version'] in versions and versions[message['version']] != content:
            raise ValueError('Conflicting same-version repair orders')
        versions[message['version']] = content
    cursor = max(versions)
    cancelled = max((v for v,m in versions.items() if m['kind'] == 'revoke'),default=0)
    patches = []
    while cursor in versions:
        message = versions[cursor]
        if message['kind'] == 'revoke':
            break
        if message['kind'] == 'full':
            if cursor <= cancelled:
                break
            result = deepcopy(message['fields'])
            for patch in reversed(patches):
                result.update(patch)
            return result
        if message['base_version'] >= cursor:
            raise ValueError('Repair references must point to lower versions')
        patches.append(message['fields'])
        cursor = message['base_version']
    return {'standby':True}


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'收到设备(U\d+)、维修轮(Q\d+)工单，签发序号(\d+)。(.*)',text)
        if header is None:
            continue
        unit,cycle,version,body = header.groups()
        message = {'unit':unit,'cycle':cycle,'version':int(version)}
        full = re.fullmatch(r'完整作业配置：备件([ABC])，扭矩(\d+) N·m。',body)
        part = re.fullmatch(r'明确引用本范围第(\d+)号底稿，只把备件改为([ABC])。',body)
        torque = re.fullmatch(r'明确引用本范围第(\d+)号底稿，只把扭矩改为(\d+) N·m。',body)
        if full:
            message.update(kind='full',fields={'part':full[1],'torque_nm':int(full[2])})
        elif part:
            message.update(kind='patch',base_version=int(part[1]),fields={'part':part[2]})
        elif torque:
            message.update(kind='patch',base_version=int(torque[1]),fields={'torque_nm':int(torque[2])})
        elif body == '撤销本范围维修授权。':
            message.update(kind='revoke',fields={})
        else:
            raise ValueError('Incomplete public repair order')
        messages.append(message)
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['unit'],current['cycle'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Repair differs from the scoped candidate and its authorized root')
