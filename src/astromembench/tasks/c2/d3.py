"""FM-C2-D3: versioned directory rules, revocation tombstones and fallback."""
from copy import deepcopy
import re

from ..common import History, clock, ordered_options, task_shell
from ..prepared import PreparedChoiceRuntime, audit_decision_cases as audit_cases
from ..prose import STORY_STAMP, paragraphs, record_paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('SCI.IR.LINE',('*:1:AR','SCI:7:BF','SCI.IR:4:CL'),'SCI.IR:3:AL','CL'),
    ('SCI.IR.LINE',('*:1:AR','SCI:7:BF','SCI.IR:2:CL'),'SCI.IR:3:AL','AL'),
    ('ENG.THERM.LOOP',('*:1:AF','ENG:3:CR','SCI:12:BF'),'ENG:4:H',None),
    ('ENG.THERM.LOOP',('*:1:AF','ENG:5:CR','SCI:12:BF'),'ENG:4:H','CR'),
    ('SCI.IR.LINE',('*:1:BR','SCI:5:AL','SCI.IR:3:CF'),'SCI.IR:4:X','AL'),
    ('SCI.VIS.FRAME',('*:1:AR','SCI:3:H','ENG:8:CF'),'SCI:4:X','AR'),
    ('SCI.IR.LINE',('*:1:AR','SCI:8:BF','SCI.IR:6:CL','SCI.IR.LINE:2:BR'),'SCI.IR:7:X','BR'),
    ('SCI.IR.LINE',('*:1:BR','SCI:3:AF','SCI.IR:4:CL','SCI.IR.LINE:5:X'),'SCI.IR.LINE:4:CF','CL'),
    ('ENG.THERM.LOOP',('*:1:AL','ENG:7:BF','ENG.THERM:4:X','ENG:3:CL'),'ENG.THERM:3:CR','BF'),
    ('SCI.IR.LINE',('*:1:CR','SCI:6:BL','SCI.IR:3:AF','SCI.IR.LINE:2:H'),'SCI.IR.LINE:1:CL',None),
    ('SCI.IR.CONT',('*:1:CL','SCI:4:AR','SCI.IR:3:BF','SCI.IR.LINE:9:CL'),'SCI.IR.CONT:1:CR','CR'),
    ('SCI.IR.LINE',('*:1:AF','SCI:4:BR','SCI.IR:5:X','SCI.IR.LINE:7:H'),'SCI.IR.LINE:8:X','BR'),
    ('SCI.VIS.FRAME',('*:1:BR','SCI:4:AF','SCI.VIS:8:X','邻/SCI.VIS:99:CL','SCI.VIS:7:BR'),'SCI.VIS:9:CF','CF'),
    ('ENG.THERM.LOOP',('*:1:BF','ENG:3:AR','ENG.THERM:7:CL','ENG.THERM.LOOP:9:H','旧/ENG.THERM.LOOP:88:AF'),'ENG.THERM:8:X',None),
    ('SCI.IR.LINE',('*:1:CR','SCI:5:BL','SCI.IR:3:H','SCI.IR.LINE:4:X','邻/*:100:AR'),'SCI.IR.LINE:5:AF','AF'),
    ('SCI.IR.CONT',('*:1:AL','SCI:4:CF','SCI.IR:7:BR','SCI.IR.CONT:8:X','SCI.IRX:90:BF'),'SCI.IR:6:H','BR'),
)
PACKAGING = {'R':'原始帧','L':'无损块封装','F':'冗余分片封装'}
OPERATIONS = tuple({'operation':{'endpoint':endpoint,'packaging':packaging},
                    'description':f'向接收端{endpoint}以{PACKAGING[packaging]}回传本件全部64 MiB净荷。'}
                   for endpoint in 'ABC' for packaging in 'RLF') + (
    {'operation':{'standby':True},'description':'保持待机，本次不发送净荷。'},)


def _message(code,received):
    craft,batch = 'DS7','B12'
    if '/' in code:
        scope,code = code.split('/')
        if scope == '旧':
            batch = 'B11'
        else:
            craft = 'DS8'
    prefix,version,content = code.split(':')
    version = int(version)
    issued = clock('06:00',119 if batch == 'B11' else 120) + version
    message = {'event':'downlink_rule','craft':craft,'batch':batch,'prefix':prefix,'version':version,
               'issued_s':issued,'issued_at':story_timestamp(issued),'occurred_s':issued,'occurred_at':story_timestamp(issued),
               'received_s':received,'received_at':story_timestamp(received)}
    if content == 'X':
        message.update(kind='revoke')
        text = '撤销该目录前缀规则，保留版本记录，不删除子目录规则。'
    elif content == 'H':
        message.update(kind='pause')
        text = '明确暂停该目录前缀的回传，保留此层匹配规则。'
    else:
        message.update(kind='set',endpoint=content[0],packaging=content[1])
        text = f'完整设置：接收端{content[0]}，封装方式{PACKAGING[content[1]]}。'
    message['text'] = f'收到航天器{craft}、回传批{batch}、目录前缀{prefix}第{version}号指示；'
    message['text'] += f'签发于{story_timestamp(issued)}，接收于{story_timestamp(received)}。' + text
    return message


def build(index):
    product,rows,arrival,expected = CONFIGS[index]
    history = History()
    history.add(1,'DS7回传批B12本件净荷64 MiB，今日09:00开始本次回传，历史期间无发送义务。'
                '地面单一控制方按航天器/批次/目录前缀独立编号，指示给完整设置、明确暂停或撤销该前缀。'
                '同范围只保留已收最高版本，版本与签发时间同序，同号重发内容相同，无冲突或隐藏规则，缺号无需补链。'
                '撤销保留版本以阻止迟到旧规则复活，但该前缀退出匹配，不删除子层；更高设置可重新加入。'
                '前缀按点分隔完整段匹配，SCI.IR匹配SCI.IR.LINE和SCI.IR.CONT，不匹配SCI.IRX.CONT；'
                '*匹配全部，完整标签也匹配。只考虑本航天器/批次，取匹配段数最多的未撤销规则，*最宽。'
                '最具体规则暂停则待机，不跳过它找父层；撤销可连续回退；无匹配也待机。'
                '新消息不改当前产品身份。A/B/C三个端同等可达，原始帧/无损块封装/冗余分片封装均无损、各端都能处理。'
                '资源窗口充足，附加封装字节不影响本次任务完成，预置宏完成整件64 MiB，不拆件、不多投、不改标签。'
                '准备只检查电路及产品完整性，不发送或清副本，收信后一次选择完整业务动作。'
                '第一次合法选择执行即终结，总最多4次提交，累计3次格式错误终止；主动放弃直接结束，合法待机可完成业务。',
                event='downlink_protocol',operations=list(OPERATIONS))
    rounds = (4,12,24) if index < 6 else (4,10,18,26) if index < 12 else (4,9,15,21,27)
    for at,code in zip(rounds,rows,strict=True):
        message = _message(code,clock(f'08:{at:02d}'))
        history.add(at,message.pop('text'),occurred=message['issued_s'],received=message['received_s'],**message)
    history.add(30,'DS7已排定B12当前产品，64 MiB净荷完整在本地，尚未发送，三个接收端与封装装置均可用。',event='downlink_ready')
    pair = f'FM-C2-D3-pair{index//2+1:02d}' if index < 4 else None
    task = task_shell('FM-C2-D3',index,group=pair,background_group=pair,
                      current_input_group=f'FM-C2-D3-{product}')
    task.public = {'time_s':clock('09:00'),'craft':'DS7','batch':'B12','product':product,'payload_mib':64,'max_steps':4,
                   'instruction':f'继续处理DS7、B12的本件回传；产品标签为{product}，净荷64 MiB。请完成发送准备。',
                   'operation_menu':deepcopy(list(OPERATIONS)),
                   'state_fields':['prepared','format_errors','local_payload_mib','sent_payload_mib','transmission'],
                   'actions':ordered_options(OPERATIONS,'FM-C2-D3') + [{'action':'end','description':'放弃本次任务'}]}
    task.initial = {'prepared':False,'format_errors':0,'time_s':clock('09:00'),
                    'local_payload_mib':64,'sent_payload_mib':0,'transmission':None}
    message = _message(arrival,clock('09:01'))
    message['record_id'] = 'ARR01'
    task.world = {'arrival_time_s':clock('09:01'),'arrivals':[message],
                  'correct_operation':{'endpoint':expected[0],'packaging':expected[1]} if expected else {'standby':True}}
    task.rubric = {'score':'100 iff the actual full transfer or standby matches the most specific effective scoped prefix'}
    return history.finish(task)


class Runtime(PreparedChoiceRuntime):
    def observation(self):
        result = super().observation()
        if self.state['prepared']:
            result['instruction'] = '请选择本件的操作。'
        return result

    def submit(self,action):
        super().submit(action)
        if self.received_messages:
            self.feedback = '发送准备完成，尚未发送。收到一条地面指示。'
        if self.termination == 'completed':
            self.feedback = '操作已执行，记录已存档'
            operation = self.facts['executed_operation']
            if 'endpoint' in operation:
                self.state.update(sent_payload_mib=64,transmission=deepcopy(operation))


def _replay(messages,craft,batch,product):
    prefixes = {}
    for message in messages:
        if (message['craft'],message['batch']) != (craft,batch):
            continue
        versions = prefixes.setdefault(message['prefix'],{})
        content = {k:message[k] for k in ('kind','endpoint','packaging') if k in message}
        if message['version'] in versions and versions[message['version']] != content:
            raise ValueError('Conflicting same-version directory rule')
        versions[message['version']] = content
    matches = []
    for prefix,versions in prefixes.items():
        rule = versions[max(versions)]
        if rule['kind'] == 'revoke':
            continue
        parts = [] if prefix == '*' else prefix.split('.')
        if product.split('.')[:len(parts)] == parts:
            matches.append((len(parts),rule))
    if not matches:
        return {'standby':True}
    _,rule = max(matches,key=lambda row:row[0])
    return {'standby':True} if rule['kind'] == 'pause' else {'endpoint':rule['endpoint'],'packaging':rule['packaging']}


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'收到航天器(DS\d+)、回传批(B\d+)、目录前缀(\*|[A-Z0-9]+(?:\.[A-Z0-9]+)*)第(\d+)号指示；'
                              rf'签发于({STORY_STAMP})，接收于({STORY_STAMP})。(.*)',text)
        if header is None:
            continue
        craft,batch,prefix,version,issued,received,body = header.groups()
        message = {'craft':craft,'batch':batch,'prefix':prefix,'version':int(version),
                   'issued_s':seconds(issued),'received_s':seconds(received)}
        setting = re.fullmatch(r'完整设置：接收端([ABC])，封装方式(原始帧|无损块封装|冗余分片封装)。',body)
        if setting:
            message.update(kind='set',endpoint=setting[1],
                           packaging={'原始帧':'R','无损块封装':'L','冗余分片封装':'F'}[setting[2]])
        elif body == '撤销该目录前缀规则，保留版本记录，不删除子目录规则。':
            message.update(kind='revoke')
        elif body == '明确暂停该目录前缀的回传，保留此层匹配规则。':
            message.update(kind='pause')
        else:
            raise ValueError('Incomplete public downlink rule')
        messages.append(message)
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if not current['state']['prepared']:
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['craft'],current['batch'],current['product'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Downlink differs from the highest effective scoped directory prefix')
