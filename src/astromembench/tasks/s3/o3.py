"""FM-S3-O3: recover delivered batches and non-revivable actuator evidence."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
MENU = ('pump_1L','open_valve','pump_6L','disconnect','pump_3L','archive_handover','pump_8L',
        'close_valve','pump_2L','finish','pump_10L','pump_4L','pump_7L','pump_5L','pump_9L')
CONFIGS = ((4,10,'O',7,'K0',2),(8,11,'O',8,'K1',10),(20,20,'O',7,'K1',11),
           (0,0,'C',8,'K0',7),(14,20,'D',8,'K0',13),(20,20,'G',8,'K1',10),
           (10,15,'O',8,'K1',3),(16,19,'O',8,'K1',5),(12,20,'C',7,'K1',1),
           (9,15,'C',8,'K1',9),(12,12,'O',7,'K1',0),(6,14,'O',8,'K1',8),
           (3,20,'C',7,'K0',11),(7,20,'O',8,'K1',7),(15,16,'O',8,'K0',13),(4,13,'O',7,'K1',4))


def actuators(stage):
    return {'connected':stage in ('O','C'),'valve_open':stage == 'O','handover_archived':stage == 'G'}


def description(action):
    return f'实际定量泵送{action[5:-1]} L' if action.startswith('pump_') else {
        'open_valve':'打开阀门','close_valve':'关闭阀门','disconnect':'确认无残流后脱离接口',
        'archive_handover':'完成外部交接归档','finish':'结束W8'}[action]


def fields_text(fields):
    parts = []
    for name,value in fields.get('meter',{}).items():
        label = {'B1':'第一批B1已交付','B2':'第二批B2已交付','total_l':'累计净转移'}[name]
        parts.append(f'{label}{value} L')
    for name,value in fields.get('actuators',{}).items():
        parts.append({'connected':('接口已脱离','接口仍连接'),
            'valve_open':('阀门已关闭','阀门已打开'),
            'handover_archived':('外部交接未归档','外部交接已归档')}[name][int(value)])
    for name,value in fields.get('tanks_l',{}).items():
        parts.append(('供罐' if name == 'source' else '收罐')+f'{value} L')
    return '；'.join(parts)


def build(index):
    q,volume,stage,failed,loaded,offset = CONFIGS[index]
    delta = volume-q
    interface = '综合验收' if index < 6 else '计量与执行器分开' if index < 12 else '分批交接'
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()

    def record(at,letter,text,**facts):
        history.add(at,ids[letter]+'：'+text,record_id=ids[letter],**facts)

    def fields(meter,mechanical=None):
        result = {'meter':meter}
        if mechanical is not None:
            result['actuators'] = mechanical
        if index < 6 and 'total_l' in meter:
            result['tanks_l'] = {'source':80-meter['total_l'],'receiver':7+meter['total_l']}
        return result

    initial = {'meter':{'total_l':0},'actuators':actuators('C'),'tanks_l':{'source':80,'receiver':7}}
    first = fields({'B1':q,'total_l':q},actuators('O') if index < 6 else None)
    second = fields({'B2':delta,**({'total_l':volume} if index < 12 else {})},actuators('O') if index < 6 else None)
    final = fields({'total_l':volume} if index < 6 else {'B2':delta} if index >= 12 else {},actuators(stage))

    def receipt(at,letter,text,reported,operations=()):
        record(at,letter,'本机W8/接收端R：'+text+'；接口实际报告：'+fields_text(reported),event='supply_actual',
               order='W8',receiver='R',operations=list(operations),**deepcopy(reported))

    def snapshot(at,letter,name,reported,save_time,*,load=False):
        record(at,letter,('读取' if load else '保存')+f'W8/R快照{name}，原保存时间{save_time}；保存时真实字段：'+fields_text(reported)+
               '；只操作显示缓存，无开泵、阀动作或档案改写。',event='supply_snapshot_loaded' if load else 'supply_snapshot_saved',
               order='W8',receiver='R',snapshot=name,saved_s=clock(save_time),**deepcopy(reported))

    history.add(1,'W8向接收端R净补给20 L；供罐初始80 L，收罐初始7 L、容量40 L，两罐总量恒87 L，净转移V后为80−V和7+V。'
        '当前管路、泵阀及接口正常，唯一管路正确连接，零泄漏、1 L精度，无未记录残流。初始连接、阀关、无外部交接档案。'
        '只认实转量；失败或中断已实转的液体仍计入，计划、请求、受理不计入。请求量不保证等于实际剩余量。'
        '过去连续自动泵可转0—20 L；恢复后当前定量程序只有1—10 L，目标达到不得再泵。'
        '未满且阀关先开阀；未满且阀开选恰好剩余升数；已满且阀开先关；已满且关阀仍连接则脱离；脱离且未归档则交接归档；已归档结束。'
        '历史允许未满暂停关阀；脱离须已满、关阀、无残流；归档须已脱离。真实交付、计量、阀位和独立档案不随显示重启或载入回滚。'
        '设备采用'+interface+'接口：'+('各综合回执给当前累计、两罐量和完整连接/阀位/档案字段。' if index < 6 else
        '计量回执报告实际批次及累计，执行器回执报告机械/档案，无跨接口字段合并。' if index < 12 else
        '首批B1有累计读数，第二批B2只报自身实际增量；交接报告复述B2及机械/档案，不给B1、当前累计或罐量。')+
        'B1/B2为不同实际批次，相同批次复述只计一次；当前累计不能再加已包含批次。早累计在后来正转移后失效，批次成果持久。'
        '正实转证明当时已连接、阀开，零转移不证明；纯计量缓存不包含实际泵送动作。机械字段在相反真实动作后失效，后来恢复同值也不复活旧证。'
        '明确成功脱离蕴含已满且阀关，成功归档蕴含前序完成。引用内容的有效字段可以合并，但未引用后态不自动补入；无编号动作只用于可达性和撤销旧字段。'
        '当前仅登记下一作业，不真正驱动，可引用实际旧状态/实转/机械分量；准确缓存可合证，过时缓存、别工单和请求不证明当前状态。'
        '提交精确action、evidence，证据为null或非空H01—H16数组，重复先去重最多2种。3次总调用含格式错，首格式合法即终局，无重答；原生检索不计额度。',event='supply_protocol')
    receipt(2,'a','本批初态核对，尚无交付',initial)
    record(3,'b','W7/R上一批已实转20 L、关阀、脱离和归档，是独立批次，不是W8物料余额。',event='old_supply_completed',order='W7',receiver='R')
    snapshot(4,'c','K0',initial,'08:04')
    record(5,'d','W8补20 L及收尾计划受理，未实际转移。',event='supply_planned')
    history.add(6,'管路识别及安全联锁正常，无液体转移。',event='supply_monitoring')
    history.add(7,'W8/R实际开阀成功，仍连接，累计0 L。',event='supply_actual',order='W8',receiver='R',
                operations=[{'action':'open_valve'}],meter={'total_l':0},actuators={'connected':True,'valve_open':True})
    receipt(8,'e',f'第一批B1实转{q} L'+('成功' if q else '，未开泵'),first,
            [{'action':'pump','batch':'B1','actual_l':q}] if q else [])
    snapshot(9,'f','K1',first,'08:09')
    history.add(10,'稳定保持，无液体转移。',event='supply_monitoring')
    record(11,'g','另一独立接收端Q的工单实转30 L并归档；R管路无动作。',event='other_supply_completed',order='Q9',receiver='Q')
    for at,text in ((12,'计量器自检正常，无累计变化。'),(13,'温度18℃，无补给。'),(14,'等待下一排程指令，无液体转移。')):
        history.add(at,text,event='supply_monitoring')
    message = ('只提交已有批次的完成通知，通知失败，无新泵动作；B2实际0 L' if q == 20 else
               f'第二批B2原请求{20-q} L，执行中断或完成通知失败，实际转移{delta} L；已交付部分持久记账')
    receipt(15,'h',message,second,[{'action':'pump','batch':'B2','actual_l':delta}] if delta else [])
    history.add(16,'泵驱动暂停，无表外残流。',event='supply_monitoring')
    record(17,'i','下一工序请求进入等待，未执行，不报告最终状态。',event='supply_request_accepted')
    actions = [] if stage == 'O' else [{'action':'close_valve'}]
    if stage in ('D','G'):
        actions.append({'action':'disconnect'})
    if stage == 'G':
        actions.append({'action':'archive_handover'})
    receipt(18,'j','；'.join(description(op['action'])+'实际成功' for op in actions) or '无新增机械操作，实际接口核对',final,actions)
    if failed == 8:
        receipt(19,'k','下一指令提交失败，执行数0，没有物理或档案变化',final)
    else:
        record(19,'k','W7/R旧批次结束标记提交失败、执行0，已归档状态不变，W8无新动作。',event='old_supply_failure',order='W7',receiver='R')
    for at,text in ((20,'停止所有补给执行，无转移或档案新写入。'),(21,'保留管路当前物理位置。'),
                    (22,'调度显示服务故障重启，计量持久存储、液体、阀位和外部档案均未回滚。'),
                    (23,'泵阀提交接口恢复正常，未开泵。'),(24,'本批20 L目标未变，无新物料操作。')):
        if at == 22:
            record(at,'l',text,event='supply_display_failed')
        else:
            history.add(at,text,event='supply_monitoring')
    saved = deepcopy(initial if loaded == 'K0' else first)
    if index >= 6:
        saved = {'meter':saved['meter']}
    snapshot(25,'m',loaded,saved,'08:04' if loaded == 'K0' else '08:09',load=True)
    record(26,'n','操作接口就绪，无液体转移。',event='supply_monitoring')
    history.add(27,'时钟同步，无计量变化。',event='supply_monitoring')
    record(28,'o','W7补给计划副本归档，无当前工单操作。',event='supply_plan_archived',order='W7')
    record(29,'p','传感器温度18℃，无新操作。',event='supply_monitoring')
    history.add(30,'全部执行器保持当前状态，没有新交接。',event='supply_monitoring')
    task = task_shell('FM-S3-O3',index,current_input_group='FM-S3-O3')
    task.public = {'instruction':'继续工单W8向R的补给任务，提交下一项作业及依据；当前只登记决定。',
        'order':'W8','receiver':'R','target_l':20,'time_s':clock('09:00'),'max_steps':3,'state_fields':[],
        'record_catalog':list(CATALOG),'actions':[{'action':action,'description':description(action)} for action in MENU]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'volume_l':volume,**actuators(stage),'registered_action':None}
    task.rubric = {'score':'correct action with sufficient current fields and distinct actual batches:100; useful actual but insufficient:30; otherwise:0'}
    return history.finish(task)


def _supply_fields(text):
    values,batches,tanks = {},{},{}
    mechanical = {'接口已脱离':('connected',False),'接口仍连接':('connected',True),
        '阀门已关闭':('valve_open',False),'阀门已打开':('valve_open',True),
        '外部交接未归档':('handover_archived',False),'外部交接已归档':('handover_archived',True)}
    for part in text.split('；'):
        if match := re.fullmatch(r'第([一二])批(B[12])已交付(\d+) L',part):
            number,batch,amount = match.groups()
            if batch != {'一':'B1','二':'B2'}[number] or batch in batches:
                raise ValueError('Supply fields must identify each distinct batch once')
            batches[batch] = int(amount)
        elif match := re.fullmatch(r'累计净转移(\d+) L',part):
            if 'volume_l' in values:
                raise ValueError('A supply receipt has one cumulative reading')
            values['volume_l'] = int(match[1])
        elif part in mechanical:
            key,value = mechanical[part]
            if key in values:
                raise ValueError('A supply receipt has one value per mechanical field')
            values[key] = value
        elif match := re.fullmatch(r'(供|收)罐(\d+) L',part):
            if match[1] in tanks:
                raise ValueError('A supply receipt has one reading per tank')
            tanks[match[1]] = int(match[2])
        else:
            raise ValueError('Supply fields must describe delivered liquid and reported physical state')
    return values,batches,tanks


def _supply_operations(text,batches):
    if text in ('本批初态核对，尚无交付','无新增机械操作，实际接口核对',
                '下一指令提交失败，执行数0，没有物理或档案变化'):
        return []
    if match := re.fullmatch(r'第一批B1实转(\d+) L(成功|，未开泵)',text):
        amount = int(match[1])
        if batches.get('B1') != amount or (match[2] == '成功') != (amount > 0):
            raise ValueError('The first delivery and its batch reading must agree')
        return [('B1',amount)]
    if match := re.fullmatch(r'第二批B2原请求(\d+) L，执行中断或完成通知失败，实际转移(\d+) L；已交付部分持久记账',text):
        request,amount = map(int,match.groups())
        if amount > request or batches.get('B2') != amount:
            raise ValueError('Interrupted delivery must use its actual batch quantity')
        return [('B2',amount)]
    if text == '只提交已有批次的完成通知，通知失败，无新泵动作；B2实际0 L':
        if batches.get('B2') != 0:
            raise ValueError('A failed notification alone cannot deliver liquid')
        return []
    operations = []
    names = {description(action)+'实际成功':action for action in ('open_valve','close_valve','disconnect','archive_handover')}
    for part in text.split('；'):
        if part not in names:
            raise ValueError('Supply receipts must identify actual successful operations')
        operations.append((names[part],None))
    return operations


def correct_action(state):
    if state['handover_archived']:
        return 'finish'
    if not state['connected']:
        return 'archive_handover'
    if state['volume_l'] < 20:
        return f"pump_{20-state['volume_l']}L" if state['valve_open'] else 'open_valve'
    return 'close_valve' if state['valve_open'] else 'disconnect'


def reconstruct(history,current):
    state,epochs = {},{}
    receipts,snapshots,delivered = {},{},{}
    scope = re.escape(current['order']+'/'+current['receiver'])
    actual_scope = re.escape('本机'+current['order']+'/接收端'+current['receiver'])
    source_initial = receiver_initial = capacity = None

    def update(values):
        for key,value in values.items():
            if state[key] != value:
                epochs[key] += 1
                state[key] = value

    for text in paragraphs(history):
        if match := re.match(re.escape(current['order']+'向接收端'+current['receiver'])+
                r'净补给(\d+) L；供罐初始(\d+) L，收罐初始(\d+) L、容量(\d+) L，两罐总量恒(\d+) L，',text):
            target,source_initial,receiver_initial,capacity,total = map(int,match.groups())
            if target != current['target_l'] or total != source_initial+receiver_initial or '初始连接、阀关、无外部交接档案。' not in text:
                raise ValueError('Supply initialization must follow the public material protocol')
            state = {'volume_l':0,'connected':True,'valve_open':False,'handover_archived':False}
            epochs = dict.fromkeys(state,0)
            continue
        if text == current['order']+'/'+current['receiver']+'实际开阀成功，仍连接，累计0 L。':
            update({'valve_open':True})
            continue
        numbered = re.fullmatch(r'(H\d{2})：(.+)',text)
        if not numbered:
            continue
        identifier,body = numbered.groups()
        snapshot = None
        batch_epochs = None
        if match := re.fullmatch(r'(保存|读取)'+scope+r'快照(K\d+)，原保存时间(\d{2}:\d{2})；保存时真实字段：(.+)；只操作显示缓存，无开泵、阀动作或档案改写。',body):
            kind,name,saved,fields = match.groups()
            snapshot = (name,saved)
            actual = False
            values,batches,tanks = _supply_fields(fields)
        elif match := re.fullmatch(actual_scope+r'：(.+)；接口实际报告：(.+)',body):
            message,fields = match.groups()
            actual = True
            values,batches,tanks = _supply_fields(fields)
            for action,amount in _supply_operations(message,batches):
                if action in ('B1','B2'):
                    if action in delivered:
                        if delivered[action]['amount'] != amount:
                            raise ValueError('The same delivered batch cannot change its quantity')
                    else:
                        update({'volume_l':state['volume_l']+amount,
                            **({'connected':True,'valve_open':True} if amount > 0 else {})})
                        delivered[action] = {'amount':amount,'epochs':deepcopy(epochs)}
                    batch_epochs = delivered[action]['epochs']
                    if amount > 0:
                        values.update(connected=True,valve_open=True)
                elif action in ('open_valve','close_valve'):
                    update({'valve_open':action == 'open_valve'})
                    values['valve_open'] = action == 'open_valve'
                elif action == 'disconnect':
                    update({'connected':False})
                    values.update(volume_l=20,connected=False,valve_open=False)
                elif action == 'archive_handover':
                    update({'handover_archived':True})
                    values.update(volume_l=20,connected=False,valve_open=False,handover_archived=True)
            if any(batch in delivered and delivered[batch]['amount'] != amount for batch,amount in batches.items()):
                raise ValueError('A repeated batch report must preserve its delivered quantity')
        else:
            continue
        if tanks:
            volume = values.get('volume_l')
            if (volume is None or source_initial is None or tanks != {'供':source_initial-volume,'收':receiver_initial+volume}
                    or not 0 <= tanks['收'] <= capacity or tanks['供'] < 0):
                raise ValueError('Reported tank quantities must conserve the published liquid')
        proof = {'values':values,'batches':batches,'epochs':{key:(epochs if batch_epochs is None else batch_epochs)[key] for key in values},'actual':actual}
        if snapshot is not None:
            if kind == '读取':
                original = snapshots[snapshot]
                if any(original['values'].get(key) != value for key,value in values.items()) or any(original['batches'].get(key) != value for key,value in batches.items()):
                    raise ValueError('Loaded fields must belong to the named original snapshot')
                proof['epochs'] = {key:original['epochs'][key] for key in values}
            else:
                snapshots[snapshot] = deepcopy(proof)
        receipts[identifier] = proof
    for proof in receipts.values():
        proof['values'] = {key:value for key,value in proof['values'].items() if proof['epochs'][key] == epochs[key]}
        del proof['epochs']
    return {'state':state,'evidence':receipts,'correct_action':correct_action(state)}


def evaluate(facts,action,refs):
    if action != facts['correct_action'] or refs is None:
        return 0
    values,batches,useful = {},{},False
    for ref in refs:
        proof = facts['evidence'].get(ref,{})
        values.update(proof.get('values',{}))
        batches.update(proof.get('batches',{}))
        useful |= proof.get('actual',False)
    if 'volume_l' not in values and set(batches) == {'B1','B2'}:
        values['volume_l'] = batches['B1']+batches['B2']
    volume = values.get('volume_l')
    connected = values.get('connected')
    opened = values.get('valve_open')
    if action == 'finish':
        enough = values.get('handover_archived') is True
    elif action == 'archive_handover':
        enough = connected is False and values.get('handover_archived') is False
    elif action == 'disconnect':
        enough = volume == 20 and opened is False and connected is True
    elif action == 'close_valve':
        enough = volume == 20 and opened is True
    elif action == 'open_valve':
        enough = volume is not None and volume < 20 and opened is False and connected is True
    else:
        enough = volume == 20-int(action[5:-1]) and opened is True and connected is True
    return 100 if enough else 30 if useful else 0


class Runtime(TaskRuntime):
    action_contract = ActionContract(fields=('action',),parameters={'*':{'evidence':{'type':['array','null'],'required':True,
        'items':{'type':'string','enum':list(CATALOG)},'minItems':1,'description':'null或非空H01—H16编号数组；重复先去重，最多2种。'}}})

    def actions(self):
        return [] if self.done else super().actions()

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','evidence'} or action['action'] not in MENU:
            self.invalid()
            return
        refs = action['evidence']
        if refs is not None and (not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in CATALOG for ref in refs) or len(set(refs)) > 2):
            self.invalid()
            return
        refs = None if refs is None else list(dict.fromkeys(refs))
        score = evaluate(self.task.world,action['action'],refs)
        self.state['registered_action'] = action['action']
        self.facts = {'registered_action':action['action'],'references':refs}
        self.feedback = '补给接续决定与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for count in (1,2):
        for refs in combinations(CATALOG,count):
            if evaluate(facts,facts['correct_action'],refs) == 100:
                return {'action':facts['correct_action'],'evidence':list(refs)}
    raise ValueError('Supply continuation requires a sufficient proof within two distinct records')


def check_world(task,facts):
    if task.world != facts or task.initial != {**facts['state'],'registered_action':None}:
        raise ValueError('Supply recovery must preserve delivered batches and actual actuator state')


def audit_cases(task,facts,solution):
    cases = []
    for action in MENU:
        for refs in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{'action':action,'evidence':refs}],evaluate(facts,action,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
