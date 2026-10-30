"""FM-S2-D3: production image identity and independently validated full pipelines."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'E{i:02d}' for i in range(1,13))
PIPELINES = tuple(encoder+e+f for encoder in 'rcd' for e in '01' for f in '01')
CAPACITY = {'r':8,'c':16,'d':32}
CHECKSUMS = {'v1':'6b93c8d1','v2':'a7420e5f'}
CAPABILITIES = {
    'K':PIPELINES,'L':('r00','r01','r10','r11','c00','c01','c10','c11'),
    'M':('r00','r01','c00','c01','d00','d01'),'N':('r00','r10','c00','c10','d00','d10'),
    'P':('r00','r01','r10','r11','c00','c01','d00','d01'),
    'Q':('r00','r01','r10','r11','c00','c10','d00','d10'),
    'R':('r00','c00','d00','r11'),
    'S':('r00','r01','r10','r11','c00','c01','c10','c11','d00','d01','d10'),
    'T':('r00','r11','c00','c11','d00','d11'),'U':(),
}
# Contract, actual chain, identity receipt round, late offline image, spare
# regression result, explicit job identities, menu, and evidence addresses.
CONFIGS = (
    ('cd','11',16,'S:S',20,'v2',None,('J42','J09'),(4,12,1,9,6,3,11,7,13,2,10,5,8),(5,10,11,6,8,1,2,12,4,9,7,3)),
    ('rcd','11',8,'S:R',20,'v1',None,('J42','J17'),(11,3,7,1,8,5,12,6,10,13,2,4,9),(9,12,2,7,3,1,10,4,8,11,5,6)),
    ('rcd','1*',16,'S:P',20,'v2',None,('J17','J31'),(8,1,12,5,11,4,9,3,6,2,13,10,7),(2,5,10,3,4,12,6,8,11,9,1,7)),
    ('cd','*1',16,'S:Q',16,'v1',None,('J09','J42'),(3,10,6,13,1,8,4,11,7,12,5,2,9),(3,12,5,10,11,9,7,6,2,1,4,8)),
    ('rcd','00',8,'S:R',16,'v1',None,('J31','J42'),(12,6,4,8,2,11,7,5,9,1,10,13,3),(6,2,11,10,8,5,1,12,4,3,7,9)),
    ('d','10',32,'S:S',20,'v2',None,('J09','J17'),(1,8,5,11,6,2,10,9,3,7,4,12,13),(11,2,3,1,10,8,4,6,7,9,5,12)),
    ('d','11',24,'W:S',16,'v2',None,('J31','J09'),(13,7,3,10,2,6,12,5,1,11,8,9,4),(10,6,5,3,7,2,9,4,11,1,8,12)),
    ('cd','11',16,'B:M',20,'v1',None,('J17','J42'),(4,9,12,2,8,11,1,6,13,5,7,3,10),(7,8,10,9,6,4,5,2,11,3,12,1)),
    ('cd','11',16,'R:M',20,'v1',None,('J09','J31'),(7,11,5,1,12,3,8,10,4,9,2,13,6),(1,9,10,3,11,7,6,8,12,5,4,2)),
    ('cd','1*',16,'L:N',20,'v2','M',('J31','J42'),(11,6,1,13,7,10,4,8,3,2,9,5,12),(3,6,9,7,4,10,8,11,12,1,2,5)),
    ('rcd','*1',8,'L:T',16,'v1','Q',('J09','J17'),(5,3,10,7,9,1,12,2,11,6,8,13,4),(9,1,2,11,6,4,10,8,7,3,12,5)),
    ('rcd','00',8,'F:K',16,'v1',None,('J17','J31'),(3,7,11,5,10,12,6,9,1,4,13,2,8),(3,1,6,12,5,2,10,4,9,8,11,7)),
    ('cd','*1',16,'L:P',16,'v1','L',('J31','J42'),(7,9,1,12,5,8,11,4,2,6,13,3,10),(1,9,3,6,5,4,2,11,7,10,8,12)),
    ('rcd','1*',8,'R:Q',20,'v1',None,('J17','J09'),(4,6,11,2,10,13,8,3,12,5,1,7,9),(12,4,7,10,5,9,3,6,8,2,11,1)),
    ('rcd','11',9,'L:R',20,'v1','S',('J17','J42'),(11,1,6,10,8,3,7,12,4,13,9,5,2),(7,2,11,4,5,1,6,10,12,8,9,3)),
    ('d','01',32,'B:N',20,'v2',None,('J31','J09'),(5,12,9,13,4,10,1,7,3,11,2,6,8),(1,9,11,8,5,3,7,6,12,10,2,4)),
)


def identity(image,hardware):
    return {'image':image,'checksum':CHECKSUMS[image],'hardware':hardware}


def describe(entity):
    return f'镜像{entity["image"]}、校验值{entity["checksum"]}、处理模块{entity["hardware"]}'


def build(index):
    encoders,flags,size,chain,identity_round,late_image,candidate,job_names,menu,ids = CONFIGS[index]
    kind,code = chain.split(':')
    identifiers = [f'E{n:02d}' for n in ids]
    hardware = 'H2' if kind == 'L' else 'H1'
    jobs = {job:identity(image,hardware) for image,job in zip(('v1','v2'),job_names,strict=True)}
    history = History()
    history.add(1,'本轮回传一个不可拆逻辑块。r原样、c游程、d差分编码的单块输入上限分别8/16/32 KiB，这是本题缓冲接口能力，不是假定压缩比。'
        '编码后两位e/f分别为加密、纠错的关闭0或开启1。12种完整管线均为真实选择，另有H保持；不得分块或更换数据族。'
        '接收合同C给允许编码器，e/f为0、1或*（任一均可），大小n必须≤所用编码器单块上限，等号可用。'
        '业务正确须活动镜像当前已授权完整组合、编码器/标志满足合同且容量足够，所有合格组合均接受，不强制最高压缩或全部保护。'
        '单个编码、加密或纠错功能能启动，不证明组合管线通过；完整组合证书不得由单项拼接。链路、供电和接收条件保障，不测窗口、能耗或确认删除。'
        '两镜像保留在各自槽；下载和文件安装不是生产激活。离线验收在隔离实例完成，只证明指定校验值和模块配置的能力，不改变或证明生产活动身份。'
        '同配置未受影响的证书仍有效；v2服务自身故障只撤销v2授权，换共享处理模块使两镜像旧模块能力证书均不适用。'
        '故障后修复或重启不等于验证，同值重新通过也不使故障前旧证复活；活动切换再回滚不使旧活动回执复活，但未改变的离线能力不因切换失效。'
        '业务选择需分别引用当前活动镜像身份与该镜像当前完整管线能力；无任何合格管线才应H保持，仍须两项事实。'
        '证据按内容覆盖，目录内无效证据不抹已有支持，不评分解释或唯一轨迹。select恰含action、option数字字符串及evidence目录E01—E12数组；可空，重复先去重后最多2不同ID。'
        '仅单字段action=end提前结束。最多3次总调用，格式错只指出结构且不处理块；目录内失效或不足依据仍是合法业务提交。'
        '首次合法选择立即实际处理且终局，反馈“回传管线与依据已存档。”；错管线无合格块、不可试编重选或重投，无免费读取活动镜像或重新验收入口。'
        '当前单块期间无额外激活、回滚、换模块或授权变化，原生记忆检索不计环境调用。',event='pipeline_protocol')
    history.add(2,identifiers[0]+'：生产活动确认，'+describe(identity('v1','H1'))+'。',record_id=identifiers[0],event='production_identity_confirmed',**identity('v1','H1'))

    def certify(at,slot,image,configuration,capability,*,job_id=None):
        entity = identity(image,configuration)
        allowed = list(CAPABILITIES[capability])
        label = '' if index >= 12 and job_id else describe(entity)+'，'
        job_text = f'工单{job_id}，' if job_id else ''
        status = '完整隔离验收通过' if allowed else '复位完成但仍无新验证，全部管线未获准'
        permissions = '完整获准管线为'+'、'.join(allowed) if allowed else '完整获准管线为空'
        history.add(at,identifiers[slot]+f'：{job_text}{label}{status}；{permissions}。离线验收，不确认生产活动身份。',
            record_id=identifiers[slot],event='pipeline_certificate',pipelines=allowed,
            **({'job_id':job_id} if job_id else {}),**({} if index >= 12 and job_id else entity))

    certify(3,1,'v1','H1','K')
    history.add(5,'候选v2镜像已下载至独立镜像槽，校验值'+CHECKSUMS['v2']+'；没有生产激活。',event='pipeline_image_downloaded',image='v2',checksum=CHECKSUMS['v2'])
    history.add(7,identifiers[2]+'：候选v2文件安装完成、校验值'+CHECKSUMS['v2']+'；明确尚未激活。',record_id=identifiers[2],event='pipeline_candidate_installed',image='v2',checksum=CHECKSUMS['v2'])
    certify(10,3,'v2','H1',candidate if kind == 'L' else code)
    history.add(12,identifiers[4]+'：分别启动r/c/d三个编码器；没有验证额外的加密/纠错组合，不构成任何完整管线证书。',record_id=identifiers[4],event='encoders_started_separately')
    history.add(14,'登记两份后续完整离线回归工单：'+'；'.join(f'{job}：{describe(entity)}，范围为全部12完整管线' for job,entity in jobs.items())+
        '。工单只是安排，H2工单须等实际换模块后执行；登记不安装模块、不切换镜像，也不产生授权。',event='pipeline_jobs_registered',jobs=jobs)
    for at,slot in ((16,5),(20,6)):
        if kind == 'B':
            image = 'v2' if at == 16 else 'v1'
            history.add(at,identifiers[slot]+('：已实际激活v2；' if at == 16 else '：已实际回滚v1，其原镜像和H1未变；')+
                describe(identity(image,'H1'))+'现承担生产处理。',record_id=identifiers[slot],event='production_identity_confirmed',**identity(image,'H1'))
        elif at == identity_round:
            image = 'v1' if kind in 'WL' else 'v2'
            status = '候选切换尚未实施，v1持续承担生产' if image == 'v1' else 'v2已实际激活并承担生产'
            history.add(at,identifiers[slot]+f'：{status}；'+describe(identity(image,'H1'))+'。',record_id=identifiers[slot],event='production_identity_confirmed',**identity(image,'H1'))
        elif kind in 'WL' or at == 16:
            history.add(at,identifiers[slot]+'：登记并批准v2后续切换计划，尚未执行；本记录不是活动状态检查。',record_id=identifiers[slot],event='pipeline_activation_planned',image='v2')
        else:
            history.add(at,identifiers[slot]+'：非活动v1镜像文件校验完成、校验值'+CHECKSUMS['v1']+'；不是生产状态检查，不新增管线验收。',
                record_id=identifiers[slot],event='inactive_image_file_checked',image='v1',checksum=CHECKSUMS['v1'])
    if kind in 'FR':
        history.add(22,identifiers[7]+'：v2服务实际故障；'+describe(identity('v2','H1'))+'完整获准管线现为空，全部受限。本回执只报告v2服务，不确认生产身份。',
            record_id=identifiers[7],event='pipeline_service_fault',pipelines=[],**identity('v2','H1'))
    elif kind == 'L':
        history.add(22,identifiers[7]+'：共享处理模块已实际换为H2，两镜像H1能力证书均不再适用；镜像未切换，'+describe(identity('v1','H2'))+'仍承担生产。',
            record_id=identifiers[7],event='pipeline_module_replaced',**identity('v1','H2'))
    else:
        history.add(22,identifiers[7]+'：两镜像槽的存储完整性检查完成，不提供生产活动身份或管线能力。',record_id=identifiers[7],event='image_storage_checked')
    if kind == 'R':
        history.add(23,'v2修复操作已完成，但尚未验收、授权尚未恢复；没有生产身份检查。',event='pipeline_repaired_without_validation',image='v2')
    for at,slot,image in ((24,8,'v1' if late_image == 'v2' else 'v2'),(27,9,late_image)):
        capability = (code if image == 'v1' else candidate) if kind == 'L' else 'K' if image == 'v1' else 'U' if kind == 'F' else code
        certify(at,slot,image,hardware,capability,job_id=job_names[0 if image == 'v1' else 1])
    history.add(28,identifiers[10]+'：上一个数据块已收讫，当前块尚未提交。',record_id=identifiers[10],event='previous_block_received')
    history.add(29,identifiers[11]+'：v3下载计划尚未执行，不更改当前镜像。',record_id=identifiers[11],event='next_image_download_planned')
    history.add(30,'天线、电源和存储自检正常，没有新的处理验证。',event='pipeline_hardware_ready')
    base = [{'description':f'{pipeline}：以'+{'r':'原样','c':'游程','d':'差分'}[pipeline[0]]+f'编码当前整块，加密={pipeline[1]}，纠错={pipeline[2]}',
             'operation':{'pipeline':pipeline}} for pipeline in PIPELINES]
    base.append({'description':'H：保持待机，不处理当前块','operation':{'hold':True}})
    task = task_shell('FM-S2-D3',index)
    task.public = {'instruction':f'当前不可拆数据块为{size} KiB，接收合同允许编码器'+ '、'.join(encoders)+f'，加密e={flags[0]}、纠错f={flags[1]}，*表示任一值。请选择完整管线或保持，并附依据。',
        'allowed_encoders':list(encoders),'encryption':flags[0],'error_correction':flags[1],'block_kib':size,'capacity_kib':CAPACITY,
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],'actions':fixed_options(base[n-1] for n in menu)}
    task.initial = {'attempts':[],'qualified_block_delivered':False}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'correct pipeline or hold: 50 for current production identity and 50 for that image current complete pipeline capability; wrong business 0'}
    return history.finish(task)


ENTITY = r'镜像(v\d+)、校验值([0-9a-f]+)、处理模块(H\d+)'


def _entity(text):
    match = re.fullmatch(ENTITY,text)
    if match is None:
        raise ValueError('A pipeline receipt must state its image, checksum and module')
    return dict(zip(('image','checksum','hardware'),match.groups(),strict=True))


def _pipeline_record(text):
    if match := re.fullmatch(r'生产活动确认，('+ENTITY+r')。',text):
        return {'event':'production_identity_confirmed',**_entity(match[1])}
    if match := re.fullmatch(r'(已实际激活(v\d+)|已实际回滚(v\d+)，其原镜像和(H\d+)未变)；('+ENTITY+r')现承担生产处理。',text):
        entity = _entity(match[5])
        if entity['image'] != (match[2] or match[3]) or match[4] and entity['hardware'] != match[4]:
            raise ValueError('The actual activation or rollback must match its production identity')
        return {'event':'production_identity_confirmed',**entity}
    if match := re.fullmatch(r'(候选切换尚未实施，(v\d+)持续承担生产|(v\d+)已实际激活并承担生产)；('+ENTITY+r')。',text):
        entity = _entity(match[4])
        if entity['image'] != (match[2] or match[3]):
            raise ValueError('The confirmed production image must match its stated activation status')
        return {'event':'production_identity_confirmed',**entity}
    if match := re.fullmatch(r'共享处理模块已实际换为(H\d+)，两镜像(H\d+)能力证书均不再适用；镜像未切换，('+ENTITY+r')仍承担生产。',text):
        entity = _entity(match[3])
        if entity['hardware'] != match[1]:
            raise ValueError('The installed replacement must match the reported production module')
        return {'event':'pipeline_module_replaced','previous_hardware':match[2],**entity}
    if match := re.fullmatch(r'(v\d+)服务实际故障；('+ENTITY+r')完整获准管线现为空，全部受限。本回执只报告(v\d+)服务，不确认生产身份。',text):
        entity = _entity(match[2])
        if entity['image'] != match[1] or entity['image'] != match[6]:
            raise ValueError('The service fault and its restriction must identify the same image')
        return {'event':'pipeline_service_fault','pipelines':[],**entity}
    match = re.fullmatch(r'(?:工单(J\d+)，)?(?:('+ENTITY+r')，)?'
        r'(完整隔离验收通过|复位完成但仍无新验证，全部管线未获准)；'
        r'完整获准管线(?:为([rcd][01]{2}(?:、[rcd][01]{2})*)|(为空))。离线验收，不确认生产活动身份。',text)
    if match is None:
        return {}
    job_id,identity_text,_,_,_,status,allowed,empty = match.groups()
    pipelines = allowed.split('、') if allowed else []
    if (status == '完整隔离验收通过') != bool(pipelines) or len(set(pipelines)) != len(pipelines):
        raise ValueError('Complete pipeline acceptance must agree with its explicit permission set')
    if not job_id and not identity_text:
        raise ValueError('An offline certificate needs an image identity or a registered job')
    return {'event':'pipeline_certificate','pipelines':pipelines,
        **({'job_id':job_id} if job_id else {}),**(_entity(identity_text) if identity_text else {})}


def _pipeline_jobs(text):
    match = re.fullmatch(r'登记两份后续完整离线回归工单：(.+)。工单只是安排，H2工单须等实际换模块后执行；登记不安装模块、不切换镜像，也不产生授权。',text)
    if match is None:
        return None
    jobs = {}
    for entry in match[1].split('；'):
        job = re.fullmatch(r'(J\d+)：('+ENTITY+r')，范围为全部12完整管线',entry)
        if job is None or job[1] in jobs:
            raise ValueError('Each offline job must bind one image and the complete pipeline scope')
        jobs[job[1]] = _entity(job[2])
    if len(jobs) != 2:
        raise ValueError('The regression dispatch must state both offline jobs')
    return jobs


def reconstruct(history,current):
    active,hardware,images,jobs = None,None,{},{}

    def confirm(entity,identifier):
        nonlocal active
        if active is None or active['image'] != entity['image'] or active['checksum'] != entity['checksum']:
            active = {'image':entity['image'],'checksum':entity['checksum'],'evidence':[]}
        active['evidence'].append(identifier)

    def certificate(entity,pipelines,identifier,*,invalidate=False):
        image = entity['image']
        state = images.get(image)
        if state is None or invalidate or any(state[key] != entity[key] for key in ('checksum','hardware')) or set(state['pipelines']) != set(pipelines):
            images[image] = {'checksum':entity['checksum'],'hardware':entity['hardware'],'pipelines':deepcopy(pipelines),'evidence':[]}
        images[image]['evidence'].append(identifier)

    for text in paragraphs(history):
        if registered := _pipeline_jobs(text):
            jobs = registered
            continue
        numbered = re.fullmatch(r'(E\d{2})：(.+)',text)
        if numbered is None:
            continue
        identifier,body = numbered.groups()
        record = _pipeline_record(body)
        event = record.get('event')
        if event == 'production_identity_confirmed':
            if hardware is not None and hardware != record['hardware']:
                raise ValueError('An image activation cannot silently replace the shared hardware module')
            hardware = record['hardware']
            confirm(record,identifier)
        elif event == 'pipeline_module_replaced':
            if hardware != record['previous_hardware'] or active is None or any(active[key] != record[key] for key in ('image','checksum')):
                raise ValueError('A module replacement must retain the stated unchanged production image')
            hardware = record['hardware']
            images = {}
            confirm(record,identifier)
        elif event in ('pipeline_certificate','pipeline_service_fault'):
            entity = jobs[record['job_id']] if record.get('job_id') else record
            if any(record[key] != entity[key] for key in ('image','checksum','hardware') if key in record):
                raise ValueError('The offline job must match its explicitly registered image and configuration')
            if entity['hardware'] != hardware:
                raise ValueError('Offline capability acceptance must refer to the installed module configuration')
            certificate(entity,record['pipelines'],identifier,invalidate=event == 'pipeline_service_fault')
    return {'active':active,'hardware':hardware,'images':images,
            'contract':{key:deepcopy(current[key]) for key in ('allowed_encoders','encryption','error_correction','block_kib','capacity_kib')}}


def legal_pipelines(facts):
    contract = facts['contract']
    state = facts['images'][facts['active']['image']]
    if state['hardware'] != facts['hardware'] or state['checksum'] != facts['active']['checksum']:
        return []
    return [pipeline for pipeline in state['pipelines'] if pipeline[0] in contract['allowed_encoders']
            and contract['encryption'] in ('*',pipeline[1]) and contract['error_correction'] in ('*',pipeline[2])
            and contract['block_kib'] <= contract['capacity_kib'][pipeline[0]]]


def evaluate(facts,operation,references):
    legal = legal_pipelines(facts)
    correct = not legal if operation.get('hold') else operation['pipeline'] in legal
    supported = []
    if set(references)&set(facts['active']['evidence']):
        supported.append('identity')
    if set(references)&set(facts['images'][facts['active']['image']]['evidence']):
        supported.append('capability')
    return (50*len(supported) if correct else 0),correct,supported


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},'description':'E01—E12编号字符串数组，可空；重复先去重后最多2个不同ID。'}}})

    def actions(self):
        return [] if self.done else super().actions()

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','option','evidence'} or action['action'] != 'select':
            self.invalid()
            return
        option = next((row for row in self.actions() if isinstance(action['option'],str) and row['option'] == action['option']),None)
        references = action['evidence']
        if option is None or not isinstance(references,list) or not all(isinstance(identifier,str) and identifier in CATALOG for identifier in references) or len(set(references)) > 2:
            self.invalid()
            return
        references = list(dict.fromkeys(references))
        operation = deepcopy(option['operation'])
        score,correct,supported = evaluate(self.task.world,operation,references)
        if not operation.get('hold'):
            self.state['attempts'].append({**operation,'image':self.task.world['active']['image'],'hardware':self.task.world['hardware'],
                'block_kib':self.task.public['block_kib'],'qualified':correct})
            self.state['qualified_block_delivered'] = correct
        self.facts = {'executed_operation':operation,'operation_correct':correct,'supported':supported,'references':references}
        self.feedback = '回传管线与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('The current image identity and full pipeline capability require at most two sufficient records')


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Production activation and offline capability must follow their separate public histories')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(3):
            for references in combinations(CATALOG,count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
