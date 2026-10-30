"""FM-C2-D1: per-role versions and per-field command priority with handback."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import paragraphs, record_paragraphs
from ...schema import story_timestamp

CONFIGS = (
    (((4,'L3EH1'),(16,'M4S--')),'L8IL0','SL0'),
    (((4,'L3EH1'),(16,'M4I--')),'L8IL0','IL0'),
    (((4,'L3IL0'),(16,'F5-H1')),'M2S--','SH1'),
    (((4,'L3SL0'),(16,'F4EH-')),'F5I-1','IL1'),
    (((5,'L3EH0'),(17,'M5S-1')),'M6X','EH0'),
    (((5,'L3SH1'),(18,'M4E--')),'M3X','EH1'),
    (((4,'L3IL0'),(12,'F5EH1'),(22,'M2S--')),'M3-L-','EL1'),
    (((5,'L3EL0'),(13,'F6SH1'),(23,'M5I-0')),'M4-L1','IH0'),
    (((4,'L3IH0'),(12,'F7EL1'),(22,'M5S--')),'F8X','SH0'),
    (((5,'L3IL0'),(13,'F5EH1'),(23,'M6-L-')),'L11SH0','EL1'),
    (((4,'L3SH0'),(12,'F5IL1'),(22,'M4E-0')),'M5-H-','IH1'),
    (((5,'L3EL1'),(13,'F7SH0'),(23,'M3I--')),'L3/M99EL1','IH0'),
    (((4,'L3IL1'),(10,'F10EH0'),(18,'M8S-1'),(25,'L3/M70IL0')),'M9-L-','EL0'),
    (((5,'L3EH0'),(11,'F8SL1'),(19,'M6IH-'),(26,'F7X')),'M7X','SL1'),
    (((5,'L3IH0'),(11,'F9EL1'),(19,'M8S--'),(26,'L12EH1')),'M9--0','EL0'),
    (((4,'L3EL1'),(10,'F10SH0'),(18,'M9-L-'),(25,'L3/F80IH1')),'F11X','EL1'),
)
ROLES = {'M':'航行指挥','F':'编队协调','L':'设备值守'}
ATTITUDES = {'S':'对日','E':'对地','I':'惯性保持'}
BEACONS = {'L':'低频','H':'高频'}
FIELDS = ('attitude','beacon','heater')
DEFAULT = {'attitude':'I','beacon':'L','heater':0}
OPERATIONS = tuple({'operation':dict(zip(FIELDS,(attitude,beacon,heater))),
                    'description':f'运行30秒：姿态{ATTITUDES[attitude]}，信标{BEACONS[beacon]}，保温循环{"开启" if heater else "关闭"}。'}
                   for attitude in 'SEI' for beacon in 'LH' for heater in (0,1))


def _message(code):
    craft,segment = 'C7','L4'
    if '/' in code:
        scope,code = code.split('/')
        if scope.startswith('C'):
            craft = scope
        else:
            segment = scope
    role,version,values = re.fullmatch(r'([MFL])(\d+)(.*)',code).groups()
    message = {'event':'cruise_instruction','craft':craft,'segment':segment,'role':role,
               'role_name':ROLES[role],'version':int(version)}
    if values == 'X':
        message.update(kind='revoke',fields={})
        text = '撤下本角色的整条规定，字段交还下级或默认。'
    else:
        attitude,beacon,heater = values
        fields = {k:v for k,v in zip(FIELDS,(attitude,beacon,int(heater) if heater != '-' else '-')) if v != '-'}
        message.update(kind='declaration',fields=fields)
        descriptions = []
        if attitude != '-':
            descriptions.append('姿态'+ATTITUDES[attitude])
        if beacon != '-':
            descriptions.append('信标'+BEACONS[beacon])
        if heater != '-':
            descriptions.append('保温循环'+('开启' if heater == '1' else '关闭'))
        text = '本角色本轮只规定以下字段：'+'、'.join(descriptions)+'；其他字段交还下级，不继承本角色旧规定。'
    message['text'] = f'收到航天器{craft}、航段{segment}的{ROLES[role]}第{version}号指示。'+text
    return message


def build(index):
    rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'C7航天器处于L4航段，下段控制持续30秒；姿态对日/对地/惯性保持、信标低频/高频、保温关闭/开启'
                '全部12种组合均可正常执行，热余量、能量和姿态安全条件充分。'
                '三角色航行指挥>编队协调>设备值守均为已验证合法来源。范围为航天器/航段/角色，'
                '各角色仅取本范围最高签发版本，接收顺序无关，跨角色编号不比较。'
                '普通消息完整替换本角色管辖字段和值，未列字段即不再管辖，不继承旧字段。'
                '逐字段依次取航行指挥、编队协调、设备值守的当前明确规定，均无规定则用设备默认：惯性保持/低频/保温关闭。'
                '角色撤销只撤下本角色规定，使低优角色或默认重新适用，不是全舰停机；旧撤销不能覆盖本角色新规定。'
                '外航天器、旧航段独立，缺号无隐藏要求，同号无冲突，无待命或缺页状态。'
                '准备做控制校验，不执行巡航段，收信后一次选择完整三字段，实际运行30秒。'
                '第一有效选择终结，总最多4次提交、累计3次格式错误终止，主动放弃计未完成。',
                event='cruise_protocol',roles=ROLES,default=DEFAULT,operations=list(OPERATIONS))
    for at,code in rows:
        message = _message(code)
        history.add(at,message.pop('text'),**message)
    history.add(30,'L4航段下一控制段尚未执行，当前控制校验待完成。',event='cruise_ready')
    task = task_shell('FM-C2-D1',index,background_group='FM-C2-D1-pair01' if index < 2 else None,
                      current_input_group='FM-C2-D1')
    task.public = {'time_s':clock('09:00'),'craft':'C7','segment':'L4','max_steps':4,
                   'instruction':'继续C7/L4的下一巡航控制段，设备正常，请完成控制校验。',
                   'state_fields':['prepared','format_errors','executed_configuration','elapsed_control_s'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-D1') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00'),
                    'executed_configuration':None,'elapsed_control_s':0}
    message = _message(arrival)
    message.update(record_id='ARR01',occurred_s=clock('09:01'),received_s=clock('09:01'),
                   occurred_at=story_timestamp(clock('09:01')),received_at=story_timestamp(clock('09:01')))
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],
                  'correct_operation':dict(zip(FIELDS,(expected[0],expected[1],int(expected[2]))))}
    task.rubric = {'score':'100 iff all three actual configuration fields follow current per-role jurisdiction'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    def submit(self,action):
        super().submit(action)
        operation = self.facts.get('executed_operation',{})
        if 'attitude' in operation:
            self.state.update(executed_configuration=deepcopy(operation),elapsed_control_s=30)
            self.state['time_s'] += 30


def _replay(messages,craft,segment):
    roles = {}
    for message in messages:
        if (message['craft'],message['segment']) != (craft,segment):
            continue
        role,version = message['role'],message['version']
        versions = roles.setdefault(role,{})
        content = (message['kind'],message['fields'])
        if version in versions and versions[version] != content:
            raise ValueError('Conflicting same-version role declaration')
        versions[version] = content
    current = {r:versions[max(versions)][1] for r,versions in roles.items()}
    result = deepcopy(DEFAULT)
    for role in ('L','F','M'):
        result.update(current.get(role,{}))
    return result


def _instructions(texts):
    messages = []
    for text in texts:
        match = re.fullmatch(r'收到航天器(C\d+)、航段(L\d+)的(航行指挥|编队协调|设备值守)第(\d+)号指示。(.*)', text)
        if match is None:
            continue
        craft, segment, role_name, version, content = match.groups()
        role = next(key for key, name in ROLES.items() if name == role_name)
        fields = {}
        if content == '撤下本角色的整条规定，字段交还下级或默认。':
            kind = 'revoke'
        else:
            declaration = re.fullmatch(r'本角色本轮只规定以下字段：(.*)；其他字段交还下级，不继承本角色旧规定。', content)
            if declaration is None:
                raise ValueError('Missing the scope of a public cruise instruction')
            kind = 'declaration'
            vocabulary = {**{'姿态'+name:('attitude',key) for key,name in ATTITUDES.items()},
                          **{'信标'+name:('beacon',key) for key,name in BEACONS.items()},
                          '保温循环开启':('heater',1), '保温循环关闭':('heater',0)}
            for description in declaration[1].split('、') if declaration[1] else ():
                key, value = vocabulary[description]
                fields[key] = value
        messages.append({'craft':craft, 'segment':segment, 'role':role,
                         'version':int(version), 'kind':kind, 'fields':fields})
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['craft'],current['segment'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Cruise configuration differs from current scoped role declarations')
