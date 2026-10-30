"""FM-C2-P1: replay full instructions, field patches and revocations by scope."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

# Explicit received histories and arrival, followed by the independently authored
# final mode/side (None denotes no authorization). Scope prefixes are literal.
CONFIGS = (
    ('R2',((4,'F4NE'),(15,'F6WW')),'F5NW','WW'),
    ('R2',((4,'F4NE'),(15,'F6NW')),'F5WW','NW'),
    ('R1',((5,'F3WE'),(17,'X7')),'F6NE',None),
    ('R2',((3,'F2WE'),(12,'X5')),'F6NW','NW'),
    ('R2',((5,'F1NW'),(14,'F4WW')),'F7WE','WE'),
    ('R1',((4,'F2WE'),(18,'F6NE')),'F7WW','WW'),
    ('R3',((3,'F2WE'),(10,'P5侧W'),(20,'R1:F9NE')),'P4方N','NW'),
    ('R1',((4,'F3NW'),(12,'P6方W'),(21,'R2:X11')),'P5侧E','WE'),
    ('R2',((3,'F1WE'),(11,'X4'),(18,'R3:F8WW')),'P3侧W',None),
    ('R1',((4,'F3WE'),(14,'P8方N'),(22,'R2:X20')),'F6WW','NW'),
    ('R3',((4,'F2WE'),(16,'X7'),(24,'R1:F18NW')),'P8方N',None),
    ('R1',((3,'F2NW'),(12,'X6'),(22,'R2:F19WW')),'F8NE','NE'),
    ('R3',((3,'F2WW'),(9,'P7方N'),(16,'Q11/R3:F40WW'),(28,'F6WE')),'R1:X12','NE'),
    ('R1',((3,'F2NE'),(8,'F8WW'),(21,'R2:F13NE'),(28,'X7')),'Q11/R1:X55','WW'),
    ('R3',((3,'F3NW'),(8,'P12方W'),(21,'X10'),(26,'R1:F30WE')),'P11侧E',None),
    ('R1',((3,'F2NW'),(8,'X9'),(20,'P11方W'),(28,'F10NE')),'P12侧W','WW'),
)
MODE_NAMES = {'W':'宽带','N':'窄带'}
SIDE_NAMES = {'E':'东侧','W':'西侧'}
OPERATIONS = tuple({'operation':{'region':region,'mode':mode,'side':side},
                    'description':f'对{region}执行{MODE_NAMES[mode]}勘察，从{SIDE_NAMES[side]}起扫。'}
                   for region in ('R1','R2','R3') for mode in ('W','N') for side in ('E','W')) + (
    {'operation':{'standby':True},'description':'保持待命，本次不启动扫描。'},)


def _message(code,region):
    cycle = 'Q12'
    if ':' in code:
        scope,code = code.split(':')
        if '/' in scope:
            cycle,region = scope.split('/')
        else:
            region = scope
    match = re.fullmatch(r'([FPX])(\d+)(.*)',code)
    if match is None:
        raise ValueError('Invalid authored survey instruction')
    kind,version,fields = match.groups()
    content = {'event':'survey_instruction','cycle':cycle,'region':region,'version':int(version)}
    if kind == 'F':
        mode,side = fields
        content.update(kind='full',fields={'mode':mode,'side':side})
        description = f'完整指示：{MODE_NAMES[mode]}勘察，从{SIDE_NAMES[side]}起扫，替换配置并授权。'
    elif kind == 'P':
        field,value = fields
        name = {'方':'mode','侧':'side'}[field]
        content.update(kind='patch',fields={name:value})
        description = '字段修订：' + (f'勘察方式改为{MODE_NAMES[value]}。' if name == 'mode' else f'起扫改为{SIDE_NAMES[value]}。')
    else:
        if fields:
            raise ValueError('Revocation has no configuration fields')
        content.update(kind='revoke',fields={})
        description = '撤销该范围作业授权并清除配置。'
    content['text'] = f'收到转发：周期{cycle}、区域{region}，签发序号{version}。{description}'
    return content


def build(index):
    region,rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'Q12区域勘察各周期/区域由同一控制方独立编号，按签发序号从小到大重放已收到的指示。'
                '完整指示替换全部方式和起扫侧并授权；字段修订只改明确字段、其他继承此前有效配置。'
                '撤销清除授权及配置，此后的修订不能重启或跨撤销继承；只有更高序号完整指示可重新授权。'
                '接收顺序不决定效力，迟到完整底稿或中间补丁须按其位置重放，不同周期/区域不能比较编号或串用字段。'
                '无同范围同号异文，不存在未收的隐藏指示；序号空缺无需等待，无另加期限。设备正常，扫描轨迹预置。'
                '完成准备后接收新消息，再选择当前指定区域的一次勘察；无授权则保持待命。选其他区域为业务错误。'
                '总最多4次环境提交，累计3次格式错误终止；第一有效作业选择终结，不重试，主动放弃为未完成。',
                event='survey_protocol',operations=list(OPERATIONS))
    for at,code in rows:
        content = _message(code,region)
        history.add(at,content.pop('text'),**content)
    history.add(30,'平台转位完成，测量前最后校验尚未执行，本轮尚未采集。',event='survey_ready')
    task = task_shell('FM-C2-P1',index,background_group='FM-C2-P1-pair01' if index in (0,1) else None,
                      current_input_group=f'FM-C2-P1-{region}')
    task.public = {'time_s':clock('09:00'),'cycle':'Q12','region':region,'max_steps':4,
                   'instruction':f'继续处理Q12的{region}本轮任务。设备待命，请完成作业前准备。',
                   'state_fields':['prepared','format_errors'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-P1') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00')}
    message = _message(arrival,region)
    message.update(record_id='ARR01',occurred_s=clock('09:01'),received_s=clock('09:01'),
                   occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],
                  'correct_operation':{'region':region,'mode':expected[0],'side':expected[1]} if expected else {'standby':True}}
    task.rubric = {'score':'100 iff the actual operation matches the scoped replay decision'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    pass


def _replay(messages,cycle,region):
    relevant = {}
    for message in messages:
        if (message['cycle'],message['region']) != (cycle,region):
            continue
        record = (message['kind'],message['fields'])
        version = message['version']
        if version in relevant and relevant[version] != record:
            raise ValueError('Conflicting same-version survey instructions')
        relevant[version] = record
    state = None
    for _,(kind,fields) in sorted(relevant.items()):
        if kind == 'full':
            state = deepcopy(fields)
        elif kind == 'revoke':
            state = None
        elif kind == 'patch' and state is not None:
            state.update(fields)
    return {'standby':True} if state is None else {'region':region,**state}


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'收到转发：周期(Q\d+)、区域(R\d+)，签发序号(\d+)。(.*)',text)
        if header is None:
            continue
        cycle,region,version,body = header.groups()
        message = {'cycle':cycle,'region':region,'version':int(version)}
        full = re.fullmatch(r'完整指示：(宽带|窄带)勘察，从(东侧|西侧)起扫，替换配置并授权。',body)
        mode = re.fullmatch(r'字段修订：勘察方式改为(宽带|窄带)。',body)
        side = re.fullmatch(r'字段修订：起扫改为(东侧|西侧)。',body)
        if full:
            message.update(kind='full',fields={'mode':{'宽带':'W','窄带':'N'}[full[1]],
                                               'side':{'东侧':'E','西侧':'W'}[full[2]]})
        elif mode:
            message.update(kind='patch',fields={'mode':{'宽带':'W','窄带':'N'}[mode[1]]})
        elif side:
            message.update(kind='patch',fields={'side':{'东侧':'E','西侧':'W'}[side[1]]})
        elif body == '撤销该范围作业授权并清除配置。':
            message.update(kind='revoke',fields={})
        else:
            raise ValueError('Incomplete public survey instruction')
        messages.append(message)
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['cycle'],current['region'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Survey decision differs from the received scoped instruction chain')
