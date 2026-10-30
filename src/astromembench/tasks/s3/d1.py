"""FM-S3-D1: continue an ordered pulse sequence from cumulative and delta telemetry."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp
from ..common import History, clock, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds

TARGETS = {'X':4,'Y':6,'Z':8}
CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
MENU = tuple(f'pulse_{channel}_{seconds}s' for channel in 'XYZ' for seconds in range(1,9))+('finish_sequence',)
CONFIGS = (('XYZ',0,1,7,'K0',4),('XYZ',3,4,8,'K1',8),('XYZ',9,10,8,'K1',2),
           ('XYZ',18,18,8,'K1',5),('XZY',17,18,7,'K1',14),('YZX',0,0,8,'K0',9),
           ('XYZ',5,7,8,'K1',6),('XYZ',15,17,7,'K0',0),('YXZ',0,2,7,'K0',11),
           ('YXZ',4,6,8,'K1',3),('ZXY',1,3,7,'K0',1),('ZXY',5,8,8,'K1',12),
           ('XZY',4,6,7,'K0',4),('YZX',6,12,8,'K1',8),('YZX',14,17,8,'K1',5),('ZYX',7,8,7,'K0',0))


def prefix(order,total):
    counts = dict.fromkeys('XYZ',0)
    for channel in order:
        counts[channel] = min(total,TARGETS[channel])
        total -= counts[channel]
    return counts


def counts_text(counts):
    return '、'.join(f'{channel}通道{value}秒' for channel,value in counts.items())


def segments_text(segments):
    return '；'.join(f'{segment["channel"]}通道实际驱动{segment["actual_seconds"]}秒（'+
        story_timestamp(segment['started_s'])+'开始，'+story_timestamp(segment['completed_s'])+'完成）'
        for segment in segments) or '无驱动脉冲'


def build(index):
    order,q,total,failed,loaded,offset = CONFIGS[index]
    zero,prior,final = dict.fromkeys('XYZ',0),prefix(order,q),prefix(order,total)
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()

    def record(at,letter,text,**facts):
        stamp = story_timestamp(facts.get('occurred',clock(f'08:{at:02d}')))
        history.add(at,ids[letter]+'：'+text+f'该记录于{stamp}发生。',record_id=ids[letter],**facts)

    def snapshot(at,letter,name,counts,saved,*,load=False):
        record(at,letter,('载入' if load else '保存')+f'N8快照{name}，原保存时间{story_timestamp(clock(saved))}，当时真实累计：'+counts_text(counts)+
               '；只读取显示，不施加或撤销脉冲，不读取当前实际计数。',event='pulse_snapshot',sequence='N8',
               snapshot=name,saved_s=clock(saved),counts_seconds=deepcopy(counts))

    def batch(at,letter,before,after,*,delta_only=False):
        delta = {channel:after[channel]-before[channel] for channel in 'XYZ'}
        start = clock(f'08:{at:02d}')
        elapsed,segments = 0,[]
        for channel in order:
            seconds = delta[channel]
            if seconds:
                segments.append({'channel':channel,'actual_seconds':seconds,'started_s':start+elapsed,'completed_s':start+elapsed+seconds})
                elapsed += seconds
        fields = {'actual_delta_seconds':delta}
        if not delta_only:
            fields.update(counts_seconds=deepcopy(after),segments=segments)
        report = ('中断后的增量遥测：仅报告实际新增'+counts_text(delta) if delta_only else
            '综合计数回执：实际新增'+counts_text(delta)+'；当前完整累计'+counts_text(after)+'；实际脉冲段：'+segments_text(segments))
        record(at,letter,'N8本批'+report+'；已经实际施加的部分保留，未列脉冲没有发生。',event='pulse_batch',sequence='N8',
               occurred=start+elapsed,received=start+59,**fields)

    history.add(1,'巡航保障序列N8，严格按'+ '→'.join(order)+'逐通道执行，目标X4/Y6/Z8秒。恒定执行速率，只有确认的实际脉冲计入，失败中断已施加部分仍计入。'
        '每通道满目标后才进入下一通道，满后不重发、不回退；不得交换次序、超额或提前驱动后通道。N7是开始N8前的独立序列；地面离线标定不是本航天器实际驱动。'
        '无后台脉冲、未确认执行或隐蔽自动补偿，待执行队列中断后全部撤销，恢复不补发，界面检查点不撤销实际脉冲。'
        '执行器健康、姿态闭环与低层控制正常；当前选首个未满通道恰好剩余秒数的1—8秒程序，全满才结束。25动作全部可选，错序/超额是业务决定并结束作答。'
        +('本机采用增量遥测：第一批有完整累计，后来批只给各通道新增秒数，不给原累计、当前累计、完成标签、起止位置或剩余量；失败回执只给执行0。' if index >= 12 else
          '本机采用综合计数：批次回执给实际新增量及完整累计，失败回执给执行0及当前完整累计。')+
        '证据可合并真实累计基线与所引后续实际增量，逐通道不得漏掉其他后续正增量，两个累计不能相加。同一真实增量只计一次，快照用原保存时刻。'
        '后通道实际正脉冲按严格前置证明此前通道已满，满值持久。旧向量中未被推进的分量仍有效，不因别通道过时一并作废。'
        '未引用历史只用于核对失效或漏增量，不把其数值补入证据；下一脉冲只需前通道已满及当前活动通道精确量，结束需全部满。'
        '当前只登记一个决定，不真实发射。提交精确action和evidence；证据为null或非空H01—H16数组，重复先去重最多2种。'
        '3次总调用含格式错，首格式合法即终局，反馈不允许试射后重答；原生记忆检索不计额度。',event='pulse_protocol',
        sequence='N8',sequence_order=list(order),target_seconds=TARGETS)
    record(2,'a','N8开始，各通道实际累计均0，无待执行命令。',event='pulse_initial',sequence='N8',counts_seconds=zero)
    record(3,'b','收到第119日N7已完成X4/Y6/Z8秒的遥测，是旧独立保障序列，本次未驱动。',event='old_pulse_archive',
           sequence='N7',counts_seconds=TARGETS,occurred=clock('18:00',day=119))
    snapshot(4,'c','K0',zero,'08:04')
    record(5,'d','N8完整序列已列入计划，不代表实际执行。',event='pulse_planned',sequence='N8')
    for at,text in ((6,'执行器自检，无驱动脉冲。'),(7,'保障时钟同步，无驱动。')):
        history.add(at,text,event='pulse_monitoring')
    batch(8,'e',zero,prior)
    snapshot(9,'f','K1',prior,'08:09')
    record(10,'g','读取独立地面离线标定：通道试验各8秒，不是本航天器N8实际脉冲。',event='ground_calibration',counts_seconds=dict.fromkeys('XYZ',8))
    for at,text in ((11,'温度18℃，无驱动。'),(12,'遥测链路正常，无驱动。'),(13,'N8顺序与目标不变。')):
        history.add(at,text,event='pulse_monitoring')
    record(14,'i','下一控制段请求受理，尚未执行，无执行完成字段。',event='pulse_request_accepted',sequence='N8')
    history.add(15,'等待排程驱动，无新增脉冲。',event='pulse_monitoring')
    batch(16,'h',prior,final,delta_only=index >= 12)
    history.add(17,'中断后所有待执行命令撤销，自动队列为空，无额外驱动。',event='pulse_queue_cancelled')
    history.add(18,'各通道保持，没有继续脉冲。',event='pulse_monitoring')
    if failed == 8:
        fields = {'counts_seconds':deepcopy(final)} if index < 12 else {}
        record(19,'j','N8下一指令提交失败，执行数0，无新增脉冲'+('；当前完整累计'+counts_text(final) if fields else '；不报告指令内容或当前计数'),
               event='pulse_failure',sequence='N8',executions=0,**fields)
    else:
        record(19,'j','重读第119日N7结束标记失败日志，N8无新驱动。',event='old_pulse_failure',sequence='N7',occurred=clock('18:01',day=119))
    record(20,'k','N8此后没有后台脉冲，未设置自动补发。',event='pulse_queue_audit',sequence='N8')
    history.add(21,'无通道驱动。',event='pulse_monitoring')
    record(22,'l','控制显示服务故障重启，只恢复显示；实际累计脉冲及持久遥测保留。',event='pulse_display_failed')
    history.add(23,'低层执行及提交接口恢复正常，没有重放命令。',event='pulse_monitoring')
    history.add(24,'保障目标未改变。',event='pulse_monitoring')
    snapshot(25,'m',loaded,zero if loaded == 'K0' else prior,'08:04' if loaded == 'K0' else '08:09',load=True)
    record(26,'n','接口就绪，无新脉冲。',event='pulse_monitoring')
    history.add(27,'时钟正常，队列仍空。',event='pulse_monitoring')
    record(28,'o','再读第119日N7同名通道完工档案，非N8实际脉冲。',event='old_pulse_archive',sequence='N7',
           counts_seconds=TARGETS,occurred=clock('18:00',day=119))
    record(29,'p','温度18℃，无驱动。',event='pulse_monitoring')
    history.add(30,'待命，无驱动。',event='pulse_monitoring')
    task = task_shell('FM-S3-D1',index,current_input_group='FM-S3-D1')
    task.public = {'instruction':'继续巡航保障序列N8，提交下一项控制作业及依据。','sequence':'N8','time_s':clock('09:00'),
        'max_steps':3,'state_fields':[],'record_catalog':list(CATALOG),'actions':[{'action':action,'description':
        '结束N8' if action == 'finish_sequence' else f'对通道{action[6]}实际驱动{action[8:-1]}秒'} for action in MENU]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'counts_seconds':final,'registered_action':None}
    task.rubric = {'score':'correct next full remaining segment with sufficient per-channel baseline/delta or prerequisite evidence:100; useful actual progress only:30; otherwise:0'}
    return history.finish(task)


def correct_action(counts,order,targets):
    for channel in order:
        if counts[channel] < targets[channel]:
            return f'pulse_{channel}_{targets[channel]-counts[channel]}s'
    return 'finish_sequence'


def _pulse_counts(text):
    counts = {}
    for part in text.split('、'):
        match = re.fullmatch(r'([XYZ])通道(\d+)秒',part)
        if not match or match[1] in counts:
            raise ValueError('Pulse telemetry must name each channel once with its duration')
        counts[match[1]] = int(match[2])
    if set(counts) != set('XYZ'):
        raise ValueError('Pulse telemetry must report all three channel components')
    return dict(sorted(counts.items()))


def _pulse_segments(text,delta,order,completed):
    segments = []
    if text != '无驱动脉冲':
        for part in text.split('；'):
            match = re.fullmatch(rf'([XYZ])通道实际驱动(\d+)秒（({STORY_STAMP})开始，({STORY_STAMP})完成）',part)
            if not match:
                raise ValueError('Pulse segments must report actual channel durations and story clocks')
            channel,duration,start,end = match.groups()
            start,end,duration = seconds(start),seconds(end),int(duration)
            if duration <= 0 or end-start != duration or segments and start != segments[-1][3]:
                raise ValueError('Actual pulse durations must match consecutive segment clocks')
            segments.append((channel,duration,start,end))
    if [(channel,duration) for channel,duration,_,_ in segments] != [(channel,delta[channel]) for channel in order if delta[channel] > 0]:
        raise ValueError('Pulse segments must follow the public order and reported actual increments')
    if segments and segments[-1][3] != completed:
        raise ValueError('The batch occurrence must be the actual last segment completion')


def _reachable_prefix(counts,order,targets):
    incomplete = False
    for channel in order:
        value = counts[channel]
        if not 0 <= value <= targets[channel] or incomplete and value != 0:
            return False
        incomplete |= value < targets[channel]
    return bool(order)


def reconstruct(history,current):
    counts,records,pulses = {},{},[]
    order,targets = [],{}
    scope = re.escape(current['sequence'])
    for text in paragraphs(history):
        if match := re.match(r'巡航保障序列'+scope+r'，严格按([XYZ]→[XYZ]→[XYZ])逐通道执行，目标X(\d+)/Y(\d+)/Z(\d+)秒。',text):
            order = match[1].split('→')
            if set(order) != set('XYZ'):
                raise ValueError('The pulse protocol must order each channel exactly once')
            targets = dict(zip('XYZ',map(int,match.groups()[1:]),strict=True))
            continue
        numbered = re.fullmatch(rf'(H\d{{2}})：(.+)该记录于({STORY_STAMP})发生。',text)
        if numbered is None:
            continue
        identifier,body,stamp = numbered.groups()
        at = seconds(stamp)
        anchor,delta,useful = {},{},False
        actual_counts = False
        if re.fullmatch(scope+r'开始，各通道实际累计均0，无待执行命令。',body):
            anchor,useful,actual_counts = dict.fromkeys('XYZ',0),True,True
        elif match := re.fullmatch(rf'(?:载入|保存){scope}快照K\d+，原保存时间({STORY_STAMP})，当时真实累计：(.+)；只读取显示，不施加或撤销脉冲，不读取当前实际计数。',body):
            at = seconds(match[1])
            anchor = _pulse_counts(match[2])
        elif match := re.fullmatch(scope+r'本批综合计数回执：实际新增(.+)；当前完整累计(.+)；实际脉冲段：(.+)；已经实际施加的部分保留，未列脉冲没有发生。',body):
            delta,anchor = _pulse_counts(match[1]),_pulse_counts(match[2])
            _pulse_segments(match[3],delta,order,at)
            useful,actual_counts = True,True
        elif match := re.fullmatch(scope+r'本批中断后的增量遥测：仅报告实际新增(.+)；已经实际施加的部分保留，未列脉冲没有发生。',body):
            delta,useful = _pulse_counts(match[1]),True
        elif match := re.fullmatch(scope+r'下一指令提交失败，执行数0，无新增脉冲；当前完整累计(.+)',body):
            anchor = _pulse_counts(match[1])
            actual_counts = True
        elif not re.fullmatch(scope+r'下一指令提交失败，执行数0，无新增脉冲；不报告指令内容或当前计数',body):
            continue
        proof = {'counts':anchor,'delta':delta,'time_s':at,'useful':useful}
        if identifier in records:
            if records[identifier] != proof:
                raise ValueError('A repeated pulse record must preserve its original telemetry and clock')
            continue
        if not order:
            raise ValueError('Pulse recovery requires the public sequence order and targets')
        if anchor and not _reachable_prefix(anchor,order,targets):
            raise ValueError('Cumulative pulse telemetry must be a reachable ordered prefix')
        if actual_counts and any(anchor[channel] < counts.get(channel,0) for channel in order):
            raise ValueError('Actual cumulative telemetry cannot revoke confirmed pulse progress')
        if delta and anchor:
            before = {channel:anchor[channel]-delta[channel] for channel in order}
            if not _reachable_prefix(before,order,targets) or pulses and before != counts:
                raise ValueError('Cumulative pulse telemetry must agree with its actual increment and known preceding batch')
        if actual_counts:
            counts = deepcopy(anchor)
        elif delta:
            for channel in order:
                duration = delta[channel]
                if duration > 0:
                    for prior in order[:order.index(channel)]:
                        counts[prior] = targets[prior]
                    counts[channel] += duration
        if delta:
            if not _reachable_prefix(counts,order,targets):
                raise ValueError('Actual pulse increments must preserve the ordered target prefix')
            pulses.append({'id':identifier,'time_s':at,'delta':deepcopy(delta)})
        records[identifier] = proof
    if not order:
        raise ValueError('Pulse recovery requires the public sequence order and targets')
    for proof in records.values():
        for channel,base in proof['counts'].items():
            subsequent = sum(pulse['delta'][channel] for pulse in pulses if pulse['time_s'] > proof['time_s'])
            if base+subsequent > counts[channel]:
                raise ValueError('Actual pulse history cannot account for its true dated anchors and later increments')
    return {'counts':counts,'order':deepcopy(order),'targets':deepcopy(targets),'evidence':records,'pulses':pulses,
            'correct_action':correct_action(counts,order,targets)}


def supported_counts(facts,refs):
    support = {channel:set() for channel in facts['order']}
    for ref in refs:
        proof = facts['evidence'].get(ref,{})
        for channel,seconds in proof.get('delta',{}).items():
            if seconds > 0:
                for previous in facts['order'][:facts['order'].index(channel)]:
                    support[previous].add(facts['targets'][previous])
        for channel,base in proof.get('counts',{}).items():
            following = [pulse for pulse in facts['pulses'] if pulse['time_s'] > proof['time_s'] and pulse['delta'][channel] > 0]
            if all(pulse['id'] in refs for pulse in following):
                support[channel].add(base+sum(pulse['delta'][channel] for pulse in following))
    return support


def evaluate(facts,action,refs):
    if action != facts['correct_action'] or refs is None:
        return 0
    support = supported_counts(facts,refs)
    required = deepcopy(facts['targets'])
    if action != 'finish_sequence':
        channel,seconds = action[6],int(action[8:-1])
        required = {prior:facts['targets'][prior] for prior in facts['order'][:facts['order'].index(channel)]}
        required[channel] = facts['targets'][channel]-seconds
    if all(value in support[channel] for channel,value in required.items()):
        return 100
    return 30 if any(facts['evidence'].get(ref,{}).get('useful',False) for ref in refs) else 0


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
        self.feedback = '保障序列接续决定与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for count in (1,2):
        for refs in combinations(CATALOG,count):
            if evaluate(facts,facts['correct_action'],refs) == 100:
                return {'action':facts['correct_action'],'evidence':list(refs)}
    raise ValueError('The next pulse must be provable within two records')


def check_world(task,facts):
    if task.world != facts or task.initial != {'counts_seconds':facts['counts'],'registered_action':None}:
        raise ValueError('Pulse continuation must preserve ordered actual durations after display recovery')


def audit_cases(task,facts,solution):
    cases = []
    for action in MENU:
        for refs in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{'action':action,'evidence':refs}],evaluate(facts,action,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
