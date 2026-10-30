"""FM-S3-D3: one real byte-transfer window after durable receiver recovery."""
from copy import deepcopy
from hashlib import sha256
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp
from ..common import History, clock, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds

BLOCK_BYTES = 8192
SOURCE_FILES = {identity:b''.join(bytes([block+offset])*BLOCK_BYTES for block in range(1,13))
                for identity,offset in ((('D','v2'),0),(('D','v1'),16),(('Q','v2'),32))}
CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
RANGES = tuple((start,count) for count in range(1,4) for start in range(1,14-count))
CONFIGS = ((0,0,3,2,'K0',2),(0,0,1,1,'K1',8),(8,8,2,1,'K1',9),
           (10,12,3,2,'K0',1),(11,12,2,2,'K0',4),(0,1,1,1,'K1',9),
           (0,1,3,1,'K1',10),(2,4,3,2,'K0',12),(6,9,3,1,'K1',5),
           (3,6,1,2,'K0',4),(4,5,2,1,'K1',12),(2,6,3,1,'K1',7),
           (8,10,3,2,'K0',11),(9,11,3,1,'K1',7),(10,11,2,1,'K1',15),(0,11,3,2,'K0',14))


def blocks_text(blocks):
    return '；'.join(f'块{block["block"]}的{block["bytes"]}字节均为字节值{block["content_byte"]}，'+
        story_timestamp(block['started_s'])+'开始，'+story_timestamp(block['committed_s'])+'持久提交'
        for block in blocks) or '本批无新增块'


def build(index):
    q,prefix,window,failed,loaded,offset = CONFIGS[index]
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()

    def record(at,letter,text,**facts):
        history.add(at,ids[letter]+'：'+text,record_id=ids[letter],**facts)

    def snapshot(at,letter,name,position,saved):
        record(at,letter,('载入' if at == 25 else '保存')+f'本地D/v2快照{name}，原保存时间{saved}，当时真实游标{position}、{8*position} KiB；只读显示，不重新获取接收清单，不传新块。',
               event='transfer_snapshot',file='D',version='v2',snapshot=name,saved_s=clock(saved),prefix=position,committed_kib=8*position)

    def batch(at,letter,before,after):
        start = clock(f'08:{at:02d}')
        blocks = [{'block':block,'bytes':BLOCK_BYTES,'content_byte':block,'started_s':start+4*(block-before-1),'committed_s':start+4*(block-before)}
                  for block in range(before+1,after+1)]
        record(at,letter,'D/v2接收方逐块持久提交回执：'+blocks_text(blocks)+f'；完整前缀{after}、{8*after} KiB，清单仍未封存。空批仅核对，无额外提交。',
               event='transfer_committed',file='D',version='v2',blocks=blocks,prefix=after,committed_kib=8*after,sealed=False,
               occurred=start+4*(after-before),received=start+59)

    history.add(1,'文件D版本v2完整源文件96 KiB，共12块每块8192字节，块i为字节值i重复8192次；D/v1块i为i+16，Q/v2块i为i+32，均有独立完整12块源文件。'
        '文件/版本/块号精确绑定，接收方只接当前前缀之后连续新块，源端始终完整、不删除。过去批次协商最大12块，传输速率2 KiB/s，每块4秒并按序持久提交；无不确定ACK或隐藏在途块。'
        '当前恢复窗口协商w=1/2/3且当前再次显示，菜单所有1/2/3块范围都可选。合法send必须从当前前缀+1开始、count≤w且不越12，否则原子拒绝0新增。'
        '12块到齐不自动封存；全满且未封存才可finalize，成功只写持久封存标记，其余拒绝。历史发送只提交块，不封存；界面恢复不回滚接收成果、不自动补发。'
        '当前首次格式合法业务操作真实执行且结束唯一窗口，较小合法范围也推进成果，无查询/试传后再答。send成功n块用4n秒加1秒接收确认；原子拒绝或封存各1秒，格式错不进入业务、不推进业务钟。'
        'send精确字段action/start/count/evidence；finalize精确action/evidence，整数不含bool。证据为null或非空H01—H16数组，重复先去重最多2种。'
        '最多3次总调用含格式错，原生检索不计额度。null合法且仍执行真实业务；新增回执不加入过去证据目录，不能事后补证。'
        '准确缓存、成功或明确无变化回执都能证明当前前缀；被后续提交推进超过的旧实际前缀、纯缓存、计划、协商、其他版本/文件分清，两个累计不能相加。',
        event='transfer_protocol',file='D',version='v2',block_bytes=BLOCK_BYTES,block_count=12,
        source_catalog=[{'file':name,'version':version,'block_byte_offset':offset,'block_count':12,'block_bytes':BLOCK_BYTES}
                        for (name,version),offset in ((('D','v2'),0),(('D','v1'),16),(('Q','v2'),32))])
    record(2,'a','D/v2本次尚无已提交块，前缀0，清单未封存，源端12块完整存在。',event='transfer_initial',file='D',version='v2',prefix=0,committed_kib=0,sealed=False)
    record(3,'b','D/v1旧版本已完整提交12块，非D/v2。',event='other_transfer_completed',file='D',version='v1',prefix=12)
    snapshot(4,'c','K0',0,'08:04')
    record(5,'d','D/v2全部1—12块已编号并加入发送计划，尚无实际提交。',event='transfer_planned',file='D',version='v2',planned_blocks=list(range(1,13)))
    history.add(6,'源端完整性检查完成，无传输。',event='transfer_monitoring')
    history.add(7,'历史批次接收容量12块协商完成，没有数据提交。',event='transfer_monitoring')
    batch(8,'e',0,q)
    snapshot(9,'f','K1',q,'08:09')
    record(10,'g','Q/v2另文件12块已提交，与D/v2分离。',event='other_transfer_completed',file='Q',version='v2',prefix=12)
    for at,text in ((11,'链路保持，无新数据。'),(12,'源端版本v2不变，无覆盖。'),(13,'接收方未清理或回滚。')):
        history.add(at,text,event='transfer_monitoring')
    record(14,'i','D/v2后续计划请求排队但未提交，计划最大块号12不表示完成。',event='transfer_request_queued',file='D',version='v2')
    history.add(15,'等待实际传输，没有隐蔽在途块。',event='transfer_monitoring')
    batch(16,'h',q,prefix)
    history.add(17,'后续队列全部撤销，无自动补发。',event='transfer_queue_cancelled')
    history.add(18,'接收前缀没有变化。',event='transfer_monitoring')
    if failed == 2:
        record(19,'j','D/v2'+('全文件封存' if prefix == 12 else '下一窗口')+f'请求失败，提交0新块，封存标记未写；接收端完整核对前缀{prefix}、{8*prefix} KiB，仍未封存。',
               event='transfer_failure',file='D',version='v2',prefix=prefix,committed_kib=8*prefix,sealed=False,new_blocks=0)
    else:
        record(19,'j','D/v1旧版本请求失败，旧前缀仍12；D/v2无提交或封存。',event='other_transfer_failure',file='D',version='v1',prefix=12)
    record(20,'k',f'D/v2当前恢复窗口协商最多{window}块，协商本身不传数据。',event='transfer_window_agreed',file='D',version='v2',window_blocks=window)
    history.add(21,'源端12块保持，接收端无撤销。',event='transfer_monitoring')
    record(22,'l','本地调度显示故障重启，接收端持久块未回滚，无自动重发。',event='transfer_display_failed')
    history.add(23,'链路与传输接口恢复正常，没有业务提交。',event='transfer_monitoring')
    history.add(24,'D/v2内容、版本与当前协商窗口未改变。',event='transfer_monitoring')
    snapshot(25,'m',loaded,0 if loaded == 'K0' else q,'08:04' if loaded == 'K0' else '08:09')
    record(26,'n','回传接口就绪，无新块。',event='transfer_monitoring')
    history.add(27,'所有等待队列为空。',event='transfer_monitoring')
    record(28,'o','旧D/v1最高块号12档案再次读取，身份仍v1。',event='other_transfer_archive',file='D',version='v1',prefix=12)
    record(29,'p','链路温度18℃，无业务数据。',event='transfer_monitoring')
    history.add(30,'待命，无块提交、删除或封存；前述失败后没有封存成功事件。',event='transfer_monitoring')
    task = task_shell('FM-S3-D3',index,current_input_group=f'FM-S3-D3-w{window}')
    task.public = {'instruction':f'继续D/v2的数据回传；本次窗口最多{window}块。提交下一项真实作业及依据。',
        'file':'D','version':'v2','window_blocks':window,'time_s':clock('09:00'),'max_steps':3,'state_fields':[],'record_catalog':list(CATALOG),
        'actions':[{'action':'send','start':start,'count':count,'description':f'实际发送D/v2块{start}…{start+count-1}，共{8*count} KiB'} for start,count in RANGES]+
                  [{'action':'finalize','description':'封存D/v2接收清单，不传新块'}]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    received = SOURCE_FILES[('D','v2')][:prefix*BLOCK_BYTES]
    task.initial = {'prefix':prefix,'sealed':False,'received_bytes':len(received),'received_sha256':sha256(received).hexdigest(),'time_s':clock('09:00')}
    task.rubric = {'score':'100*actual new blocks/min(window,remaining)*evidence factor; full prefix finalize:100*factor; factor sufficient1/old actual0.2/none0'}
    return history.finish(task)


def _transfer_blocks(text,prefix,block_bytes,rate):
    if text == '本批无新增块':
        return
    previous_block = previous_end = None
    for part in text.split('；'):
        match = re.fullmatch(rf'块(\d+)的(\d+)字节均为字节值(\d+)，({STORY_STAMP})开始，({STORY_STAMP})持久提交',part)
        if not match:
            raise ValueError('Committed blocks must report actual contents and durable submission clocks')
        block,size,value = map(int,match.groups()[:3])
        start,end = map(seconds,match.groups()[3:])
        if size != block_bytes or value != block or not 1 <= block <= prefix:
            raise ValueError('Each committed block must match the public source bytes and prefix')
        if end <= start or (end-start)*rate*1024 != size or previous_end is not None and start != previous_end:
            raise ValueError('Committed block clocks must follow the public transfer rate')
        if previous_block is not None and block != previous_block+1:
            raise ValueError('A committed batch must contain consecutive blocks')
        previous_block,previous_end = block,end
    if previous_block != prefix:
        raise ValueError('A committed batch must end at its reported full prefix')


def reconstruct(history,current):
    prefix,records = None,{}
    block_count = block_bytes = rate = None
    scope = re.escape(current['file']+'/'+current['version'])
    for text in paragraphs(history):
        if match := re.match(re.escape('文件'+current['file']+'版本'+current['version'])+
                r'完整源文件(\d+) KiB，共(\d+)块每块(\d+)字节，块i为字节值i重复(\d+)次；',text):
            kib,block_count,block_bytes,repeated = map(int,match.groups())
            speed = re.search(r'传输速率(\d+) KiB/s，每块(\d+)秒并按序持久提交',text)
            if not speed or not block_count or repeated != block_bytes or kib*1024 != block_count*block_bytes:
                raise ValueError('Transfer source size must follow the public block protocol')
            rate,duration = map(int,speed.groups())
            if rate <= 0 or duration*rate*1024 != block_bytes:
                raise ValueError('The public transfer rate must match each block duration')
            continue
        numbered = re.fullmatch(r'(H\d{2})：(.+)',text)
        if numbered is None:
            continue
        identifier,body = numbered.groups()
        actual,current_state = False,False
        if re.fullmatch(scope+r'本次尚无已提交块，前缀0，清单未封存，源端12块完整存在。',body):
            value,kib,actual,current_state = 0,0,True,True
        elif match := re.fullmatch(r'(?:载入|保存)本地'+scope+r'快照K\d+，原保存时间\d{2}:\d{2}，当时真实游标(\d+)、(\d+) KiB；只读显示，不重新获取接收清单，不传新块。',body):
            value,kib = map(int,match.groups())
        elif match := re.fullmatch(scope+r'接收方逐块持久提交回执：(.+)；完整前缀(\d+)、(\d+) KiB，清单仍未封存。空批仅核对，无额外提交。',body):
            value,kib = map(int,match.groups()[1:])
            if block_bytes is None:
                raise ValueError('Transfer recovery requires the public source protocol')
            _transfer_blocks(match[1],value,block_bytes,rate)
            actual,current_state = True,True
        elif match := re.fullmatch(scope+r'(?:全文件封存|下一窗口)请求失败，提交0新块，封存标记未写；接收端完整核对前缀(\d+)、(\d+) KiB，仍未封存。',body):
            value,kib = map(int,match.groups())
            current_state = True
        else:
            continue
        if block_count is None or not 0 <= value <= block_count or value*block_bytes != kib*1024:
            raise ValueError('A reported prefix and byte count must match the public source protocol')
        if current_state:
            prefix = value if prefix is None else max(prefix,value)
        records[identifier] = {'prefix':value,'actual':actual}
    if prefix is None:
        raise ValueError('Transfer recovery requires an actual receiver prefix')
    if any(record['prefix'] > prefix for record in records.values()):
        raise ValueError('Actual receiver history cannot account for its true saved prefixes')
    sufficient = [ref for ref,record in records.items() if record['prefix'] == prefix]
    earlier = [ref for ref,record in records.items() if record['actual'] and record['prefix'] < prefix]
    return {'prefix':prefix,'window':current['window_blocks'],'sufficient':sufficient,'earlier':earlier}


def evidence_factor(facts,refs):
    if refs is None:
        return 0
    return 1 if set(refs)&set(facts['sufficient']) else 0.2 if set(refs)&set(facts['earlier']) else 0


def evaluate(facts,operation,refs):
    factor = evidence_factor(facts,refs)
    if operation['action'] == 'finalize':
        return 100*factor if facts['prefix'] == 12 else 0
    if operation['start'] != facts['prefix']+1 or operation['count'] > min(facts['window'],12-facts['prefix']):
        return 0
    return 100*operation['count']/min(facts['window'],12-facts['prefix'])*factor


class Runtime(TaskRuntime):
    action_contract = ActionContract(fields=('action','start','count'),parameters={'*':{'evidence':{'type':['array','null'],'required':True,
        'items':{'type':'string','enum':list(CATALOG)},'minItems':1,'description':'null或非空H01—H16编号数组；重复先去重，最多2种。'}}})

    def __init__(self,task):
        super().__init__(task)
        self.sources = SOURCE_FILES.copy()
        self.receiver = self.sources[('D','v2')][:task.initial['prefix']*BLOCK_BYTES]

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        result = super().observation()
        result['time_s'] = self.state['time_s']
        result['current_time'] = story_timestamp(self.state['time_s'])
        return result

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or not isinstance(action.get('action'),str):
            self.invalid()
            return
        name = action['action']
        if name == 'send':
            valid = (set(action) == {'action','start','count','evidence'} and type(action['start']) is int and type(action['count']) is int
                     and (action['start'],action['count']) in RANGES)
        else:
            valid = name == 'finalize' and set(action) == {'action','evidence'}
        if not valid:
            self.invalid()
            return
        refs = action['evidence']
        if refs is not None and (not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in CATALOG for ref in refs) or len(set(refs)) > 2):
            self.invalid()
            return
        refs = None if refs is None else list(dict.fromkeys(refs))
        before = len(self.receiver)//BLOCK_BYTES
        new_blocks,sealed_now = 0,False
        if name == 'send' and action['start'] == before+1 and action['count'] <= min(self.task.public['window_blocks'],12-before):
            first,last = before*BLOCK_BYTES,(before+action['count'])*BLOCK_BYTES
            transmitted = self.sources[('D','v2')][first:last]
            self.receiver += transmitted
            new_blocks = len(transmitted)//BLOCK_BYTES
            self.feedback = f'D/v2已新增提交块{before+1}…{before+new_blocks}，共{8*new_blocks} KiB。'
        elif name == 'finalize' and before == 12 and not self.state['sealed']:
            self.state['sealed'] = sealed_now = True
            self.feedback = 'D/v2接收清单已封存。'
        else:
            self.feedback = '本窗口没有新增提交。'
        self.state.update(prefix=len(self.receiver)//BLOCK_BYTES,received_bytes=len(self.receiver),received_sha256=sha256(self.receiver).hexdigest(),
                          time_s=self.state['time_s']+4*new_blocks+1)
        factor = evidence_factor(self.task.world,refs)
        score = 100*new_blocks/min(self.task.public['window_blocks'],12-before)*factor if before < 12 else 100*factor if sealed_now else 0
        self.facts = {'operation':{key:value for key,value in action.items() if key != 'evidence'},'references':refs,
                      'new_blocks':new_blocks,'new_bytes':new_blocks*BLOCK_BYTES,'sealed_now':sealed_now}
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    operation = {'action':'finalize'} if facts['prefix'] == 12 else {'action':'send','start':facts['prefix']+1,'count':min(facts['window'],12-facts['prefix'])}
    return {**operation,'evidence':[facts['sufficient'][0]]}


def check_world(task,facts):
    received = SOURCE_FILES[('D','v2')][:facts['prefix']*BLOCK_BYTES]
    if task.world != facts or task.initial != {'prefix':facts['prefix'],'sealed':False,'received_bytes':len(received),
        'received_sha256':sha256(received).hexdigest(),'time_s':clock('09:00')}:
        raise ValueError('Receiver byte contents and durable prefix must match the exact current file/version')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        operation = {key:row[key] for key in ('action','start','count') if key in row}
        for refs in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{**operation,'evidence':refs}],evaluate(facts,operation,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
