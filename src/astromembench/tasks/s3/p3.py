"""FM-S3-P3: monotone custody facts and sufficient batch-specific evidence."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
STATES = {'L':'车上已系固','U':'已卸入指定架、未签收','S':'收货人已签收并归档'}
MENU = (('unload','A'),('sign','BC'),('unload','AB'),('sign','A'),('unload','C'),('sign','ABC'),
        ('unload','BC'),('sign','B'),('unload','ABC'),('sign','AC'),('unload','B'),('sign','AB'),
        ('unload','AC'),('sign','C'),('close_batch',''))
CONFIGS = (
    ('ULL',None,7,'K0',3),('ULU','ULU',8,'K1',14),('USU',None,7,'K1',12),
    ('SSS','SSS',7,'K0',15),('LLL',None,8,'K1',4),('ULU',None,8,'K1',8),
    ('LLU','LLU',7,'K0',0),('ULU','ULS',8,'K0',0),('UUL','UUU',7,'K1',8),
    ('UUU','SUU',8,'K1',5),('UUS','USS',8,'K1',3),('UUU','SSS',7,'K1',7),
    ('LUL','UUL',7,'K1',2),('LLL','LSL',8,'K0',4),('LLL','SLS',7,'K0',2),('SUL','SSS',7,'K0',13),
)


def described(vector,boxes='ABC'):
    return {box:STATES[vector['ABC'.index(box)]] for box in boxes}


def fields_text(fields):
    return '；'.join(f'箱{box}为{state}' for box,state in fields.items())


def changes(before,after,boxes='ABC'):
    operations = []
    for action,start,end in (('unload','L','U'),('sign','U','S')):
        for box in boxes:
            old,new = before['ABC'.index(box)],after['ABC'.index(box)]
            if 'LUS'.index(old) <= 'LUS'.index(start) and 'LUS'.index(new) >= 'LUS'.index(end):
                operations.append({'action':action,'box':box,'rack':'L'+box})
    return operations


def operations_text(operations):
    return '；'.join(f'{row["box"]}'+(f'实际卸至{row["rack"]}成功' if row['action'] == 'unload' else '由收货人签收并归档成功') for row in operations) or '所列接口没有新增操作'


def build(index):
    first,after,failed_order,snapshot,offset = CONFIGS[index]
    final = after or first
    mode = 'integrated' if index < 6 else 'split' if index < 12 else 'incremental'
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()

    def record(at,letter,text,**facts):
        history.add(at,ids[letter]+'：'+text,record_id=ids[letter],**facts)

    def status(at,letter,vector,*,order='W8',vehicle='本车',boxes='ABC',operations=(),intro=''):
        fields = described(vector,boxes)
        record(at,letter,f'{vehicle}/{order}：'+intro+operations_text(operations)+'；当前所列箱状态：'+fields_text(fields)+'。未报告的箱不附加状态。',
            event='custody_confirmed',order=order,vehicle=vehicle,states=fields,operations=list(operations))

    report_format = {
        'integrated':'本车使用综合清单接口，实际回执及快照列三箱状态。',
        'split':'本车使用A/B执行接口与C保管接口；实际回执分开报告A/B及C，K1的保存快照只含C，恢复显示只含A/B，不能将一份分量当成完整清单。',
        'incremental':'本车使用基线账本与成功增量接口；首批及快照列完整基线，后批仅报告实际成功操作，不附未变箱状态；失败提交只报告零执行。',
    }[mode]
    history.add(1,'当前工单W8，A/B/C三只货箱分别卸至接收架LA/LB/LC，每箱一件不可拆。目的站已到达、收货方在线、各箱可安全卸放，接口和机械正常。'
        '每箱只能依次车上已系固→卸入指定架未签收→收货人签收归档，三箱独立，W7和独立车辆Q的同名箱是其他实体。'
        '历史允许逐箱交接；故障后续作合同为：有车上箱则一次卸下全部车上箱，否则有未签收箱则一次签收全部未签收箱，否则close_batch。少选或重复已完成箱均不正确。'
        '对A/B/C/AB/AC/BC/ABC各有unload和sign，另有close_batch；当前只登记下一批作业，不执行。没有未回执的隐蔽动作，缓存不能撤销卸货或外部签收。'+report_format+
        '每份所选证据只证明其明确字段或成功增量，缓存采用原保存时刻。后续卸货撤销旧车上状态；后续签收撤销旧未签收状态，但旧卸货仍可证明已离车；已签收和已离车不会回退。'
        '卸货需证明各箱是否仍在车上；签收需精确证明哪些未签收和哪些已签；关闭需证明全部已签。不能将未引用的后继记录补成所选证据的精确后态。'
        '纯缓存不足时不构成实际进度弱证，实际旧进度或部分状态及成功增量可作弱证。'
        '提交action、所选动作所需的boxes及evidence；boxes为A/B/C无重复非空数组、顺序无关，close_batch不带boxes；evidence可null或非空数组，H01—H16重复先去重最多2种。'
        '只能交声明字段，最多3次总调用含格式错；首合法决定即结束，不能刷新实时清单，原生记忆检索不计次数。',event='custody_resume_protocol')
    status(2,'b','SSS',order='W7',operations=changes('LLL','SSS'),intro='三箱各已实际接收并装车系固，随后依次：')
    record(3,'a','本车/W8三箱分别实际接收、装车系固成功，当前三箱均车上已系固，此前无卸货或签收。',
        event='custody_confirmed',order='W8',vehicle='本车',states=described('LLL'),operations=[])
    record(4,'c','保存本车/W8的K0，原保存时间08:04，显示三箱车上已系固。',event='custody_snapshot_saved',
        order='W8',vehicle='本车',snapshot='K0',saved_s=clock('08:04'),states=described('LLL'))
    record(5,'d','本车/W8卸货和签收计划已排程，未下发执行。',event='custody_planned',order='W8',vehicle='本车')
    for at,text in ((6,'路面和站内通道正常，无箱移动。'),(7,'目的架LA/LB/LC均空且与箱对应，无箱移动。'),
        (8,'起重单元自检完成，无装卸。'),(9,'车上隔振器状态正常，无保管变化。')):
        history.add(at,text,event='custody_monitoring')
    boxes = 'AB' if mode == 'split' else 'ABC'
    status(10,'e',first,boxes=boxes,operations=changes('LLL',first,boxes))
    fields = described(first,'C' if mode == 'split' else 'ABC')
    record(11,'f','保存本车/W8的K1，原保存时间08:11，保存时实际字段：'+fields_text(fields)+'；本条是纯快照，不是装卸或签收执行回执。',
        event='custody_snapshot_saved',order='W8',vehicle='本车',snapshot='K1',saved_s=clock('08:11'),states=fields)
    status(12,'g','SSS',vehicle='Q',operations=changes('LLL','SSS'))
    for at,text in ((13,'车载时钟同步，无保管变化。'),(14,'箱体温度18℃，无装卸。'),(15,'载台指示灯检查完成，无装卸。'),
        (16,'目的架照明检查完成，无装卸。'),(17,'电源总线检查完成，无装卸。'),(18,'备件车经过，与本工单无操作关系。')):
        history.add(at,text,event='custody_monitoring')
    if after is None:
        status(19,'h','SSS',order='W7')
    elif mode == 'incremental':
        operations = changes(first,after)
        record(19,'h','本车/W8本次实际成功增量：'+operations_text(operations)+'；仅报告这些操作，不附未变箱状态。',
            event='custody_increment_confirmed',order='W8',vehicle='本车',operations=operations)
    else:
        status(19,'h',after,boxes=boxes,operations=changes(first,after,boxes))
        if mode == 'split':
            status(19,'i',after,boxes='C',operations=changes(first,after,'C'))
    history.add(20,'控制器随后只处理已列请求，无其他装卸或签收。',event='custody_log_complete')
    request = '本车/W8下一批作业指令只获受理，尚未执行，不写真实清单。'
    if mode == 'split':
        history.add(21,request,event='custody_request_accepted',order='W8',vehicle='本车')
    else:
        record(21,'i',request,event='custody_request_accepted',order='W8',vehicle='本车')
    history.add(22,'无新的保管操作，服务准备维护。',event='custody_monitoring')
    failure_fields = {} if mode == 'incremental' and failed_order == 8 else described('SSS' if failed_order == 7 else final,'ABC' if failed_order == 7 else boxes)
    record(23,'j',f'本车/W{failed_order}'+('下一条指令提交失败' if failed_order == 8 else '结束标记失败')+'，执行数0，不撤销既有成果。'+
        ('所列当前核对：'+fields_text(failure_fields)+'。' if failure_fields else '不报告指令类型或箱状态。'),
        event='custody_failed_request',order=f'W{failed_order}',vehicle='本车',executions=0,states=failure_fields)
    record(24,'k','车载任务服务故障，箱和外部签收档案未发生操作。',event='custody_service_failed')
    fields = described('LLL' if snapshot == 'K0' else first,boxes)
    saved = '08:04' if snapshot == 'K0' else '08:11'
    record(25,'l',f'读取本车/W8的{snapshot}，原保存时间{saved}，历史显示字段：'+fields_text(fields)+'；只读取缓存，不追加当前状态。',
        event='custody_snapshot_loaded',order='W8',vehicle='本车',snapshot=snapshot,saved_s=clock(saved),states=fields)
    record(26,'m','车辆Q重新载入其缓存，本车无装卸。',event='other_custody_display_loaded',vehicle='Q')
    record(27,'n','本车执行接口恢复正常，没有新的保管操作。',event='custody_interface_restored')
    record(28,'o','W7再签收计划撤回，未执行。',event='custody_plan_cancelled',order='W7',vehicle='本车')
    record(29,'p','箱温18℃，无装卸和档案改写。',event='custody_monitoring')
    history.add(30,'通信监测正常，无新操作。',event='custody_monitoring')
    task = task_shell('FM-S3-P3',index,current_input_group='FM-S3-P3')
    task.public = {'instruction':'继续本车工单W8的三箱转运任务。请提交下一批操作。','order':'W8','vehicle':'本车',
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':[{'action':action,**({'boxes':list(boxes)} if boxes else {}),
                    'description':'结束本批' if not boxes else ('批量卸货至指定接收架：' if action == 'unload' else '批量由收货人签收归档：')+'、'.join('箱'+box+'对应L'+box for box in boxes)}
                   for action,boxes in MENU]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'custody':described(final),'registered_operation':None}
    task.rubric = {'score':'correct complete batch with sufficient live field support:100; useful actual progress but insufficient:30; otherwise:0'}
    return history.finish(task)


def _custody_fields(text):
    codes = {description:code for code,description in STATES.items()}
    fields = {}
    for item in text.split('；'):
        match = re.fullmatch(r'箱([ABC])为(.+)',item)
        if not match or match[1] in fields or match[2] not in codes:
            raise ValueError('Custody fields must name each reported box and its complete state')
        fields[match[1]] = codes[match[2]]
    return fields


def _custody_operations(text,racks):
    if text == '所列接口没有新增操作':
        return {}
    fields = {}
    for item in text.split('；'):
        if match := re.fullmatch(r'([ABC])实际卸至(L[A-Z0-9]+)成功',item):
            box,rack = match.groups()
            if racks is None or racks[box] != rack or box in fields:
                raise ValueError('Successful unloading must use the public rack and precede signing')
            fields[box] = 'U'
        elif match := re.fullmatch(r'([ABC])由收货人签收并归档成功',item):
            box = match[1]
            if fields.get(box) == 'S':
                raise ValueError('A custody receipt cannot repeat successful signing')
            fields[box] = 'S'
        else:
            raise ValueError('Custody increments must report actual successful operations')
    return fields


def _custody_receipt(text,scope,racks):
    if text == scope+'三箱分别实际接收、装车系固成功，当前三箱均车上已系固，此前无卸货或签收。':
        return dict.fromkeys('ABC','L'),'actual'
    if re.fullmatch('保存'+re.escape(scope)+r'的K\d+，原保存时间\d{2}:\d{2}，显示三箱车上已系固。',text):
        return dict.fromkeys('ABC','L'),'saved'
    if match := re.fullmatch('保存'+re.escape(scope)+r'的K\d+，原保存时间\d{2}:\d{2}，保存时实际字段：(.+)；本条是纯快照，不是装卸或签收执行回执。',text):
        return _custody_fields(match[1]),'saved'
    if match := re.fullmatch('读取'+re.escape(scope)+r'的K\d+，原保存时间\d{2}:\d{2}，历史显示字段：(.+)；只读取缓存，不追加当前状态。',text):
        return _custody_fields(match[1]),'loaded'
    if not text.startswith(scope):
        return None
    body = text[len(scope):]
    if match := re.fullmatch(r'：(.+)；当前所列箱状态：(.+)。未报告的箱不附加状态。',body):
        operations = _custody_operations(match[1],racks)
        fields = _custody_fields(match[2])
        if any(fields.get(box) != state for box,state in operations.items()):
            raise ValueError('Reported custody fields must agree with actual successful operations')
        return fields,'actual'
    if match := re.fullmatch(r'本次实际成功增量：(.+)；仅报告这些操作，不附未变箱状态。',body):
        return _custody_operations(match[1],racks),'actual'
    if match := re.fullmatch(r'(?:下一条指令提交失败|结束标记失败)，执行数0，不撤销既有成果。所列当前核对：(.+)。',body):
        return _custody_fields(match[1]),'actual'
    return None


def reconstruct(history,current):
    actual,records,useful,racks = {},{},[],None
    scope = current['vehicle']+'/'+current['order']
    for text in paragraphs(history):
        if match := re.match(r'当前工单(\w+)，([ABC](?:/[ABC]){2})三只货箱分别卸至接收架(L[A-Z0-9]+(?:/L[A-Z0-9]+){2})，每箱',text):
            if match[1] != current['order']:
                continue
            boxes,destinations = (part.split('/') for part in match.groups()[1:])
            if set(boxes) != set('ABC'):
                raise ValueError('The custody protocol must bind each box to its destination rack')
            racks = dict(zip(boxes,destinations,strict=True))
        elif match := re.fullmatch(r'(H\d{2})：(.+)',text):
            if receipt := _custody_receipt(match[2],scope,racks):
                fields,kind = receipt
                if fields:
                    records[match[1]] = fields
                    # A newly saved snapshot reports its then-current fields;
                    # loading an old snapshot cannot reverse physical custody.
                    if kind != 'loaded':
                        actual.update(fields)
                    if kind == 'actual':
                        useful.append(match[1])
    supports = {}
    for identifier,fields in records.items():
        supports[identifier] = {}
        for box,state in fields.items():
            bits = [state] if state == actual[box] else []
            if state in 'US':
                bits.append('nonL')
            supports[identifier][box] = bits
    loaded = [box for box in 'ABC' if actual[box] == 'L']
    unsigned = [box for box in 'ABC' if actual[box] == 'U']
    operation = {'action':'unload','boxes':loaded} if loaded else {'action':'sign','boxes':unsigned} if unsigned else {'action':'close_batch'}
    return {'actual':actual,'supports':supports,'useful':useful,'correct_operation':operation}


def evaluate(facts,operation,references):
    if operation != facts['correct_operation'] or references is None:
        return 0
    coverage = {box:set() for box in 'ABC'}
    for identifier in references:
        for box,bits in facts['supports'].get(identifier,{}).items():
            coverage[box].update(bits)
    if operation['action'] == 'unload':
        sufficient = all(('L' if box in operation['boxes'] else 'nonL') in coverage[box] for box in 'ABC')
    elif operation['action'] == 'sign':
        sufficient = all(('U' if box in operation['boxes'] else 'S') in coverage[box] for box in 'ABC')
    else:
        sufficient = all('S' in coverage[box] for box in 'ABC')
    return 100 if sufficient else 30 if set(references)&set(facts['useful']) else 0


class Runtime(TaskRuntime):
    action_contract = ActionContract(fields=('action','boxes'),parameters={'*':{'evidence':{'type':['array','null'],'required':True,
        'items':{'type':'string','enum':list(CATALOG)},'minItems':1,'description':'null或非空H01—H16编号数组；重复先去重最多2种。boxes须无重复，顺序无关。'}}})

    def actions(self):
        return [] if self.done else super().actions()

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or not isinstance(action.get('action'),str) or action['action'] not in ('unload','sign','close_batch'):
            self.invalid()
            return
        expected_fields = {'action','evidence'} if action['action'] == 'close_batch' else {'action','boxes','evidence'}
        if set(action) != expected_fields:
            self.invalid()
            return
        operation = {'action':action['action']}
        if 'boxes' in action:
            boxes = action['boxes']
            if not isinstance(boxes,list) or not boxes or any(not isinstance(box,str) or box not in ('A','B','C') for box in boxes) or len(set(boxes)) != len(boxes):
                self.invalid()
                return
            operation['boxes'] = sorted(boxes)
        refs = action['evidence']
        if refs is not None and (not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in CATALOG for ref in refs) or len(set(refs)) > 2):
            self.invalid()
            return
        refs = None if refs is None else list(dict.fromkeys(refs))
        score = evaluate(self.task.world,operation,refs)
        self.state['registered_operation'] = deepcopy(operation)
        self.facts = {'registered_operation':operation,'references':refs}
        self.feedback = '下一批作业与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for count in (1,2):
        for refs in combinations(CATALOG,count):
            if evaluate(facts,facts['correct_operation'],refs) == 100:
                return {**deepcopy(facts['correct_operation']),'evidence':list(refs)}
    raise ValueError('The complete batch requires at most two sufficient field records')


def check_world(task,facts):
    if task.world != facts or task.initial['custody'] != {box:STATES[state] for box,state in facts['actual'].items()}:
        raise ValueError('Monotone custody and field evidence must follow public receipts rather than restored displays')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        operation = {key:deepcopy(row[key]) for key in ('action','boxes') if key in row}
        for refs in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{**operation,'evidence':refs}],evaluate(facts,operation,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
