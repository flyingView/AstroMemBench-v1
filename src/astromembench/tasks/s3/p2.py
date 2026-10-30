"""FM-S3-P2: retained sample-box decisions with native thirty-round receipts."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

STEPS = ('collect','seal','transfer','register','finish')
LABELS = ('取得指定样品并装盒','封存','转移到指定存放位','登记处理完成','结束对象任务')
FAILURES = ('未取得指定样品，盒内尚无该样品','未形成封口，已取得样品仍在未封存盒内',
            '未位移，已封存盒仍在作业位','写入未提交，盒在存放位、尚未登记',
            '结束标记未生效，档案已登记，本对象尚未结束')
CATALOG = tuple(f'E{i:02d}' for i in range(1,17))
# Target, successful operation minutes, saved snapshots, loaded snapshot,
# failed operation before/after the last success, and preserved receipt IDs.
CONFIGS = (
    ('B',(30,),(28,),'K1',None,33,(11,4)),('C',(22,),(20,),'K1',None,None,(2,)),
    ('C',(26,30),(27,),'K1',None,33,(8,12)),('A',(22,26,30),(27,),'K1',None,33,(5,4)),
    ('A',(12,16,20,24),(10,),'K1',None,None,(11,)),('C',(10,14,18,22),(15,),'K1',None,None,(9,)),
    ('A',(28,),(26,),'K1',26,None,(9,)),('B',(24,28),(22,),'K1',26,None,(6,)),
    ('C',(22,26),(23,),'K1',None,29,(13,1)),('C',(20,24,28),(18,),'K1',26,None,(3,)),
    ('B',(26,30,34),(31,),'K1',None,None,(1,)),('B',(14,18,22,26),(12,),'K1',None,29,(7,1)),
    ('A',(30,),(27,28,29),'K1',28,None,(14,)),('C',(32,36),(29,30,33),'K2',None,39,(2,6)),
    ('A',(28,32,36),(25,29,33),'K2',None,39,(15,14)),('A',(18,22,26,30),(15,23,27),'K2',28,None,(5,)),
)


def time(minute,second=0):
    return clock(f'09:{minute:02d}:{second:02d}',day=210)


def location(box):
    return 'L'+str('ABC'.index(box)+1)


def physical_state(box,stage):
    return {'sample':'S'+box if stage else None,'sealed':stage >= 2,
            'location':location(box) if stage >= 3 else '作业位','registered':stage >= 4,'ended':False}


def state_text(box,stage):
    return (f'指定样品S{box}尚未取得，盒内无该样品。',f'样品S{box}已装入{box}，等待封存。',
            f'{box}已封存，仍在作业位。',f'{box}已到{location(box)}，尚未登记完成。',
            f'{box}处理及样品档案登记完成，尚未结束本对象任务。')[stage]


def build(index):
    target,minutes,saved_minutes,loaded,before,after,preserved = CONFIGS[index]
    stage = len(minutes)
    other1,other2 = ('ABC'[('ABC'.index(target)+offset)%3] for offset in (1,2))
    entries = []

    def add(minute,second,text,*,record_id=None,**facts):
        entries.append({'at':time(minute,second),'text':text,'record_id':record_id,'facts':facts})

    for step in range(1,5):
        if step <= stage:
            add(minutes[step-1],10,f'{target}的{LABELS[step-1]}成功。'+state_text(target,step),
                record_id=f'E{preserved[0]:02d}' if step == stage else None,
                event='sample_operation_succeeded',box=target,operation=STEPS[step-1],success=True,changed=True,actual=physical_state(target,step))
        else:
            add(4+2*step,30,'温度采样完成，本轮未处理样品盒。',event='sample_monitoring')

    def fail(minute,second,step,record_id=None):
        add(minute,second,f'{target}的{LABELS[step]}失败，{FAILURES[step]}；实际没有变化。'+state_text(target,step),
            record_id=record_id,event='sample_operation_failed',box=target,operation=STEPS[step],success=False,changed=False,actual=physical_state(target,step))

    if before is not None:
        fail(before,5,stage-1)
    else:
        add(16,30,'机械臂自检完成，本轮未处理样品盒。',event='sample_monitoring')
    if after is not None:
        fail(after,10,stage,f'E{preserved[1]:02d}')
    else:
        add(18,30,'时间基准同步完成，本轮未处理样品盒。',event='sample_monitoring')
    add(3,10,f'{target}后续封存计划已制定，尚未执行。',event='sample_planned',box=target,operation='seal')
    snapshots = {}
    for position in range(3):
        if position < len(saved_minutes):
            minute = saved_minutes[position]
            captured = sum(success_minute <= minute for success_minute in minutes)
            name = f'K{position+1}'
            snapshots[name] = {'saved_s':time(minute,20),'state':physical_state(target,captured),'stage':captured,'minute':minute}
            add(minute,20,f'保存{target}快照{name}，保存时间第210日09:{minute:02d}:20；'+state_text(target,captured),
                event='sample_snapshot_saved',box=target,snapshot=name,saved_s=time(minute,20),display=physical_state(target,captured))
        else:
            add(17+2*position,30,('压力监测归档' if position == 1 else '照明检查完成')+'，本轮未处理样品盒。',event='sample_monitoring')
    snap = snapshots[loaded]
    add(48,0,f'进度服务恢复，载入{target}的{loaded}，保存时间第210日09:{snap["minute"]:02d}:20；恢复显示：'+state_text(target,snap['stage'])+
        '只读取缓存，不执行采样，不改变物理样品或已写入档案。',event='sample_snapshot_loaded',box=target,snapshot=loaded,saved_s=snap['saved_s'],display=snap['state'])
    for box,minute,steps,enabled,label in ((other1,40,stage%4+1,index in (1,5) or index >= 6,'通信检查完成'),
        (other2,42,(stage+1)%4+1,index >= 6,'温控检查完成')):
        if enabled:
            add(minute,10,box+'从取得开始依次：'+'；'.join(LABELS[step]+'成功' for step in range(steps))+'。'+state_text(box,steps),
                event='sample_operations_succeeded',box=box,operations=list(STEPS[:steps]),success=True,changed=True,actual=physical_state(box,steps))
        else:
            add(minute,30,label+'，本轮未处理样品盒。',event='sample_monitoring')
    add(4,30,f'{other1}取得S{other1}的计划已制定，尚未执行。',event='sample_planned',box=other1,operation='collect')
    add(44,30,'供电检查完成，本轮未处理样品盒。',event='sample_monitoring')
    add(50,30,'处理接口就绪，没有新的样品处理，本轮未处理样品盒。',event='sample_interface_ready')
    entries.sort(key=lambda entry:entry['at'])
    remaining = iter(identifier for identifier in CATALOG if identifier not in {f'E{number:02d}' for number in preserved})
    for entry in entries:
        if entry['record_id'] is None:
            entry['record_id'] = next(remaining)
    entries.append({'at':time(45),'record_id':None,'text':'进度服务故障，开始恢复，没有新的样品处理。','facts':{'event':'sample_progress_service_failed'}})
    entries.sort(key=lambda entry:entry['at'])
    history = History(times=[time(1),time(2),*[entry['at'] for entry in entries],*[time(50,second) for second in range(31,42)]])
    history.add(1,'样品盒A、B、C分别处理指定样品SA、SB、SC，固定存放位分别L1、L2、L3。'
        '流程为取得指定样品并装盒→封存→转移指定存放位→登记完成→结束本对象任务。按流程执行，不跳步；已封存不能再次封存，其他已完成步骤也不应重复。'
        '计划、请求和成功回执是不同事件；明确失败且无实际变化时，该步可重试。后续步骤成功表示前置条件已满足。'
        '快照只记录保存时状态；读取快照不执行采样，不改变物理样品，也不删除成功写入的样品档案。'
        '登记写入样品档案，与调度界面的进度缓存不同；进度服务故障不撤销封存、转移和档案登记。'
        '正式测试只决定下一步，设备与操作接口已经恢复正常。提交下一操作时，同时交一个动作及一至两个事件编号，或明确提交没有可用依据。',event='sample_continuation_protocol')
    history.add(2,'三盒均空，指定样品尚未取得。',event='sample_boxes_initialized',boxes={box:physical_state(box,0) for box in 'ABC'})
    for at,entry in enumerate(entries,3):
        identifier = entry['record_id']
        history.add(at,(identifier+'：' if identifier else '')+entry['text'],record_id=identifier,
            occurred=entry['at'],received=entry['at'],**entry['facts'])
    for at,second in enumerate(range(31,42),20):
        history.add(at,'运行监测正常，没有新的样品处理或档案改写。',occurred=time(50,second),received=time(50,second),event='sample_monitoring')
    task = task_shell('FM-S3-P2',index,current_input_group=f'FM-S3-P2-{target}')
    task.public = {'instruction':f'继续完成样品盒{target}的处理任务。请提交下一项操作。','box':target,
        'time_s':time(51),'max_steps':3,'record_catalog':list(CATALOG),
        'evidence_format':'一至两个不同记录编号的列表；没有可用依据时填写null。重复编号只算一条。',
        'actions':[{'action':action,'box':box,'description':label} for box in 'ABC'
                   for action,label in zip(STEPS,(f'取得S{box}并装入{box}',f'封存{box}',f'{box}转移{location(box)}',f'登记{box}处理完成',f'结束{box}任务'))]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'boxes':deepcopy(task.world['boxes'])}
    task.rubric = {'score':'correct with sufficient record 100; correct with existing insufficient record 20; otherwise 0'}
    task.design['scoring_version'] = 'm16/4'
    return history.finish(task)


def _retained_state(box,stage,objects):
    sample,destination = objects[box]['sample'],objects[box]['location']
    return {'sample':sample if stage else None,'sealed':stage >= 2,
            'location':destination if stage >= 3 else '作业位','registered':stage >= 4,'ended':False}


def _sample_receipt(text,objects):
    if match := re.fullmatch(r'([ABC])的(.+)成功。(.+)',text):
        box,label,state_text = match.groups()
        if label not in LABELS[:4]:
            raise ValueError('A successful sample receipt must name an actual processing step')
        stage = LABELS.index(label)+1
    elif match := re.fullmatch(r'([ABC])的(.+)失败，(.+)；实际没有变化。(.+)',text):
        box,label,reason,state_text = match.groups()
        if label not in LABELS or reason != FAILURES[LABELS.index(label)]:
            raise ValueError('An unchanged failure must match the reported sample operation')
        stage = LABELS.index(label)
    elif match := re.fullmatch(r'([ABC])从取得开始依次：(.+)。(.+)',text):
        box,steps,state_text = match.groups()
        operations = steps.split('；')
        stage = len(operations)
        if not 1 <= stage <= 4 or operations != [label+'成功' for label in LABELS[:stage]]:
            raise ValueError('A combined sample receipt must report its complete successful prefix')
    else:
        return None
    if objects is None:
        raise ValueError('Sample receipts require the public sample and destination assignments')
    sample,destination = objects[box]['sample'],objects[box]['location']
    expected = (f'指定样品{sample}尚未取得，盒内无该样品。',f'样品{sample}已装入{box}，等待封存。',
        f'{box}已封存，仍在作业位。',f'{box}已到{destination}，尚未登记完成。',
        f'{box}处理及样品档案登记完成，尚未结束本对象任务。')[stage]
    if state_text != expected:
        raise ValueError('The retained sample state must agree with the operation and public object binding')
    return box,_retained_state(box,stage,objects)


def reconstruct(history,current):
    boxes,receipts,objects = {},{},None
    for text in paragraphs(history):
        if match := re.match(r'样品盒([ABC](?:、[ABC]){2})分别处理指定样品(S[A-Z0-9]+(?:、S[A-Z0-9]+){2})，'
                             r'固定存放位分别(L\d+(?:、L\d+){2})。',text):
            names,samples,destinations = (part.split('、') for part in match.groups())
            if set(names) != set('ABC'):
                raise ValueError('The sample protocol must bind each of the three boxes once')
            objects = {box:{'sample':sample,'location':destination} for box,sample,destination in zip(names,samples,destinations,strict=True)}
        elif text == '三盒均空，指定样品尚未取得。':
            if objects is None:
                raise ValueError('Initial boxes require the public sample and destination assignments')
            boxes = {box:_retained_state(box,0,objects) for box in objects}
        elif match := re.fullmatch(r'(E\d{2})：(.+)',text):
            if receipt := _sample_receipt(match[2],objects):
                box,state = receipt
                boxes[box] = state
                if box == current['box']:
                    receipts[match[1]] = deepcopy(state)
    actual = boxes[current['box']]
    stage = int(actual['sample'] is not None)+int(actual['sealed'])+int(actual['location'] == objects[current['box']]['location'])+int(actual['registered'])
    return {'boxes':boxes,'correct_operation':{'action':STEPS[stage],'box':current['box']},
            'sufficient_evidence':[identifier for identifier,state in receipts.items() if state == actual]}


def evaluate(facts,operation,references):
    return (100 if set(references)&set(facts['sufficient_evidence']) else 20) if operation == facts['correct_operation'] and references else 0


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action','box'),{'*':{'evidence':{'required':True,'type':'array or null',
        'description':'一至两个不同的 E01–E16 记录编号；没有可用依据时必须填写 null，不能省略此字段。'}}})

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','box','evidence'}:
            self.invalid()
            return
        operation = {key:action[key] for key in ('action','box')}
        if not any(all(option[key] == operation[key] for key in operation) for option in self.actions()):
            self.invalid()
            return
        evidence = action['evidence']
        if evidence is not None and (not isinstance(evidence,list) or not evidence or any(not isinstance(value,str) or value not in CATALOG for value in evidence) or len(set(evidence)) > 2):
            self.invalid()
            return
        sufficient = bool(evidence and set(evidence)&set(self.task.world['sufficient_evidence']))
        score = evaluate(self.task.world,operation,evidence)
        self.facts.update(submitted_operation=deepcopy(operation),sufficient_evidence=sufficient)
        self.feedback = '下一项操作已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    return {**facts['correct_operation'],'evidence':[facts['sufficient_evidence'][0]]}


def check_world(task,facts):
    if task.world != facts or task.initial != {'boxes':facts['boxes']}:
        raise ValueError('Actual receipts determine physical sample progress; display snapshots cannot roll it back')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        operation = {key:row[key] for key in ('action','box')}
        for references in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{**operation,'evidence':references}],evaluate(facts,operation,references)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
