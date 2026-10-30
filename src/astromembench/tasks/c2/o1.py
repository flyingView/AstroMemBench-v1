"""FM-C2-O1: scoped noncommutative work-order updates minus visible held images."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

CONFIGS = (
    ('A',((4,'F4AB'),(16,'F6AC')),'F5BCD','C'),
    ('A',((4,'F4AB'),(16,'F6BC')),'F5BCD','BC'),
    ('C',((5,'F3BC'),(18,'X7')),'F6AB',''),
    ('D',((4,'F2AC'),(16,'X5')),'F6BD','B'),
    ('',((4,'F2AD'),(16,'F4BC')),'F5ABCD','ABCD'),
    ('AB',((5,'F3AB'),(18,'F6ABC')),'F7AB',''),
    ('D',((5,'F3AB'),(12,'+8D'),(23,'V3:F50ABCD')),'F6BC','BC'),
    ('C',((5,'F3ABC'),(16,'X8'),(23,'T8:F20D')),'+9D',''),
    ('AB',((4,'F2AB'),(15,'X6'),(22,'V3:X60')),'F9BCD','CD'),
    ('A',((4,'F2AB'),(13,'+8D'),(21,'V3:F70C')),'-7D','BD'),
    ('C',((5,'F3AC'),(14,'-8C'),(22,'T8:F17BD')),'+7C','A'),
    ('B',((4,'F2CD'),(13,'-6D'),(21,'T8:F12ABC')),'T8:X14','C'),
    ('D',((4,'F2AC'),(10,'+12D'),(24,'X10'),(27,'T8:F31AC')),'F11AB','AB'),
    ('AB',((5,'F3CD'),(11,'+12A'),(25,'X10'),(28,'V3:F90ABCD')),'-11D',''),
    ('C',((4,'F2AB'),(10,'+8AC'),(24,'F6BD'),(27,'T8:X28')),'-7B','AD'),
    ('A',((4,'F2AB'),(9,'-11B'),(17,'F8BC'),(25,'+10D')),'+9A','CD'),
)
PARTS = {'A':'天线根部外罩','B':'太阳翼连接件','C':'载荷舱外板','D':'星敏感器安装座'}
SUBSETS = ('','A','B','C','D','AB','AC','AD','BC','BD','CD','ABC','ABD','ACD','BCD','ABCD')
OPERATIONS = tuple({'operation':{'parts':list(parts)},'description':
                    '批量新增拍摄' + '、'.join(PARTS[p] for p in parts) + '，每处100 ms。' if parts else '不新增拍摄。'} for parts in SUBSETS)


def _message(code):
    target,service = 'T7','V4'
    if ':' in code:
        scope,code = code.split(':')
        if scope.startswith('T'):
            target = scope
        else:
            service = scope
    match = re.fullmatch(r'([F+X-])(\d+)([ABCD]*)',code)
    if match is None:
        raise ValueError('Invalid authored inspection work order')
    kind,version,parts = match.groups()
    kind = {'F':'full','+':'add','-':'remove','X':'revoke'}[kind]
    content = {'event':'inspection_work_order','target':target,'service':service,
               'version':int(version),'kind':kind,'parts':list(parts)}
    verb = {'full':'完整替换检查项目并授权','add':'增列检查项目','remove':'删列检查项目','revoke':'撤销检查授权并清空项目'}[kind]
    content['text'] = f'收到转发：目标{target}、服务轮次{service}，签发序号{version}，{verb}' + (
        '：' + '、'.join(f'{p}{PARTS[p]}' for p in parts) if parts else '') + '。'
    return content


def build(index):
    held,rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'目标T7服务轮次V4的四部位可独立预置成像，每张100 ms，设备、照明和路径正常。'
                '同目标/轮次的工单按签发序号从小到大重放；其他范围独立。完整单替换集合并授权，增列并入集合，删列移除集合，'
                '重复增列或删除不存在项均合法。撤销清空集合并取消授权，其后仅完整单可重新授权，增删不能重启。'
                '完整单清除更早增删效果但后续增删仍生效；序号空缺不等于缺件，无隐藏消息、同号冲突或期限。'
                '本轮已取得的合格图像持续可用且清单当前公开；本次只新增仍被要求且尚无图像的部位，不能重拍、多拍或漏拍。'
                '最终未授权或已全满足均应选择不新增拍摄；这与放弃任务不同。准备后收到新工单再一次选择子集，'
                '各非空请求逐处实际成像、不自动去重。总最多4次提交，累计3次格式错误终止，第一有效选择终结，主动放弃不计完成。',
                event='inspection_protocol',parts=PARTS,operations=list(OPERATIONS))
    message = _message('F1ABCD')
    history.add(2,message.pop('text'),**message)
    history.add(3,('已取得本轮合格图像：' + '、'.join(f'{p}{PARTS[p]}' for p in held) + '；其余尚未拍摄。') if held else
                '本轮合格图像清单为空，四部位均尚未拍摄。',event='inspection_images',target='T7',service='V4',qualified_parts=list(held))
    for at,code in rows:
        message = _message(code)
        history.add(at,message.pop('text'),**message)
    history.add(29,'图像存储可用，设备自检通过。',event='equipment_status')
    history.add(30,'准备尚待完成，本次准备后的追加拍摄尚未开始，之前取得的合格图像仍然可用。',event='inspection_ready')
    task = task_shell('FM-C2-O1',index,background_group='FM-C2-O1-pair01' if index in (0,1) else None,
                      current_input_group=f'FM-C2-O1-{held or "empty"}')
    task.public = {'time_s':clock('09:00'),'target':'T7','service':'V4','qualified_parts':list(held),'max_steps':4,
                   'instruction':'继续目标T7服务轮次V4的巡检。请完成作业前准备。','parts':PARTS,
                   'state_fields':['prepared','format_errors'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-O1') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00')}
    message = _message(arrival)
    message.update(record_id='ARR01',occurred_s=clock('09:01'),received_s=clock('09:01'),
                   occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],'correct_operation':{'parts':list(expected)}}
    task.rubric = {'score':'100 iff the actual new image set equals required minus current qualified images'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    pass


def _replay(messages,target,service):
    relevant = {}
    for message in messages:
        if (message['target'],message['service']) != (target,service):
            continue
        value = (message['kind'],set(message['parts']))
        if message['version'] in relevant and relevant[message['version']] != value:
            raise ValueError('Conflicting same-version inspection work orders')
        relevant[message['version']] = value
    active = None
    for _,(kind,parts) in sorted(relevant.items()):
        if kind == 'full':
            active = set(parts)
        elif kind == 'revoke':
            active = None
        elif active is not None:
            if kind == 'add':
                active.update(parts)
            elif kind == 'remove':
                active.difference_update(parts)
    return active or set()


def _instructions(texts):
    messages = []
    names = {key+name:key for key,name in PARTS.items()}
    kinds = {'完整替换检查项目并授权':'full','增列检查项目':'add','删列检查项目':'remove',
             '撤销检查授权并清空项目':'revoke'}
    for text in texts:
        header = re.fullmatch(r'收到转发：目标(T\d+)、服务轮次(V\d+)，签发序号(\d+)，(.*)',text)
        if header is None:
            continue
        target,service,version,body = header.groups()
        instruction = re.fullmatch(r'(完整替换检查项目并授权|增列检查项目|删列检查项目|撤销检查授权并清空项目)'
                                   r'(?:：(.*))?。',body)
        if instruction is None:
            raise ValueError('Incomplete public inspection work order')
        parts = [names[name] for name in instruction[2].split('、')] if instruction[2] else []
        messages.append({'target':target,'service':service,'version':int(version),
                         'kind':kinds[instruction[1]],'parts':parts})
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    required = _replay(facts['messages'],current['target'],current['service'])
    decision = {'parts':sorted(required-set(current['qualified_parts']))}
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Inspection decision differs from scoped work orders and held images')
