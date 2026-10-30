"""FM-C2-D2: complete scoped instructions with the specified native clock/menu."""
from copy import deepcopy
import re

from ..common import History, clock, round_times, task_shell
from ..prepared import audit_decision_cases as audit_cases
from ..prose import STORY_STAMP, paragraphs, record_paragraphs, seconds
from ...environment import SingleChoiceRuntime
from ...schema import story_timestamp

CONFIGS = (
    ('same',4,'窄1',3,'宽2','窄1'),
    ('same',2,'窄1',3,'宽2','宽2'),
    ('same',4,'谱1',3,'窄3','谱1'),
    ('same',2,'谱1',3,'窄3','窄3'),
    ('same',4,'宽1',3,'停','宽1'),
    ('same',2,'宽1',3,'停','停'),
    ('same',6,'停',5,'谱1','停'),
    ('same',4,'停',5,'谱1','谱1'),
    ('cycle',2,'宽3',12,'窄3','宽3'),
    ('cycle',3,'谱3',12,'窄3','谱3'),
    ('target',3,'窄3',9,'谱2','窄3'),
    ('target',4,'停',9,'谱2','停'),
    ('same',6,'窄1',5,'停','窄1'),
    ('same',4,'窄1',5,'停','停'),
    ('cycle',2,'宽1',12,'谱3','宽1'),
    ('cycle',3,'停',12,'谱3','停'),
)
MENUS = (
    ('窄2','宽3','宽2','窄3','宽1','谱2','窄1','停','谱3','谱1'),
    ('宽3','窄3','窄2','宽2','谱3','宽1','停','谱2','窄1','谱1'),
    ('谱2','谱3','窄2','停','宽2','宽1','窄3','宽3','窄1','谱1'),
    ('宽1','宽2','窄1','窄2','停','谱3','宽3','窄3','谱1','谱2'),
    ('谱3','窄3','窄2','谱1','宽2','宽3','停','谱2','窄1','宽1'),
    ('窄2','谱3','宽2','窄3','窄1','谱1','宽1','宽3','谱2','停'),
    ('窄3','宽2','宽3','窄2','窄1','宽1','谱1','谱2','停','谱3'),
    ('宽1','停','谱1','谱2','窄2','谱3','宽3','宽2','窄3','窄1'),
)
MODES = {'宽':'宽幅成像','窄':'窄幅成像','谱':'近红外光谱'}


def _operation(code):
    return {'mode':'standby','configuration':None} if code == '停' else {'mode':MODES[code[0]],'configuration':int(code[1])}


def _description(operation):
    return '保持待机，不启动本次观测' if operation['mode'] == 'standby' else f"{operation['mode']}，配置{operation['configuration']}"


def _message(target,cycle,version,code,issued,received):
    operation = _operation(code)
    return {'event':'science_instruction','target':target,'cycle':cycle,'version':version,'operation':operation,
            'issued_s':issued,'issued_at':story_timestamp(issued),
            'occurred_s':issued,'occurred_at':story_timestamp(issued),
            'received_s':received,'received_at':story_timestamp(received),
            'text':f'地面指示：目标{target}，周期{cycle}，版本V{version:02d}；签发于{story_timestamp(issued)}，'
                   f'接收于{story_timestamp(received)}；完整操作为{_description(operation)}。'}


def build(index):
    kind,old_version,old_operation,new_version,new_operation,expected = CONFIGS[index]
    old_issued,old_received = ('10:40','10:55') if kind == 'same' and old_version > new_version else ('10:00','10:10')
    anchors = {1:clock('07:59',118 if index >= 12 else 120),8:clock('08:10'),10:clock('08:20'),
               13:clock('09:10'),15:clock('09:40'),19:clock(old_received),24:clock('11:25'),27:clock('11:30'),30:clock('12:00')}
    if index >= 12:
        anchors.update({3:clock('08:10',118),5:clock('08:10',119)})
    history = History(times=round_times(anchors))
    history.add(1,'同一地面控制方的指示包含目标、周期、版本、签发/接收时间和完整操作。'
                '同目标同周期仅以已收到的最高版本为准，完整替换不拼接；版本与签发时间同序，接收可乱序。'
                '不同目标/周期不能比较版本，新周期从V01开始。无隐藏指示，同范围同号无冲突。'
                '新消息不改变当前被分配的目标/周期；已经完成的历史采集不是当前任务许可。'
                '宽幅成像/窄幅成像/近红外光谱各有配置1/2/3，另可保持待机，全部预装程序正常可执行。'
                '当前准备后收到指示，再一次选择完整模式/配置；首个有效选择终结，错误选择不重答。'
                '全题最多4次环境提交，累计第三次格式错误当次终止；准备不清零格式计数。'
                'end立即放弃；有效选择保持待机可完成业务，两者不同。准备/end仅含action，'
                'select仅含action和option，不补零的字符串编号1—10；只复制菜单arguments，不另填模式、配置或理由。',
                event='science_protocol')

    def add(at,target,cycle,version,code,issued,received):
        message = _message(target,cycle,version,code,issued,received)
        history.add(at,message.pop('text'),occurred=issued,received=received,**message)

    if index >= 12:
        add(3,'N17','Q06',20,'宽3',clock('08:00',118),clock('08:10',118))
        add(5,'N17','Q07',11 if kind == 'cycle' else 20,'宽1',clock('08:00',119),clock('08:10',119))
    add(8,'N17','Q08',1,'谱3',clock('08:00'),clock('08:10'))
    history.add(10,'N17/Q08按当时指示完成近红外光谱配置3采集；这不是当前待执行的一次采集。',
                event='science_completed',target='N17',cycle='Q08',operation=_operation('谱3'))
    if index >= 6 and old_version > 2:
        add(13,'N17','Q08',2,'停',clock('09:00'),clock('09:10'))
    if index >= 12:
        add(15,'S04','Q08',20,'窄3',clock('09:25'),clock('09:40'))
    add(19,'N17','Q08',old_version,old_operation,clock(old_issued),clock(old_received))
    if index >= 6:
        add(24,'R08','Q08',8 if kind == 'target' else 9,'谱2',clock('11:00' if kind == 'target' else '11:10'),clock('11:25'))
        history.add(27,'R08/Q08已完成近红外光谱配置2采集。',event='science_completed',target='R08',cycle='Q08',operation=_operation('谱2'))
    history.add(30,'N17/Q08当前任务尚未开始本次采集，载荷处于待机。',event='science_ready')
    pair = f'FM-C2-D2-pair{index//2+1:02d}'
    task = task_shell('FM-C2-D2',index,group=pair,background_group=pair,current_input_group=pair)
    task.public = {'time_s':clock('12:00'),'target':'N17','cycle':'Q08','max_steps':4,
                   'instruction':'继续处理N17在Q08周期的本次科学观测任务。当前载荷处于待机状态，请先完成观测准备。',
                   'state_fields':['phase','format_attempts','equipment'],
                   'actions':[{'action':'select','option':str(number),'operation':_operation(code),
                               'description':_description(_operation(code))} for number,code in enumerate(MENUS[index//2],1)]}
    task.initial = {'phase':'preparation','format_attempts':0,'equipment':'待机','time_s':clock('12:00')}
    target,cycle = ('R08','Q08') if kind == 'target' else ('N17','Q07') if kind == 'cycle' else ('N17','Q08')
    issued = clock('11:10') if kind == 'target' else clock('10:20',119 if kind == 'cycle' else 120)
    arrival = _message(target,cycle,new_version,new_operation,issued,clock('12:01'))
    arrival['record_id'] = 'ARR01'
    task.world = {'arrivals':[arrival],'correct_operation':_operation(expected)}
    task.rubric = {'score':'100 iff the executed complete mode/configuration matches the highest received scoped version'}
    return history.finish(task)


class Runtime(SingleChoiceRuntime):
    def __init__(self,task):
        super().__init__(task)
        self.received_messages = []

    def actions(self):
        if self.done:
            return []
        return [{'action':'prepare','description':'完成观测准备'}] if self.state['phase'] == 'preparation' else super().actions()

    def observation(self):
        result = super().observation()
        result.update(time_s=self.state['time_s'],current_time=story_timestamp(self.state['time_s']))
        if self.state['phase'] == 'decision':
            result['instruction'] = '请选择N17在Q08周期本次任务的操作。'
            result['received_messages'] = deepcopy(self.received_messages)
        return result

    def invalid(self):
        super().invalid()
        self.state['format_attempts'] += 1
        if self.state['format_attempts'] == 3:
            self.end('format_limit')

    def submit(self,action):
        if action == {'action':'end'}:
            return super().submit(action)
        if self.state['phase'] == 'preparation':
            if action != {'action':'prepare'}:
                self.invalid()
                return
            self.state.update(phase='decision',time_s=clock('12:01'))
            self.received_messages = deepcopy(self.task.world['arrivals'])
            self.feedback = '观测准备完成，设备状态正常，尚未启动采集。接收到一条地面指示。'
            return
        super().submit(action)


def _replay(messages,target,cycle):
    versions = {}
    for message in messages:
        if (message['target'],message['cycle']) != (target,cycle):
            continue
        if message['version'] in versions and versions[message['version']] != message['operation']:
            raise ValueError('Conflicting same-version science instructions')
        versions[message['version']] = message['operation']
    return deepcopy(versions[max(versions)])


def _instructions(texts):
    messages = []
    for text in texts:
        header = re.fullmatch(r'地面指示：目标([A-Z]\d+)，周期(Q\d+)，版本V(\d+)；'
                              rf'签发于({STORY_STAMP})，接收于({STORY_STAMP})；完整操作为(.*)。',text)
        if header is None:
            continue
        target,cycle,version,issued,received,body = header.groups()
        operation = re.fullmatch(r'(宽幅成像|窄幅成像|近红外光谱)，配置([123])',body)
        if operation:
            operation = {'mode':operation[1],'configuration':int(operation[2])}
        elif body == '保持待机，不启动本次观测':
            operation = {'mode':'standby','configuration':None}
        else:
            raise ValueError('Incomplete public science instruction')
        messages.append({'target':target,'cycle':cycle,'version':int(version),'operation':operation,
                         'issued_s':seconds(issued),'received_s':seconds(received)})
    return messages


def reconstruct(history,current):
    return {'messages':_instructions(paragraphs(history))}


def next_action(facts,current):
    if current['state']['phase'] == 'preparation':
        return {'action':'prepare'}
    facts['messages'].extend(_instructions(record_paragraphs(current.get('received_messages',[]))))
    decision = _replay(facts['messages'],current['target'],current['cycle'])
    facts['decision'] = decision
    return next(row['arguments'] for row in current['actions'] if row.get('details',{}).get('operation') == decision)


def check_world(task,facts):
    if facts['decision'] != task.world['correct_operation']:
        raise ValueError('Science decision differs from the highest received scoped version')
