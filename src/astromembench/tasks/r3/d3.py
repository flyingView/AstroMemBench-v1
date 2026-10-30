"""FM-R3-D3: combine immutable byte-block checksums in the requested frame order."""
import re

from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

# Block assignment, lengths/checksums, current order, frame assignment, old order, frame result rounds and Z value.
CONFIGS = (
    (1,(1,2),(3,5),'AB',1,'AB',12,8,23),
    (2,(2,1),(4,7),'BA',2,'BA',22,4,10),
    (1,(3,2),(2,9),'AB',2,'BA',14,11,25),
    (2,(2,3),(1,8),'BA',2,'AB',25,9,14),
    (2,(1,2),(4,11),'BA',1,'BA',24,9,17),
    (2,(3,2),(0,5),'BA',2,'AB',21,12,11),
    (2,(2,3),(3,4),'BA',2,'BA',23,10,14),
    (1,(1,2),(8,6),'AB',1,'BA',12,16,24),
    (2,(2,2),(5,9),'AB',2,'AB',16,12,27),
    (2,(2,1),(9,0),'BA',2,'AB',21,4,12),
    (1,(2,2),(7,1),'AB',2,'AB',11,8,24),
    (2,(3,1),(8,4),'AB',1,'BA',18,7,26),
    (2,(1,3),(16,1),'BA',1,'BA',12,1,25),
    (2,(1,2),(13,7),'AB',1,'BA',25,11,14),
    (2,(3,1),(3,16),'BA',2,'AB',13,6,26),
    (1,(2,2),(11,11),'AB',1,'AB',23,2,12),
)


def checksum(values):
    h = 0
    for value in values:
        h = (2*h+value)%17
    return h


def frame_checksum(checksums,blocks,order):
    first,second = order
    return (checksums[first]*2**blocks[second]['length_bytes']+checksums[second])%17


def build(index):
    permutation,lengths,values,order,frame_permutation,old_order,frame_at,z_value,z_at = CONFIGS[index]
    blocks = {name:{'package':'S','length_bytes':length} for name,length in zip(('A','B'),lengths,strict=True)}
    payloads = {name:[0]*(length-1)+[value] for name,length,value in zip(('A','B'),lengths,values,strict=True)}
    block_jobs = {}
    for identifier,name in zip(('J03','J19'),('A','B') if permutation == 1 else ('B','A'),strict=True):
        block_jobs[identifier] = {'id':identifier,'block':name,**blocks[name],'energy':15,'checksum':checksum(payloads[name])}
    full_bytes = payloads[old_order[0]]+payloads[old_order[1]]
    z_bytes = [0]*(sum(lengths)-1)+[z_value]
    definitions = (
        ({'payload':'A+B','packages':{'A':'S','B':'S'},'order':old_order},full_bytes,frame_at),
        ({'payload':'Z','packages':{'Z':'Z'},'order':'内部原序'},z_bytes,z_at),
    )
    frame_jobs,frame_payloads,frame_finishes = {},{},{}
    for identifier,position in zip(('F04','F17'),(0,1) if frame_permutation == 1 else (1,0),strict=True):
        identity,raw,finish = definitions[position]
        frame_jobs[identifier] = {'id':identifier,**identity,'length_bytes':len(raw),'energy':30,
            'method':'full_payload_read','checksum':checksum(raw)}
        frame_payloads[identifier] = raw
        frame_finishes[identifier] = finish
    history = History()
    history.add(1,'正确报告本帧协议校验余数并节省计算能源；只计算，不实际发送或清理载荷。'
        '题内使用短模滚动校验，不声称密码抗碰撞安全，也不替代真实CRC；不同输入可能得到相同校验值。'
        '校验初值0，按块内原字节顺序逐字节d执行h←(2h+d) mod17，协议余数为0至16。字节值0至255，不按UTF文本字符计数。'
        '拼接H(X||Y)=(hX·2^LY+hY) mod17，LY是第二块完整字节长度；两个块各用一次，长度相加，0校验的块也保留长度。'
        '块A/B固定包均为S，内部字节顺序未变。历史分块校验可为新拼接序廉价组合；若整帧身份和顺序相同，也可直接复用已有整帧结果。'
        '顺序变化不改变块内容，允许用旧整帧加一个分块代数恢复另一分块，不强制双块读取或特定算法。'
        '历史另处理过载荷Z；整帧工单各自真实完整流读其载荷并付费，不依赖尚未返回的分块结果。所有历史只提供成功校验，没有免费载荷字节。'
        '当前给A/B身份、长度和拼接顺序，没有块校验、旧整帧值或字节，不能由长度免费重算。合法记忆检索不计环境动作。'
        '当前能源50，历史费用不从当前扣。get_steps的scope=A/B各耗15，all耗30，省略scope按all，仅返回请求块完整固定原始字节及递推规则。'
        '访问并校验不可免费访问的块是题内服务代理，不是现实能耗实测。重复成功请求仍收费；足额才扣，不足不调用、不扣、不返回字节但占额度。'
        'submit顶层value为单个有限JSON数值；同值整数、小数和科学计数可接受，布尔、非有限、多值、字符串或算式为格式错。'
        '首次有效数值立即结束；有限负值或17以上也是合法业务值，按结果判错，不当格式错允许枚举。h+17不等于协议余数字段h，不能对提交值再取模。'
        '须正确报告协议校验余数，并尽量减少当前实际计算耗能，无需说明推导路径。'
        '正确错误都反馈回传校验值已接收，记录已存档，不报正误。最多4次总调用，包含get_steps、submit、end、格式错及余额不足；end或额度耗尽即结束，费用不退。'
        'get_steps仅action及可选scope，submit仅action/value，end仅action；未知动作/scope、额外字段或结构错报请求格式无效，不扣能源但占额度。',
        event='checksum_reuse_protocol',initial_energy=50,costs={'A':15,'B':15,'all':30},max_actions=4,base=2,modulus=17)
    history.add(2,f'A/S为{lengths[0]} byte、B/S为{lengths[1]} byte，各自固定字节与内部顺序不变。',
        event='checksum_block_identities',blocks=blocks)
    block_starts = {'J03':6,'J19':19} if index < 6 else ({'J19':4,'J03':10} if index < 12 else {'J03':3,'J19':8})
    block_payments = block_starts if index < 12 else {'J19':12,'J03':16}
    block_finishes = block_starts if index < 6 else ({'J03':21,'J19':26} if index < 12 else {'J19':22,'J03':27})
    frame_starts = frame_finishes if index < 6 else ({'F04':3,'F17':5} if index < 12 else {'F04':3,'F17':6})
    frame_payments = frame_starts if index < 12 else {'F04':5,'F17':8}
    for at in range(3,29):
        for identifier,job in block_jobs.items():
            if at == block_starts[identifier]:
                text = f'{identifier}登记块{job["block"]}'
                if index < 6:
                    history.add(at,text+f'/S、{job["length_bytes"]} byte，实际已付15，校验成功，余数{job["checksum"]}。',
                        event='block_checksum_succeeded',**job)
                elif index < 12:
                    history.add(at,text+f'/S、{job["length_bytes"]} byte，实际已付15开始读取校验。',
                        event='block_checksum_started',**{k:v for k,v in job.items() if k != 'checksum'})
                else:
                    history.add(at,text+'。',event='block_checksum_job',id=identifier,block=job['block'])
            if index >= 12 and at == block_payments[identifier]:
                history.add(at,f'{identifier}补充包S、{job["length_bytes"]} byte，实际已付15开始读取校验。',
                    event='block_checksum_started',id=identifier,package='S',length_bytes=job['length_bytes'],energy=15)
            if index >= 6 and at == block_finishes[identifier]:
                history.add(at,f'{identifier}校验成功，余数{job["checksum"]}。',event='block_checksum_result',id=identifier,checksum=job['checksum'])
        for identifier,job in frame_jobs.items():
            packages = '、'.join(f'{payload}/{package}' for payload,package in job['packages'].items())
            if at == frame_starts[identifier]:
                text = f'{identifier}登记载荷'+('A与B拼接的整帧' if job['payload'] == 'A+B' else '独立载荷Z的整帧')
                detail = f'，包映射{packages}，顺序{job["order"]}，共{job["length_bytes"]} byte，实际已付30，独立完整流读该载荷计算校验'
                if index < 6:
                    history.add(at,text+detail+f'，成功余数{job["checksum"]}。',event='frame_checksum_succeeded',**job)
                elif index < 12:
                    history.add(at,text+detail+'。',event='frame_checksum_started',**{k:v for k,v in job.items() if k != 'checksum'})
                else:
                    history.add(at,text+'。',event='frame_checksum_job',id=identifier,payload=job['payload'])
            if index >= 12 and at == frame_payments[identifier]:
                history.add(at,f'{identifier}补充包映射{packages}、顺序{job["order"]}、共{job["length_bytes"]} byte，实际已付30，独立完整流读该载荷计算校验。',
                    event='frame_checksum_started',**{k:v for k,v in job.items() if k not in ('payload','checksum')})
            if index >= 6 and at == frame_finishes[identifier]:
                history.add(at,f'{identifier}完整流读校验成功，余数{job["checksum"]}。',event='frame_checksum_result',id=identifier,checksum=job['checksum'])
        if at == 15:
            history.add(at,'下一班拟压缩Z，尚未执行，不改变现有任何包；Z正在进行及已完成的处理仍使用原包。',event='checksum_compression_plan',payload='Z',executed=False)
    history.add(29,'本班作业日志已经归档。',event='checksum_logs_archived')
    history.add(30,'当前A/S、B/S两块字节及各自内部顺序未变。',event='checksum_blocks_unchanged',blocks=blocks)
    task = task_shell('FM-R3-D3',index,current_input_group=f'FM-R3-D3-{lengths[0]}-{lengths[1]}-{order}')
    task.public = {'instruction':f'使用A/S（{lengths[0]} byte）、B/S（{lengths[1]} byte），载荷内容及内部顺序未改变。本帧按{order}拼接，请提交协议校验余数。',
        'time_s':clock('09:00'),'blocks':blocks,'order':order,'formula':'初值h=0；逐字节h←(2h+d) mod17；H(X||Y)=(hX·2^LY+hY) mod17，余数0至16。',
        'max_steps':4,'state_fields':['energy'],'actions':[{'action':'get_steps','description':'付费读取所请求块完整字节；A/B各耗15，all耗30，省略scope按all。'},
            {'action':'submit','description':'提交顶层value为单个有限数值的协议校验余数。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':50}
    task.world = {'block_jobs':block_jobs,'frame_jobs':frame_jobs,'bytes':payloads,'frame_bytes':frame_payloads,
        'checksums':{j['block']:j['checksum'] for j in block_jobs.values()}}
    task.rubric = {'metric':'correct_frame_remainder_times_remaining_energy_over_50','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {'A':15,'B':15,'all':30}
    default_scope = 'all'
    insufficient_feedback = '计算能源不足，未调用校验服务'
    submitted_feedback = '回传校验值已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'get_steps':{'scope':{'type':'string','enum':['A','B','all'],'required':False,'default':'all'}},
        'submit':{'value':{'type':'number','required':True,'description':'单个有限JSON数值，值不再取模；不接受字符串、布尔、多值或算式。'}}})

    def computation_inputs(self,scope):
        names = ('A','B') if scope == 'all' else (scope,)
        return {name:{'bytes':self.task.world['bytes'][name]} for name in names},'每块初值h=0，按所给完整字节顺序执行h←(2h+d) mod17；H(X||Y)=(hX·2^LY+hY) mod17'

    def answer_credit(self,value):
        correct = value == frame_checksum(self.task.world['checksums'],self.task.public['blocks'],self.task.public['order'])
        self.facts['value_correct'] = correct
        return 100 if correct else 0


def reconstruct(history,current):
    blocks,frames = {},{}
    payload_names = {'A与B拼接':'A+B','独立载荷Z':'Z'}
    for text in paragraphs(history):
        match = re.fullmatch(r'(J\d+)登记块([^/。]+)(?:/([^、]+)、(\d+) byte，实际已付(\d+)(.*)|。)',text)
        if match:
            identifier,block,package,length,energy,tail = match.groups()
            job = blocks[identifier] = {'id':identifier,'block':block}
            if package is not None:
                job.update(package=package,length_bytes=int(length),energy=int(energy))
                success = re.fullmatch(r'，校验成功，余数(-?\d+)。',tail)
                if success:
                    job['checksum'] = int(success[1])
            continue
        match = re.fullmatch(r'(J\d+)补充包([^、]+)、(\d+) byte，实际已付(\d+)开始读取校验。',text)
        if match:
            identifier,package,length,energy = match.groups()
            blocks[identifier].update(package=package,length_bytes=int(length),energy=int(energy))
            continue
        match = re.fullmatch(r'(J\d+)校验成功，余数(-?\d+)。',text)
        if match:
            blocks[match[1]]['checksum'] = int(match[2])
            continue
        match = re.fullmatch(r'(F\d+)登记载荷(A与B拼接|独立载荷Z)的整帧。',text)
        if match:
            identifier,payload = match.groups()
            frames[identifier] = {'id':identifier,'payload':payload_names[payload]}
            continue
        match = re.fullmatch(r'(F\d+)(?:登记载荷(A与B拼接|独立载荷Z)的整帧，|补充)'
            r'包映射((?:[A-Z]+/[A-Z]+)(?:、[A-Z]+/[A-Z]+)*)[，、]顺序([^，、]+)[，、]共(\d+) byte，实际已付(\d+)，'
            r'独立完整流读该载荷计算校验(?:，成功余数(-?\d+))?。',text)
        if match:
            identifier,payload,packages,order,length,energy,value = match.groups()
            if payload is not None:
                frames[identifier] = {'id':identifier,'payload':payload_names[payload]}
            job = frames[identifier]
            job.update(packages=dict(pair.split('/') for pair in packages.split('、')),order=order,
                length_bytes=int(length),energy=int(energy),method='full_payload_read')
            if value is not None:
                job['checksum'] = int(value)
            continue
        match = re.fullmatch(r'(F\d+)完整流读校验成功，余数(-?\d+)。',text)
        if match:
            frames[match[1]]['checksum'] = int(match[2])
    if any(j['energy'] != 15 or not 0 <= j['checksum'] < 17 or j['length_bytes'] <= 0 for j in blocks.values()):
        raise ValueError('Block checksums must follow paid fixed-length byte reads')
    if any(j['energy'] != 30 or j['method'] != 'full_payload_read' or not 0 <= j['checksum'] < 17 for j in frames.values()):
        raise ValueError('Historical frames must be actual independently paid full-payload reads')
    checksums = {name:next(j['checksum'] for j in blocks.values() if (j['block'],j['package'],j['length_bytes']) ==
        (name,b['package'],b['length_bytes'])) for name,b in current['blocks'].items()}
    return {'block_jobs':blocks,'frame_jobs':frames,'checksums':checksums,'value':frame_checksum(checksums,current['blocks'],current['order'])}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('block_jobs','frame_jobs','checksums')):
        raise ValueError('Checksum reuse must retain each block and complete frame identity')
    for j in facts['block_jobs'].values():
        raw = task.world['bytes'][j['block']]
        if len(raw) != j['length_bytes'] or checksum(raw) != j['checksum']:
            raise ValueError('Paid block bytes must reproduce the historical checksum at the full length')
    for identifier,j in facts['frame_jobs'].items():
        raw = task.world['frame_bytes'][identifier]
        if len(raw) != j['length_bytes'] or checksum(raw) != j['checksum']:
            raise ValueError('Each archived frame needs a realizable independently processed payload')


def audit_cases(task,facts,solution):
    cases = []
    for prefix,energy in (([],50),([{'action':'get_steps','scope':'A'}],35),([{'action':'get_steps','scope':'B'}],35),
        ([{'action':'get_steps'}],20),([{'action':'get_steps','scope':'A'},{'action':'get_steps','scope':'B'}],20),
        ([{'action':'get_steps','scope':'A'}]*3,5),([{'action':'get_steps'}]*3,20),
        ([{'action':'get_steps'},{'action':'get_steps','scope':'B'}],5)):
        for value in (facts['value'],facts['value']+17):
            cases.append((prefix+[{'action':'submit','value':value}],100*energy/50 if value == facts['value'] else 0))
    wrong_order = frame_checksum(facts['checksums'],task.public['blocks'],task.public['order'][::-1])
    for value in (wrong_order,*(j['checksum'] for j in facts['frame_jobs'].values())):
        cases.append(([{'action':'submit','value':value}],100 if value == facts['value'] else 0))
    return cases+[([{'action':'submit','value':-1}],0),([{}]*3+solution,100),([{'action':'get_steps'}]*4,0)]
