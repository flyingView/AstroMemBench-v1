"""FM-S1-O2: retained one-shot installation safety, in thirty native rounds."""
from copy import deepcopy
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs
from .evidence import CATALOG

PROJECTS = {'K1':'机械固定','K2':'电气隔离','K3':'管路密封'}
REWORK = {'K1':'更换固定件','K2':'重新连接电气','K3':'重新连接管路'}
# Frozen group, target, required projects, actual rework, final results.
CONFIGS = (
    (1,'A',('K1',),(),'P'), (1,'A',('K1',),(),'F'),
    (4,'D',('K1',),('K1',),'P'), (4,'D',('K1',),('K1',),'U'),
    (5,'A',('K1',),('K1',),'P'), (5,'A',('K1',),('K1',),'U'),
    (8,'D',('K1','K3'),(),'PP'), (8,'D',('K1','K3'),(),'PF'),
    (9,'A',('K1','K2'),(),'PP'), (9,'A',('K1','K2'),(),'FF'),
    (12,'D',('K1','K3'),('K1','K3'),'PP'), (12,'D',('K1','K3'),('K1','K3'),'PU'),
    (14,'B',('K1','K2','K3'),(),'PPP'), (14,'B',('K1','K2','K3'),(),'PFF'),
    (16,'D',('K1','K2','K3'),('K2','K3'),'PPP'), (16,'D',('K1','K2','K3'),('K2','K3'),'PUU'),
)
LAYOUTS = {
    1:(1,8,15,2,9,16,3,10,17,4,11,18,5,12),
    4:(10,17,4,11,18,5,12,19,6,13,20,7,14,1),
    5:(13,20,7,14,1,8,15,2,9,16,3,10,17,4),
    8:(2,9,16,3,10,17,4,11,18,5,12,19,6,13),
    9:(5,12,19,6,13,20,7,14,1,8,15,2,9,16),
    12:(14,1,8,15,2,9,16,3,10,17,4,11,18,5),
    14:(20,7,14,1,8,15,2,9,16,3,10,17,4,11),
    16:(6,13,20,7,14,1,8,15,2,9,16,3,10,17),
}
MINUTES = (1,2,3,4,5,6,7,9,11,13,15,17,19,21,23,25,27,29,31,33,35,37,39,40,41,43,45,47,49,50)


def build(index):
    group,target,required,affected,final = CONFIGS[index]
    results = dict(zip(required,final,strict=True))
    other = 'BCDE'['ABCD'.index(target)]
    identifiers = dict(zip(('I','H1','H2','H3','W','J1','J2','J3','P','D1','D2','D3','O','W_other'),
        (f'N{n:02d}' for n in LAYOUTS[group]),strict=True))
    history = History(times=[clock(f'08:{minute:02d}:59') for minute in MINUTES])
    states,events = {},{}
    history.add(1,'设备A—F的临时支撑均保持固定。K1为机械固定检查、K2为电气隔离检查、K3为管路密封检查。'
        '只有工单要求的全部项目在各自当前安装状态下实际通过，才撤除目标设备临时支撑并完成收尾；否则保持。'
        '安装完成、准备检查和检查排程不等于通过。凭据须绑定同设备、同项目及该项目当前状态。'
        '更换固定件只使K1失效，重新连接电气只使K2失效，重新连接管路只使K3失效；联合返工只影响明示项目。'
        '新安装或相关返工后，直至实际检查给出结果，该项目尚无当前有效结果；尚无结果不等于实际失败。项目状态编号分别维护。'
        '可按K1/K2/K3各引用至多一条N01—N20记录，引用不启动新检查。'
        f'本题工单目标为设备{target}，必需项目为{"、".join(required)}。',
        event='installation_protocol',device=target,required=list(required),projects=PROJECTS)

    def emit(at,role,text,**facts):
        identifier = identifiers[role]
        history.add(at,f'{identifier}：'+text,record_id=identifier,**facts)
        events[identifier] = deepcopy(facts)
        return identifier

    def install(at,device,role):
        identifier = emit(at,role,f'{device}安装完成，机械、电气、管路状态均为1，临时支撑保持。',
            event='device_installed',device=device,versions=dict.fromkeys(PROJECTS,1))
        states[device] = {key:{'version':1,'status':'U','evidence':identifier} for key in PROJECTS}

    def rework(at,device,keys,role):
        for key in keys:
            states[device][key].update(version=states[device][key]['version']+1,status='U',evidence=identifiers[role])
        versions = {key:state['version'] for key,state in states[device].items()}
        version_text = '、'.join(f'{key}为{value}' for key,value in versions.items())
        emit(at,role,f'{device}已完成{"、".join(REWORK[key] for key in keys)}；'
            f'当前各项目状态编号：{version_text}；未涉及项目保持不变。',
            event='device_reworked',device=device,projects=list(keys),versions=versions)

    def check(at,device,key,result,role):
        version = states[device][key]['version']
        if result == 'U':
            emit(at,role,f'{device}的{key}{PROJECTS[key]}检查，项目状态{version}：'
                f'复验工单V{identifiers[role][1:]}排程已受理，列入下一次作业队列。',
                event='device_check_scheduled',device=device,project=key,version=version)
        else:
            text = '实际验收完成并通过' if result == 'P' else '实际验收完成，结果未通过'
            identifier = emit(at,role,f'{device}的{key}{PROJECTS[key]}检查，项目状态{version}：{text}。',
                event='device_checked',device=device,project=key,version=version,status=result)
            states[device][key].update(status=result,evidence=identifier)

    install(3,target,'I')
    install(5,other,'O')
    first_rounds = (9,) if len(required) == 1 else ((8,10) if affected else (8,16)) if len(required) == 2 else ((7,9,11) if affected else (7,14,21))
    for key,at in zip(required,first_rounds,strict=True):
        check(at,target,key,'P' if affected else results[key],'H'+key[1])
    if affected:
        rework({1:14,2:15,3:16}[len(required)],target,affected,'W')
        checks = (18,) if len(required) == 1 else ((18,21) if len(affected) == 2 else (20,)) if len(required) == 2 else (20,23)
        for key,at in zip(affected,checks,strict=True):
            check(at,target,key,results[key],'J'+key[1])
    routine = next((key for key in required if key not in affected),'K1')
    emit(25,'P',f'{target}的{routine}{PROJECTS[routine]}下一周期例行复查已排程，没有新的相关安装或连接操作。',
        event='device_check_scheduled',device=target,project=routine,version=states[target][routine]['version'])
    other_rounds = (28,) if len(required) == 1 else (13,28) if len(required) == 2 else (13,19,28)
    for key,at in zip(required,other_rounds,strict=True):
        if len(required) == 3 and key == 'K3':
            rework(26,other,('K1',),'W_other')
        check(at,other,key,'P','D'+key[1])
    history.add(30,'辅助作业结束，等待处理安装工单。',event='installation_ready')
    task = task_shell('FM-S1-O2',index,group=f'FM-S1-O2-group-{group:02d}',current_input_group=f'FM-S1-O2-device-{target}')
    task.public = {'instruction':f'继续完成设备{target}的安装收尾，请提交下一项作业。','device':target,
        'time_s':clock('09:00'),'max_steps':1,'record_catalog':list(CATALOG),
        'evidence_format':{key:'至多一个记录编号或留空' for key in PROJECTS},
        'actions':fixed_options({'description':f'{label}{device}临时支撑','operation':{'action':action,'device':device}}
            for device in 'ABCDEF' for action,label in (('remove','撤除'),('hold','保持')))}
    task.initial = {'supports':dict.fromkeys('ABCDEF',True)}
    task.world = {'required':list(required),'states':states,'events':events,
        'correct_operation':{'action':'remove' if all(value == 'P' for value in results.values()) else 'hold','device':target}}
    task.rubric = {'score':'correct action with existing evidence: remove 20+80*g/K; hold 100 if any blocker else 20; otherwise 0'}
    return history.finish(task)


class Runtime(TaskRuntime):
    # This retained template keeps its original one-attempt protocol and feedback.
    action_contract = ActionContract(parameters={'select':{
        'evidence':{'required':False,'type':'object',
            'description':'以 K1、K2、K3 为键；每项至多一个 N01–N20 记录编号，无依据可省略该项或填 null、空字符串。'}}})

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action)-{'action','option','evidence'} or action.get('action') != 'select':
            self.invalid()
            return
        selected = next((o for o in self.actions() if o['option'] == action.get('option')),None)
        evidence = action.get('evidence',{})
        if selected is None or not isinstance(evidence,dict) or set(evidence)-set(PROJECTS) or any(
            v is not None and (not isinstance(v,str) or (v != '' and not re.fullmatch(r'N(?:0[1-9]|1[0-9]|20)',v))) for v in evidence.values()):
            self.invalid()
            return
        operation = selected['operation']
        self.state['supports'][operation['device']] = operation['action'] == 'hold'
        existing = any(identifier in self.task.world['events'] for identifier in evidence.values() if identifier)
        correct = operation == self.task.world['correct_operation']
        supported = [key for key in self.task.world['required'] if evidence.get(key) == self.task.world['states'][self.task.public['device']][key]['evidence']]
        score = 0
        if correct and existing:
            if operation['action'] == 'remove':
                score = 20+80*len(supported)/len(self.task.world['required'])
            else:
                blockers = [key for key in supported if self.task.world['states'][self.task.public['device']][key]['status'] != 'P']
                score = 100 if blockers else 20
        self.facts.update(executed_operation=deepcopy(operation),supported_projects=supported,cited_existing_event=existing)
        self.feedback = '作业已执行，记录已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def _installation_record(text,states):
    if match := re.fullmatch(r'([A-F])安装完成，机械、电气、管路状态均为1，临时支撑保持。',text):
        return {'event':'device_installed','device':match[1],'versions':dict.fromkeys(PROJECTS,1)}
    if match := re.fullmatch(r'([A-F])已完成(.+)；当前各项目状态编号：K1为(\d+)、K2为(\d+)、K3为(\d+)；未涉及项目保持不变。',text):
        names = {name:key for key,name in REWORK.items()}
        operations = match[2].split('、')
        if any(name not in names for name in operations) or len(set(operations)) != len(operations):
            raise ValueError('Rework must identify each actually changed project once')
        return {'event':'device_reworked','device':match[1],'projects':[names[name] for name in operations],
            'versions':dict(zip(PROJECTS,map(int,match.groups()[2:]),strict=True))}
    if match := re.fullmatch(r'([A-F])的(K[123])(.+)检查，项目状态(\d+)：(.+)',text):
        device,project,name,version,result = match.groups()
        if PROJECTS[project] != name:
            raise ValueError('The printed project name must match its inspection key')
        record = {'device':device,'project':project,'version':int(version)}
        if result in ('实际验收完成并通过。','实际验收完成，结果未通过。'):
            return {'event':'device_checked',**record,'status':'P' if result == '实际验收完成并通过。' else 'F'}
        if re.fullmatch(r'复验工单V\d{2}排程已受理，列入下一次作业队列。',result):
            return {'event':'device_check_scheduled',**record}
    if match := re.fullmatch(r'([A-F])的(K[123])(.+)下一周期例行复查已排程，没有新的相关安装或连接操作。',text):
        device,project,name = match.groups()
        if PROJECTS[project] != name:
            raise ValueError('The printed project name must match its inspection key')
        return {'event':'device_check_scheduled','device':device,'project':project,
            'version':states[device][project]['version']}
    return None


def reconstruct(history,current):
    states,events,required = {},{},None
    for text in paragraphs(history):
        if match := re.search(r'本题工单目标为设备([A-F])，必需项目为(K[123](?:、K[123])*)。$',text):
            required = match[2].split('、')
            if match[1] != current['device']:
                raise ValueError('The repair instruction must name its registered device')
        numbered = re.fullmatch(r'(N\d{2})：(.+)',text)
        if numbered is None:
            continue
        identifier = numbered[1]
        record = _installation_record(numbered[2],states)
        if record is None:
            continue
        event = record['event']
        if event == 'device_installed':
            states[record['device']] = {key:{'version':value,'status':'U','evidence':identifier} for key,value in record['versions'].items()}
        elif event == 'device_reworked':
            device = states[record['device']]
            for key in record['projects']:
                device[key].update(version=device[key]['version']+1,status='U',evidence=identifier)
            if record['versions'] != {key:state['version'] for key,state in device.items()}:
                raise ValueError('Rework must advance exactly the affected project versions')
        elif event == 'device_checked':
            state = states[record['device']][record['project']]
            if state['version'] != record['version']:
                raise ValueError('Actual acceptance must refer to the project version at that time')
            state.update(status=record['status'],evidence=identifier)
        if identifier in CATALOG:
            events[identifier] = deepcopy(record)
    if required is None or current['device'] not in states:
        raise ValueError('Installation history requires the printed work scope and actual installation')
    operation = {'device':current['device'],'action':'remove' if all(states[current['device']][key]['status'] == 'P' for key in required) else 'hold'}
    return {'required':required,'states':states,'events':events,'correct_operation':operation}


def next_action(facts,current):
    operation = facts['correct_operation']
    arguments = next(row['arguments'] for row in current['actions'] if row['details']['operation'] == operation)
    return {**arguments,'evidence':{key:facts['states'][current['device']][key]['evidence'] for key in facts['required']}}


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Installation safety must follow actual per-project versions and acceptance events')


def audit_cases(task,facts,solution):
    command = solution[0]
    cases = [([{'action':'select','option':row['option'],'evidence':command['evidence']}],100 if row['option'] == command['option'] else 0)
        for row in task.public['actions']]
    for key in PROJECTS:
        for identifier in CATALOG:
            state = facts['states'][task.public['device']][key]
            supported = key in facts['required'] and identifier == state['evidence']
            score = 20+80*int(supported)/len(facts['required']) if facts['correct_operation']['action'] == 'remove' else 100 if supported and state['status'] != 'P' else 20
            cases.append(([{**command,'evidence':{key:identifier}}],score if identifier in facts['events'] else 0))
    return cases+[([{**command,'evidence':{}}],0),([{}],0)]
