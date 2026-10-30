"""FM-S3-D2: recover atomic archived frames without exposing failed exposure timing."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp
from ..common import History, clock, task_shell
from ..prose import STORY_STAMP, microseconds, paragraphs

PROTOCOLS = {'F':(2,1),'G':(4,2),'H':(6,3),'J':(8,4)}
CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
MENU = tuple(f'{kind}_{seconds}s' for kind in ('signal','reference') for seconds in range(1,9))+('finish_observation',)
CONFIGS = (('F',2,0,0,1,'K0',3),('F',2,0,1,0,'K1',11),('G',3,6,6,None,'K1',6),
           ('G',4,8,8,None,'K0',9),('F',4,0,0,0,'K1',2),('J',4,6,8,None,'K0',8),
           ('G',2,2,3,2,'K1',7),('J',3,0,0,8,'K0',9),('J',3,0,1,2,'K1',1),
           ('H',4,1,2,5,'K1',0),('H',4,2,3,3,'K0',11),('H',3,0,1,0,'K1',1),
           ('G',4,3,4,4,'K1',13),('J',4,5,7,4,'K0',14),('H',4,3,6,6,'K1',15),('J',4,1,7,3,'K0',6))


def frame(index,protocol,*,cycle='N8',target='T'):
    kind = 'signal' if index%2 == 0 else 'reference'
    group = index//2+1
    return {'frame_id':f'{cycle}-{target}-{kind}-{group}','kind':kind,'group':group,'exposure_seconds':PROTOCOLS[protocol][index%2]}


def frame_list(count,pairs,protocol,*,cycle='N8',target='T'):
    return {'archived_frames':[frame(i,protocol,cycle=cycle,target=target) for i in range(count)],
            'reserved_frames':[frame(i,protocol,cycle=cycle,target=target) for i in range(count,2*pairs)]}


def _frame_text(item):
    kind = '信号' if item['kind'] == 'signal' else '参考'
    return f'{item["frame_id"]}（第{item["group"]}组{kind}，完整曝光{item["exposure_seconds"]}秒）'


def _frames_text(items):
    return '、'.join(_frame_text(item) for item in items) or '无'


def _inventory_text(fields, when='当前'):
    return (f'{when}成功归档帧：{_frames_text(fields["archived_frames"])}；'
            f'{when}尚未完成的预约帧：{_frames_text(fields["reserved_frames"])}。')


def build(index):
    protocol,pairs,q,count,exposed,loaded,offset = CONFIGS[index]
    detailed = index < 12
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()
    actual_batches = []

    def record(at,letter,text,**facts):
        received = facts.get('received', clock(f'08:{at:02d}'))
        history.add(at,ids[letter]+'：'+text+f'该记录于{story_timestamp(received)}收到。',record_id=ids[letter],**facts)

    def snapshot(at,letter,name,prefix,saved):
        fields = frame_list(prefix,pairs,protocol) if detailed else {'archived_count':prefix}
        contents = _inventory_text(fields, '当时') if detailed else f'当时实际成功数为{prefix}帧。'
        record(at,letter,('载入' if at == 25 else '保存')+f'N8/T快照{name}，原保存时间{story_timestamp(clock(saved))}。'+contents+
               '纯显示缓存，不扫描当前归档盘，不创建有效帧。',event='frame_snapshot',cycle='N8',target='T',
               snapshot=name,saved_s=clock(saved),**fields)

    def batch(at,letter,first,last):
        start,elapsed,completed = clock(f'08:{at:02d}'),0,[]
        for ordinal in range(first,last):
            item = frame(ordinal,protocol)
            completed.append({**item,'started_s':start+elapsed,'completed_s':start+elapsed+item['exposure_seconds'],'readout_archived':True})
            elapsed += item['exposure_seconds']
        actual_batches.append({'received_s':start+59,'completed_frames':completed})
        if detailed:
            fields = {**frame_list(last,pairs,protocol),'completed_frames':completed}
            occurred = start+elapsed
            reports = '、'.join(_frame_text(item)+f'，启动于{story_timestamp(item["started_s"])}，'
                f'完成于{story_timestamp(item["completed_s"])}，读出并归档成功' for item in completed) or '无'
            contents = f'本批新增归档帧：{reports}；'+_inventory_text(fields)
        else:
            fields = {'archived_count':last} if at == 8 else {'new_archived_count':last-first}
            occurred = start+59
            contents = f'实际持久成果总数为{last}帧。' if at == 8 else f'本批新增有效帧{last-first}帧。'
        record(at,letter,'N8/T归档服务回执：'+contents+'所报成果均已完成完整曝光、成功读出并持久归档；空批无新增帧。'+
               ('' if detailed else '时间戳仅为轮末服务报告的生成/接收时刻，不是曝光起止。'),
               event='frame_batch',cycle='N8',target='T',occurred=occurred,received=start+59,**fields)

    signal,reference = PROTOCOLS[protocol]
    history.add(1,f'目标T、观测周期N8，需{pairs}组，每组严格先信号S再参考R，顺序S1,R1,…,S{pairs},R{pairs}。协议{protocol}：信号完整{signal}秒、参考完整{reference}秒。'
        '成功帧必须完整曝光、成功读出并持久归档；预约或曝光达到时长不算成功。归档帧按上述顺序形成前缀；旧周期N7或另一目标Q不满足T/N8。'
        '曝光中断或读出失败不增加有效帧，临时积分清空，下一次必须完整重拍该缺失帧，不能补剩余秒或重拍已经保存的信号。'
        '无后台曝光、未记录帧或自动补拍。故障后目标稳定、同一固定协议和标定，已归档信号仍可与后来同周期参考配对，无额外有效期。'
        +('设备提供逐帧清单及实际曝光/读出回执。' if detailed else
          '设备采用归档计数接口：第一批只报实际总数，第二批只报新增有效数；快照只报保存时实际数；失败只报零新增、清空积分和保留持久成果。轮级服务报告不含每帧或失败曝光起止、类型、组号、时长或末帧元数据。')+
        '两个累计清单或计数不能相加；累计基线只可加所引后续真实新增成果，不得漏掉后来正新增，原保存时间决定缓存基线。零新增通知不补当前计数。'
        '未满时成功前缀为偶数拍下一信号、奇数拍对应参考，均选协议完整时长；全满才结束。全部17程序恒可选，错时长/错类型是业务错。'
        '当前只登记下一完整程序，不实际取像或产生新帧。提交精确action和evidence；证据为null或非空H01—H16数组，重复先去重最多2种。'
        '最多3次总调用含格式错，首格式合法即终局，无试拍后重答；原生记忆检索不计额度。',event='frame_protocol',
        cycle='N8',target='T',protocol=protocol,pairs=pairs,exposure_seconds={'signal':signal,'reference':reference})
    record(2,'a','N8/T尚未归档任何信号或参考帧，成功前缀0，无在途曝光。',event='frame_initial',cycle='N8',target='T',archived_count=0)
    record(3,'b','旧周期N7/T全部成功帧清单，不属于N8：'+_frames_text(frame_list(2*pairs,pairs,protocol,cycle='N7')['archived_frames'])+'。',
           event='old_frame_archive',cycle='N7',target='T')
    snapshot(4,'c','K0',0,'08:04')
    reservations = [{**frame(i,protocol),'status':'预约、未曝光'} for i in range(2*pairs)]
    record(5,'d','创建N8/T全部预约与计划，以下各帧均为预约、未曝光：'+_frames_text(reservations)+'。',
           event='frame_reservations',cycle='N8',target='T',reservations=reservations)
    history.add(6,'目标锁定稳定，无取像。',event='frame_monitoring')
    history.add(7,'固定标定检查完成，无归档。',event='frame_monitoring')
    batch(8,'e',0,q)
    snapshot(9,'f','K1',q,'08:09')
    record(10,'g','另一目标Q的本周期帧已全部完成，与T分离：'+_frames_text(frame_list(2*pairs,pairs,protocol,target='Q')['archived_frames'])+'。',
           event='other_frame_archive',cycle='N8',target='Q')
    for at,text in ((11,'光学温度18℃，无曝光。'),(12,'数据盘健康，无归档变化。'),(13,'协议、标定及目标不变。')):
        history.add(at,text,event='frame_monitoring')
    record(14,'i','N8/T下一批请求排队，尚未实际曝光。',event='frame_request_queued',cycle='N8',target='T')
    history.add(15,'等待执行，无新增有效帧。',event='frame_monitoring')
    batch(16,'h',q,count)
    history.add(17,'未安排已列记录之外的曝光。',event='frame_monitoring')
    history.add(18,'协议和标定保持，无帧变化。',event='frame_monitoring')
    start = clock('08:19')
    failure = {'kind':'finish_marker_failure','exposed_seconds':0,'completed_s':start} if exposed is None else {
        'kind':'readout_failure' if exposed == PROTOCOLS[protocol][count%2] else 'exposure_interrupted',
        'frame':frame(count,protocol),'exposed_seconds':exposed,'started_s':start,'completed_s':start+exposed}
    if detailed:
        fields = frame_list(count,pairs,protocol)
        if exposed is None:
            message = f'仅结束标记在{story_timestamp(start)}失败，没有额外曝光'
        else:
            message = f"下一帧{_frame_text(failure['frame'])}实际曝光{exposed}秒后"+('完整曝光但读出归档失败' if failure['kind'] == 'readout_failure' else '中断')
            message += f'；本次曝光于{story_timestamp(start)}开始、{story_timestamp(failure["completed_s"])}终止'
        inventory = _inventory_text(fields)
        fields['failed_attempt'] = deepcopy(failure)
        occurred = failure['completed_s']
    else:
        fields,message,occurred = {},'归档计数接口只确认本次未增加有效帧；时间戳是服务报告生成/接收时刻，不是曝光起止',start+59
    record(19,'j','N8/T：'+message+'；临时积分已清空，已有持久成果全部保留。'+(inventory if detailed else ''),
           event='frame_failure',cycle='N8',target='T',new_archived_count=0,integral_cleared=True,occurred=occurred,received=start+59,**fields)
    record(20,'k','计划队列未执行，预约ID没有新增归档帧。',event='frame_queue_audit',cycle='N8',target='T')
    history.add(21,'取消所有待执行曝光，无自动重放。',event='frame_queue_cancelled')
    record(22,'l','调度显示重启，未归档积分清空，持久帧全部保留。',event='frame_display_failed')
    for at,text in ((23,'仪器恢复同一标定状态，没有补拍。'),(24,'目标及协议稳定，归档信号仍可用于本轮配对。')):
        history.add(at,text,event='frame_monitoring')
    snapshot(25,'m',loaded,0 if loaded == 'K0' else q,'08:04' if loaded == 'K0' else '08:09')
    record(26,'n','当前接口就绪，无新帧。',event='frame_monitoring')
    history.add(27,'无曝光或归档删除。',event='frame_monitoring')
    record(28,'o','再次读取旧N7最高组号帧归档：'+_frame_text(frame(2*pairs-1,protocol,cycle='N7'))+'，仍不属于N8。',
           event='old_frame_archive',cycle='N7',target='T')
    record(29,'p','温度18℃，无取像。',event='frame_monitoring')
    history.add(30,'待命，无帧变化。',event='frame_monitoring')
    task = task_shell('FM-S3-D2',index,current_input_group='FM-S3-D2')
    task.public = {'instruction':'继续周期N8对目标T的科学观测，提交下一项完整帧作业及依据。','cycle':'N8','target':'T','time_s':clock('09:00'),
        'max_steps':3,'state_fields':[],'record_catalog':list(CATALOG),'actions':[{'action':action,'description':
        '结束N8观测' if action == 'finish_observation' else ('完整信号曝光' if action.startswith('signal_') else '完整参考曝光')+action.rsplit('_',1)[1]+'，随后读出归档'} for action in MENU]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'archived_count':count,'temporary_integral_seconds':0,'registered_action':None}
    task.rubric = {'score':'correct atomic frame program with sufficient archive baseline/delta:100; useful actual but insufficient:30; otherwise:0',
                   'actual_batches':actual_batches,'failed_attempt':failure}
    return history.finish(task)


def reconstruct(history,current):
    count,records,batches,pairs,exposures = 0,{},[],None,None
    cycle,target = current['cycle'],current['target']
    scope = re.escape(cycle+'/'+target)
    frame_id = re.escape(cycle+'-'+target)+'-(?:signal|reference)-[1-9]\\d*'
    for text in paragraphs(history):
        protocol = re.match(rf'目标{re.escape(target)}、观测周期{re.escape(cycle)}，需(\d+)组，.*?'
                            r'协议[A-Z]：信号完整(\d+)秒、参考完整(\d+)秒。', text)
        if protocol:
            pairs,signal,reference = map(int,protocol.groups())
            exposures = {'signal':signal,'reference':reference}
            continue
        record = re.fullmatch(rf'(H\d{{2}})：(.*)该记录于({STORY_STAMP})收到。', text)
        if record is None:
            continue
        identifier,body,received = record.groups()
        received_s = microseconds(received) // 1_000_000
        initial = re.match(rf'{scope}尚未归档任何信号或参考帧，成功前缀0，', body)
        batch = re.match(rf'{scope}归档服务回执：', body)
        snapshot = re.match(rf'(?:保存|载入){scope}快照K[01]，原保存时间({STORY_STAMP})。', body)
        failure = body.startswith(cycle+'/'+target+'：') and '临时积分已清空，已有持久成果全部保留。' in body
        if not any((initial,batch,snapshot,failure)):
            continue
        inventory = re.search(r'(?:当时|当前)成功归档帧：(.*?)；', body)
        total = re.search(r'(?:实际持久成果总数|当时实际成功数)为(\d+)帧。', body)
        value = (len(re.findall(frame_id,inventory[1])) if inventory else
                 int(total[1]) if total else 0 if initial else None)
        if batch:
            completed = re.search(r'本批新增归档帧：(.*?)；',body)
            added = re.search(r'本批新增有效帧(\d+)帧。',body)
            delta = len(re.findall(frame_id,completed[1])) if completed else int(added[1]) if added else value
            if delta is None:
                raise ValueError('Missing the actual archive batch in the public receipt')
            count += delta
            batches.append({'id':identifier,'count':delta,'time_s':received_s})
        records[identifier] = {'count':value,'time_s':microseconds(snapshot[1])//1_000_000 if snapshot else received_s,
                               'useful':bool(initial or batch)}
    if pairs is None or exposures is None or len(batches) != 2:
        raise ValueError('Missing the public frame protocol or actual archive batches')
    action = 'finish_observation' if count == 2*pairs else ('signal' if count%2 == 0 else 'reference')
    if action != 'finish_observation':
        action += f'_{exposures[action]}s'
    return {'count':count,'pairs':pairs,'exposures':deepcopy(exposures),'batches':batches,'evidence':records,'correct_action':action}


def evaluate(facts,action,refs):
    if action != facts['correct_action'] or refs is None:
        return 0
    for ref in refs:
        proof = facts['evidence'].get(ref,{})
        if proof.get('count') is None:
            continue
        following = [batch for batch in facts['batches'] if batch['time_s'] > proof['time_s'] and batch['count'] > 0]
        if all(batch['id'] in refs for batch in following) and proof['count']+sum(batch['count'] for batch in following) == facts['count']:
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
        self.feedback = '观测接续决定与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for count in (1,2):
        for refs in combinations(CATALOG,count):
            if evaluate(facts,facts['correct_action'],refs) == 100:
                return {'action':facts['correct_action'],'evidence':list(refs)}
    raise ValueError('The next complete frame must be provable within two records')


def check_world(task,facts):
    if task.world != facts or task.initial != {'archived_count':facts['count'],'temporary_integral_seconds':0,'registered_action':None}:
        raise ValueError('Only complete read-out archived frames survive recovery')


def audit_cases(task,facts,solution):
    cases = []
    for action in MENU:
        for refs in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{'action':action,'evidence':refs}],evaluate(facts,action,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
