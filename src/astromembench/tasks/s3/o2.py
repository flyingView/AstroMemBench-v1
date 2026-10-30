"""FM-S3-O2: dispatch the largest current wave across two exclusive arms."""
from copy import deepcopy
from itertools import combinations, combinations_with_replacement
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
STEPS = ('remove','install','torque')
MENU = (('remove','A'),('install','C'),('torque','B'),('remove','C'),('install','A'),('torque','C'),
        ('remove','B'),('install','B'),('torque','A'),('integrated_test',None),('close_repair',None))
CONFIGS = (
    ('000',False,'B','K1',8),('003',False,'C','K0',6),('330',False,'C','K1',6),
    ('333',True,'A','K0',1),('333',True,'C','K1',7),('333',True,'B','K0',12),
    ('100',False,'A','K0',2),('123',False,'C','K0',9),('332',False,'C','K0',10),
    ('331',False,'C','K1',8),('333',False,'C','K1',10),('333',False,'C','K1',5),
    ('001',False,'C','K0',7),('120',False,'B','K1',14),('231',False,'B','K0',5),('222',False,'B','K1',4),
)


def atomic(action,slot=None):
    return {'action':action,**({'slot':slot} if slot else {})}


def slot_state(slot,stage):
    return {'old_part':'O'+slot,'new_part':'N'+slot,'old_location':'插槽'+slot if stage == 0 else '回收位R'+slot,
            'new_location':'备件位S'+slot if stage < 2 else '插槽'+slot,'new_torqued':stage == 3}


def fields_text(fields):
    return '；'.join(f'槽{slot}：旧件{state["old_part"]}位于{state["old_location"]}，新件{state["new_part"]}位于{state["new_location"]}，'+
        ('新件已紧固' if state['new_torqued'] else '新件未紧固') for slot,state in fields.items())


def operation_text(operation):
    action,slot = operation['action'],operation.get('slot')
    if slot:
        return {'remove':f'拆下O{slot}并送至回收位R{slot}',
                'install':f'把唯一新件N{slot}装入插槽{slot}',
                'torque':f'紧固插槽{slot}中的N{slot}'}[action]
    return '整机试车并独立归档结果' if action == 'integrated_test' else '关闭维修工单'


def build(index):
    vector,tested,failed_slot,loaded,offset = CONFIGS[index]
    final = dict(zip('ABC',map(int,vector),strict=True))
    prior = {slot:max(stage-1,0) for slot,stage in final.items()}
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()

    def record(at,letter,text,**facts):
        history.add(at,ids[letter]+'：'+text,record_id=ids[letter],**facts)

    def progress_record(at,letter,before,after,slots='ABC',*,machine='本机',order='W8',test_completed=False):
        operations = [atomic(STEPS[step],slot) for slot in slots for step in range(before[slot],after[slot])]
        text = '；'.join(slot+'：'+('、'.join(operation_text(op)+'成功' for op in operations if op['slot'] == slot) or '无新部件动作，核对当前实体状态') for slot in slots)
        fields = {slot:slot_state(slot,after[slot]) for slot in slots}
        record(at,letter,f'{machine}/{order}：按槽顺序在不同历史波次执行。'+text+'；所列槽完整实体状态：'+fields_text(fields)+
            ('；整机试车成功并归档。' if test_completed else '；没有产生本轮试车结果。'),event='repair_progress',machine=machine,order=order,
            slot_states=fields,operations=operations,test_completed=test_completed)

    def snapshot(at,letter,name,stages,saved,*,load=False):
        fields = {slot:slot_state(slot,stage) for slot,stage in stages.items()}
        record(at,letter,('恢复' if load else '保存')+f'本机/W8快照{name}，原保存时间{saved}；显示字段：'+fields_text(fields)+
            '；当时尚未试车。只读取或保存显示，不执行机械动作、不倒撤实体或独立试车档案。',event='repair_snapshot_loaded' if load else 'repair_snapshot_saved',
            machine='本机',order='W8',snapshot=name,saved_s=clock(saved),slot_states=fields,test_completed=False)

    history.add(1,'W8三个独立插槽A/B/C各有唯一旧件OA/OB/OC与新件NA/NB/NC。每槽依次拆旧入对应回收位、装新就位、紧固；旧件不复装，工序不跳步、不重做，实体进度不回退。'
        '三槽全部紧固才可整机试车；成功结果永久独立归档，随后关闭W8。W7及整机Q是另一套实体。界面故障及快照读取不回滚实体或试车档案。'
        '甲臂固定负责A/B，乙臂固定负责C，两臂均正常空闲。每当前波次每臂最多一项，不可用数组先后把同臂双派解释为串行；两臂可同时推进。'
        '当前目标是本波次最大可推进份额，不优化后续工时或能源。能源、隔离、型号及工具安全保障，全部11原子操作始终公开。'
        '试车/关闭为整机独占操作，必须单独发单。任一重复、跳步、同臂冲突或整机混派使整波业务不成立；合法少派保留所推进份额。'
        '实际成功、明确无变化失败、只受理请求不同；真实保存且字段仍正确的快照可证明当前分量，过时缓存不能证明当前进度。实际旧进度可作相关弱证，仅涉及别槽的回执不能支持本槽。'
        '试车未完成来自封闭历史，不额外要求第三条证据；关闭需要真实完成结果。当前只登记原始结构化分派，不驱动部件或执行试车，不能查询实时进度。'
        '提交action=dispatch、operations和evidence。operations含1—2个原子操作：单槽对象精确含action及slot，整机对象只含action。证据为null或非空H01—H16数组，重复先去重最多2种。'
        '仅接受声明字段，3次总调用含格式错；首格式合法即终局，不可改答；原生记忆检索不计次数。',event='repair_wave_protocol')
    zero = dict.fromkeys('ABC',0)
    record(2,'a','本机/W8三槽旧件均在位、未拆，各唯一新件在独立备件位，本轮未生成试车结果。',
        event='repair_progress',machine='本机',order='W8',slot_states={slot:slot_state(slot,0) for slot in 'ABC'},operations=[],test_completed=False)
    record(3,'b','W7三槽曾依次拆下其当轮旧件、装上其当轮新件、紧固，整机试车成功并已关闭；是另一轮部件，W8尚未开始换件。',
        event='old_repair_completed',machine='本机',order='W7')
    snapshot(4,'c','K0',zero,'08:04')
    record(5,'d','W8全部换件及试车工序已排入计划，尚未下发。',event='repair_planned')
    history.add(6,'固定隔离状态正常，无拆装或试车。',event='repair_monitoring')
    history.add(7,'备件型号和旧件身份复核正常，无拆装。',event='repair_monitoring')
    progress_record(8,'e',zero,prior)
    snapshot(9,'f','K1',prior,'08:09')
    history.add(10,'工具柜整理，无新部件操作。',event='repair_monitoring')
    history.add(11,'通讯时间同步，无拆装。',event='repair_monitoring')
    progress_record(12,'g',prior,final,'AB')
    progress_record(13,'h',zero,dict.fromkeys('ABC',3),machine='Q',test_completed=True)
    history.add(14,'照明校正，无部件操作。',event='repair_monitoring')
    progress_record(15,'i',prior,final,'C')
    history.add(16,'备件位封签复核，无拆装。',event='repair_monitoring')
    next_name = operation_text(atomic(STEPS[final[failed_slot]],failed_slot)) if final[failed_slot] < 3 else f'{failed_slot}完工标签归档'
    record(17,'j',next_name+'请求只获受理，尚未执行。',event='repair_request_accepted',machine='本机',order='W8',slot=failed_slot)
    record(18,'k',f'本机/W8的{next_name}请求失败，执行数0；该槽实际实体状态仍为'+fields_text({failed_slot:slot_state(failed_slot,final[failed_slot])})+
        '；其余槽无动作，没有新试车结果。',event='repair_progress',machine='本机',order='W8',slot_states={failed_slot:slot_state(failed_slot,final[failed_slot])},operations=[],executions=0,test_completed=False)
    history.add(19,'仅有已列操作，此后直到08:22没有拆装、紧固或试车。',event='repair_log_complete')
    record(20,'l','W7旧工单恢复缓存，显示该轮三槽已紧固且试车成功；不是W8。',event='old_repair_display_loaded',machine='本机',order='W7')
    record(21,'m','本机/W8整机试车请求进入队列，未执行。',event='repair_test_queued',machine='本机',order='W8')
    record(22,'n','本机/W8整机试车实际完成并成功，结果已独立归档。' if tested else '本机/W8试车队列请求提交失败，执行数0，本轮没有产生试车结果，不报告机械分量。',
        event='repair_test_result',machine='本机',order='W8',test_completed=tested,executions=int(tested))
    history.add(23,'无新部件动作、无试车。',event='repair_monitoring')
    record(24,'o','工单界面服务故障，未执行机械动作或档案删除。',event='repair_display_failed')
    snapshot(25,'p',loaded,zero if loaded == 'K0' else prior,'08:04' if loaded == 'K0' else '08:09',load=True)
    for at,text in ((26,'机械及提交接口恢复正常，无新工序。'),(27,'工具电源监测正常，无新工序。'),
        (28,'接口日志归档，无新工序。'),(29,'未下发新拆装、紧固或试车。'),(30,'全部执行器保持静止，无档案改写。')):
        history.add(at,text,event='repair_monitoring')
    task = task_shell('FM-S3-O2',index,current_input_group='FM-S3-O2')
    task.public = {'instruction':'继续整机W8维修任务。甲臂负责A/B，乙臂负责C，均空闲。提交一个控制波次的作业分派，尽量推进当前可做工序；可将所列原子操作组成1—2项operations。',
        'machine':'本机','order':'W8','arms':{'甲臂':['A','B'],'乙臂':['C']},'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':[{'action':'dispatch','operations':[atomic(action,slot)],'description':'本机/W8：'+operation_text(atomic(action,slot))} for action,slot in MENU]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'slot_states':{slot:slot_state(slot,stage) for slot,stage in final.items()},'test_completed':tested,'registered_operations':None}
    task.rubric = {'score':'valid wave: sum of per-operation sufficient100/related-actual30/none0 divided by maximum concurrent progress; any business conflict:0'}
    return history.finish(task)


def stage_of(state):
    return 3 if state['new_torqued'] else 2 if state['new_location'].startswith('插槽') else 1 if state['old_location'].startswith('回收位') else 0


def _repair_fields(text,components):
    states = {}
    for item in text.split('；'):
        match = re.fullmatch(r'槽([ABC])：旧件(\w+)位于(插槽[ABC]|回收位\w+)，新件(\w+)位于(插槽[ABC]|备件位\w+)，新件(已|未)紧固',item)
        if not match:
            raise ValueError('Repair fields must describe each reported slot and both physical parts')
        slot,old,old_location,new,new_location,torqued = match.groups()
        if slot in states or components.get(slot) != (old,new):
            raise ValueError('Repair parts must match the public slot assignments')
        old_installed,new_installed = old_location.startswith('插槽'),new_location.startswith('插槽')
        if ((old_installed and old_location != '插槽'+slot) or (new_installed and new_location != '插槽'+slot)
                or old_installed and new_installed or torqued == '已' and not new_installed):
            raise ValueError('Repair locations and tightening must describe a reachable physical slot')
        states[slot] = {'old_part':old,'new_part':new,'old_location':old_location,'new_location':new_location,'new_torqued':torqued == '已'}
    return dict(sorted(states.items()))


def _repair_steps(text,states):
    reported = set()
    for entry in text.split('；'):
        match = re.fullmatch(r'([ABC])：(.+)',entry)
        if not match or match[1] not in states or match[1] in reported:
            raise ValueError('Each repair operation must belong to its reported slot')
        slot,operations = match.groups()
        reported.add(slot)
        state = states[slot]
        if operations == '无新部件动作，核对当前实体状态':
            continue
        steps = []
        for operation in operations.split('、'):
            if operation == f'拆下{state["old_part"]}并送至{state["old_location"]}成功' and state['old_location'].startswith('回收位'):
                steps.append(1)
            elif operation == f'把唯一新件{state["new_part"]}装入插槽{slot}成功' and state['new_location'] == '插槽'+slot:
                steps.append(2)
            elif operation == f'紧固插槽{slot}中的{state["new_part"]}成功' and state['new_torqued']:
                steps.append(3)
            else:
                raise ValueError('Successful repair operations must agree with parts and physical state')
        end = stage_of(state)
        if steps != list(range(end-len(steps)+1,end+1)):
            raise ValueError('A repair receipt must preserve the successful operation order')
    if reported != set(states):
        raise ValueError('A full repair receipt must account for its listed slots')


def _repair_record(text,scope,components):
    if text == scope+'三槽旧件均在位、未拆，各唯一新件在独立备件位，本轮未生成试车结果。':
        return dict.fromkeys('ABC',0),False,True
    if text == scope+'整机试车实际完成并成功，结果已独立归档。':
        return dict.fromkeys('ABC',3),True,True
    if text == scope+'试车队列请求提交失败，执行数0，本轮没有产生试车结果，不报告机械分量。':
        return {},False,True
    if match := re.fullmatch(r'(?:保存|恢复)'+re.escape(scope)+r'快照K\d+，原保存时间\d{2}:\d{2}；显示字段：(.+)；当时尚未试车。只读取或保存显示，不执行机械动作、不倒撤实体或独立试车档案。',text):
        return {slot:stage_of(state) for slot,state in _repair_fields(match[1],components).items()},False,False
    if not text.startswith(scope):
        return None
    body = text[len(scope):]
    if match := re.fullmatch(r'：按槽顺序在不同历史波次执行。(.+)；所列槽完整实体状态：(.+)；(整机试车成功并归档|没有产生本轮试车结果)。',body):
        states = _repair_fields(match[2],components)
        _repair_steps(match[1],states)
        stages = {slot:stage_of(state) for slot,state in states.items()}
        tested = match[3] == '整机试车成功并归档'
        if tested and stages != dict.fromkeys('ABC',3):
            raise ValueError('Successful integrated testing requires all three tightened slots')
        return stages,tested,True
    if match := re.fullmatch(r'的(.+)请求失败，执行数0；该槽实际实体状态仍为(.+)；其余槽无动作，没有新试车结果。',body):
        states = _repair_fields(match[2],components)
        if len(states) != 1:
            raise ValueError('A single-slot failure must report only its own physical state')
        slot,state = next(iter(states.items()))
        stage = stage_of(state)
        request = match[1]
        expected = (rf'拆下{re.escape(state["old_part"])}并送至回收位\w+',
            re.escape(f'把唯一新件{state["new_part"]}装入插槽{slot}'),
            re.escape(f'紧固插槽{slot}中的{state["new_part"]}'),re.escape(f'{slot}完工标签归档'))[stage]
        if not re.fullmatch(expected,request):
            raise ValueError('A failed repair request must match its unchanged slot state')
        return {slot:stage},False,True
    return None


def reconstruct(history,current):
    stages,test_completed,records = {},False,{}
    components = {}
    scope = current['machine']+'/'+current['order']
    for text in paragraphs(history):
        if match := re.match(r'(W\d+)三个独立插槽([ABC](?:/[ABC]){2})各有唯一旧件(\w+(?:/\w+){2})与新件(\w+(?:/\w+){2})。',text):
            if match[1] != current['order']:
                continue
            slots,old,new = (part.split('/') for part in match.groups()[1:])
            if set(slots) != set('ABC'):
                raise ValueError('The repair protocol must bind each of the three slots')
            components = {slot:(prior,replacement) for slot,prior,replacement in zip(slots,old,new,strict=True)}
        elif match := re.fullmatch(r'(H\d{2})：(.+)',text):
            if record := _repair_record(match[2],scope,components):
                fields,tested,actual = record
                if actual:
                    stages.update(fields)
                    test_completed = test_completed or tested
                records[match[1]] = {'stages':fields,'test_completed':tested,'actual':actual}
    evidence = {identifier:{'coverage':[slot for slot,value in entry['stages'].items() if value == stages[slot]],
        'completed':entry['test_completed'] and test_completed,'related':list(entry['stages']) if entry['actual'] else [],'actual':entry['actual']}
        for identifier,entry in records.items()}
    available = [atomic(STEPS[stages[slot]],slot) for slot in 'ABC' if stages[slot] < 3]
    maximum = int(any(stages[slot] < 3 for slot in 'AB'))+int(stages['C'] < 3)
    if not maximum:
        maximum = 1
        available = [atomic('close_repair' if test_completed else 'integrated_test')]
    return {'stages':stages,'test_completed':test_completed,'evidence':evidence,'available':available,'maximum':maximum}


def evaluate(facts,operations,refs):
    if any(operation not in facts['available'] for operation in operations):
        return 0
    arms = ['甲臂' if operation.get('slot') in ('A','B') else '乙臂' if operation.get('slot') == 'C' else '整机' for operation in operations]
    if len(set(arms)) != len(arms) or '整机' in arms and len(arms) != 1:
        return 0
    proofs = [facts['evidence'][identifier] for identifier in set(refs or []) if identifier in facts['evidence']]
    coverage = {slot for proof in proofs for slot in proof['coverage']}
    points = 0
    for operation in operations:
        slot = operation.get('slot')
        sufficient = slot in coverage if slot else any(proof['completed'] for proof in proofs) if operation['action'] == 'close_repair' else coverage == set('ABC')
        related = any(slot in proof['related'] for proof in proofs) if slot else any(proof['actual'] for proof in proofs)
        points += 100 if sufficient else 30 if related else 0
    return points/facts['maximum']


class Runtime(TaskRuntime):
    action_contract = ActionContract(fields=('action',),parameters={'dispatch':{
        'operations':{'required':True,'type':'array','minItems':1,'maxItems':2,'description':'从11种原子操作选1—2项；数组表示同一波次，并非串行。',
            'items':{'oneOf':[{'type':'object','required':['action','slot'],'additionalProperties':False,
                'properties':{'action':{'enum':list(STEPS)},'slot':{'enum':['A','B','C']}}},
                {'type':'object','required':['action'],'additionalProperties':False,'properties':{'action':{'enum':['integrated_test','close_repair']}}}]}},
        'evidence':{'required':True,'type':['array','null'],'minItems':1,'items':{'type':'string','enum':list(CATALOG)},'description':'null或非空H01—H16编号数组；重复先去重最多2种。'}}})

    def actions(self):
        return [] if self.done else super().actions()

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','operations','evidence'} or action['action'] != 'dispatch':
            self.invalid()
            return
        operations = action['operations']
        if not isinstance(operations,list) or not 1 <= len(operations) <= 2:
            self.invalid()
            return
        for operation in operations:
            if not isinstance(operation,dict) or not isinstance(operation.get('action'),str):
                self.invalid()
                return
            if operation['action'] in STEPS:
                valid = set(operation) == {'action','slot'} and isinstance(operation['slot'],str) and operation['slot'] in ('A','B','C')
            else:
                valid = set(operation) == {'action'} and operation['action'] in ('integrated_test','close_repair')
            if not valid:
                self.invalid()
                return
        refs = action['evidence']
        if refs is not None and (not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in CATALOG for ref in refs) or len(set(refs)) > 2):
            self.invalid()
            return
        refs = None if refs is None else list(dict.fromkeys(refs))
        score = evaluate(self.task.world,operations,refs)
        self.state['registered_operations'] = deepcopy(operations)
        self.facts = {'registered_operations':deepcopy(operations),'references':refs}
        self.feedback = '维修波次分派与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for operations in combinations(facts['available'],facts['maximum']):
        for count in (1,2):
            for refs in combinations(CATALOG,count):
                if evaluate(facts,operations,refs) == 100:
                    return {'action':'dispatch','operations':deepcopy(list(operations)),'evidence':list(refs)}
    raise ValueError('A maximum valid wave must have sufficient evidence within two records')


def check_world(task,facts):
    expected = {slot:slot_state(slot,stage) for slot,stage in facts['stages'].items()}
    if task.world != facts or task.initial['slot_states'] != expected or task.initial['test_completed'] != facts['test_completed']:
        raise ValueError('Two-arm repair waves must follow actual branches and independent test completion')


def audit_cases(task,facts,solution):
    cases = []
    atoms = [row['operations'][0] for row in task.public['actions']]
    for count in (1,2):
        for operations in combinations_with_replacement(atoms,count):
            for refs in (None,*(list(refs) for size in (1,2) for refs in combinations(CATALOG,size))):
                command = {'action':'dispatch','operations':deepcopy(list(operations)),'evidence':refs}
                cases.append(([command],evaluate(facts,operations,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
