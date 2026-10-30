"""FM-C2-O3: atomically activate complete, scoped three-part supply packages."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

CONFIGS = (
    (((4,'G4A4'),(16,'G6B6')),'G5C8',('B',6)),
    (((4,'G4A4'),(16,'G6C2')),'G5C8',('C',2)),
    (((5,'G3C6'),(18,'X7')),'G6B8',None),
    (((5,'G3A2'),(12,'R7B'),(19,'V7:8')),'K7',('B',8)),
    (((5,'G3C6'),(12,'R8A'),(20,'K8')),'V8:4',('A',4)),
    (((4,'G2B4'),(13,'V7:6'),(20,'K7')),'R7C',('C',6)),
    (((5,'G3A4'),(11,'R7B'),(18,'V7:8'),(24,'S8/K7')),'V8:2',('A',4)),
    (((4,'G2B6'),(10,'R8C'),(14,'K8'),(20,'V7:2'),(25,'K7')),'R7A',('A',2)),
    (((5,'G3B8'),(11,'X6'),(18,'R9C'),(25,'V9:4')),'K8',None),
    (((4,'G2C6'),(11,'X7'),(18,'R8A'),(25,'K8')),'V8:2',('A',2)),
    (((5,'G3C8'),(10,'R9B'),(16,'K9'),(24,'G7A6')),'V9:2',('B',2)),
    (((5,'G3B6'),(11,'R8C'),(17,'V8:8'),(24,'B5/K8')),'K8',('C',8)),
    (((4,'G2A2'),(9,'V10:8'),(13,'K10'),(20,'R9C'),(26,'K9')),'V9:4',('C',4)),
    (((5,'G3A6'),(10,'X10'),(16,'R12C'),(22,'K12'),(27,'V11:8')),'K11',None),
    (((4,'G2B8'),(9,'G9C2'),(14,'R12A'),(18,'K12'),(23,'V10:6'),(27,'K10')),'R10B',('B',6)),
    (((5,'G3A4'),(10,'R11C'),(15,'V11:8'),(20,'B5/K11'),(26,'G10B6')),'K11',('C',8)),
)
OPERATIONS = tuple({'operation':{'receiver':receiver,'volume_l':volume},
                    'description':f'向接收单元{receiver}实际输送{volume} L并关闭阀门。'}
                   for receiver in 'ABC' for volume in (2,4,6,8)) + (
    {'operation':{'closed':True},'description':'保持三阀关闭，不输送。'},)


def _messages(code):
    craft,batch = 'S7','B6'
    if '/' in code:
        scope,code = code.split('/')
        if scope.startswith('S'):
            craft = scope
        else:
            batch = scope
    kind,version,value = re.fullmatch(r'([GRVKX])(\d+)(.*)',code).groups()
    base = {'event':'supply_component','craft':craft,'batch':batch,'version':int(version)}
    if kind == 'G':
        components = [('receiver',value[0]),('volume_l',int(value[1:])),('signature',True)]
    elif kind == 'R':
        components = [('receiver',value)]
    elif kind == 'V':
        components = [('volume_l',int(value.removeprefix(':')))]
    else:
        components = [('signature' if kind == 'K' else 'revoke',True)]
    result = []
    for component,content in components:
        description = {'receiver':f'接收单元为{content}', 'volume_l':f'本次体积为{content} L',
                       'signature':'控制方发布签章（不是交付确认）','revoke':'独立撤销补给授权'}[component]
        result.append({**base,'component':component,'value':content,
                       'text':f'收到航天器{craft}、补给批{batch}第{version}号消息组成项：{description}。'})
    return result


def build(index):
    rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'S7补给批B6当前供给端30 L，A/B/C接收单元各可接收40 L，全部连接和安全前提已满足。'
                '每次只执行一个2/4/6/8 L定量脉冲，所有菜单均可执行，不计历史输送。'
                '同航天器/批次每版包包含接收单元、体积和发布签章三项；同范围同版本三项都收到才原子生效。'
                '签章可先到，不齐的更高包不阻断旧完整包，不同版本或范围不能借字段，同字段无冲突值。'
                '独立撤销无需三项。比较当前范围全部完整包与撤销，最高版本为完整包则执行，为撤销则关阀。'
                '版本更高的完整包重新授权，尚未齐备的版本不参加比较，没有最新签章强制停止旧包的规则。'
                '发布签章只组成控制指令，不是交付确认；无期限、隐藏默认值或额外真实性判断。'
                '准备做校验但不输送，收到一条消息或完整信封后一次决定。首个有效选择终结，'
                '总最多4次提交、累计3次格式错误终止，主动放弃计未完成。',event='supply_protocol',operations=list(OPERATIONS))
    for at,code in ((2,'G1A2'),*rows):
        for message in _messages(code):
            history.add(at,message.pop('text'),**message)
    history.add(30,'本次输送脉冲未开始，装置待命，校验尚待完成。',event='supply_ready')
    task = task_shell('FM-C2-O3',index,background_group='FM-C2-O3-pair01' if index < 2 else None,
                      current_input_group='FM-C2-O3')
    task.public = {'time_s':clock('09:00'),'craft':'S7','batch':'B6','max_steps':4,
                   'instruction':'继续S7/B6本次补给，请完成装置校验。',
                   'state_fields':['prepared','format_errors','source_l','available_capacity_l','received_l','valves_closed'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-O3') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00'),'source_l':30,
                    'available_capacity_l':dict.fromkeys('ABC',40),'received_l':dict.fromkeys('ABC',0),'valves_closed':True}
    arrivals = _messages(arrival)
    for number,message in enumerate(arrivals,1):
        message.update(record_id=f'ARR01-{number}',occurred_s=clock('09:01'),received_s=clock('09:01'),
                       occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':arrivals,
                  'correct_operation':{'receiver':expected[0],'volume_l':expected[1]} if expected else {'closed':True}}
    task.rubric = {'score':'100 iff the actual pulse or closed valves match the highest complete control record'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    def submit(self,action):
        super().submit(action)
        operation = self.facts.get('executed_operation',{})
        if 'receiver' in operation:
            receiver,amount = operation['receiver'],operation['volume_l']
            self.state['source_l'] -= amount
            self.state['received_l'][receiver] += amount
            self.state['available_capacity_l'][receiver] -= amount


def _replay(messages,craft,batch):
    packages = {}
    for message in messages:
        if (message['craft'],message['batch']) != (craft,batch):
            continue
        package = packages.setdefault(message['version'],{})
        component,value = message['component'],message['value']
        if component in package and package[component] != value:
            raise ValueError('Conflicting same-version supply component')
        package[component] = value
    complete = {v:p for v,p in packages.items() if p.get('revoke') or {'receiver','volume_l','signature'} <= p.keys()}
    highest = complete[max(complete)]
    return {'closed':True} if highest.get('revoke') else {'receiver':highest['receiver'],'volume_l':highest['volume_l']}


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'收到航天器(S\d+)、补给批(B\d+)第(\d+)号消息组成项：(.*)。',text)
        if header is None:
            continue
        craft,batch,version,body = header.groups()
        receiver = re.fullmatch(r'接收单元为([ABC])',body)
        volume = re.fullmatch(r'本次体积为(\d+) L',body)
        if receiver:
            component,value = 'receiver',receiver[1]
        elif volume:
            component,value = 'volume_l',int(volume[1])
        elif body == '控制方发布签章（不是交付确认）':
            component,value = 'signature',True
        elif body == '独立撤销补给授权':
            component,value = 'revoke',True
        else:
            raise ValueError('Incomplete public supply component')
        messages.append({'craft':craft,'batch':batch,'version':int(version),
                         'component':component,'value':value})
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['craft'],current['batch'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Supply decision differs from the highest complete scoped package')
