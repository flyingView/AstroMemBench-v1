"""FM-S1-O3: sufficient evidence for alternative supply isolation paths."""
from copy import deepcopy
from itertools import product
import re

from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs
from .evidence import CATALOG, EvidenceRuntime, evidence_contract

CHECKS = {'S':'停流','D':'残压处置','A':'封帽隔离','B':'上游阀隔离','C':'下游阀隔离'}
# Interface, record layout, original results, adjusted checks/results, status receipt.
CONFIGS = (
    ('A','a','PPPPP','','','A'), ('C','b','PPFPP','','','B'),
    ('E','c','PPPFU','','','C'), ('B','d','PPUFP','','','A'),
    ('B','d','PPFFF','','','A'), ('E','d','PPPPP','AB','FU','B'),
    ('D','a','FPPPP','S','P','A'), ('F','d','PPPPP','D','U','D'),
    ('C','c','PPFPP','C','P','C'), ('D','b','PPPPP','SD','FU','D'),
    ('B','a','PPPPP','ABC','UPU','C'), ('C','c','PPPPP','DA','PF','D'),
    ('F','d','PPFUU','BC','PP','C'), ('B','b','PPFPP','SAC','PUF','A'),
    ('B','b','UPUPP','SA','PP','S'), ('F','d','PPFPP','DB','UF','B'),
)
LAYOUTS = {
    'a':(8,15,3,11,4,18,6,13,20,2,17,9,5,14),
    'b':(17,4,12,6,15,2,19,8,3,14,10,20,5,11),
    'c':(5,18,9,16,2,11,7,20,13,4,8,1,17,12),
    'd':(14,3,17,8,19,6,12,1,11,20,4,15,9,18),
}


def release_ready(checks):
    passed = {key for key,state in checks.items() if state['status'] == 'P'}
    return {'S','D'} <= passed and ('A' in passed or {'B','C'} <= passed)


def blockers(checks):
    failed = {key for key,state in checks.items() if state['status'] != 'P'}
    return [group for group in ({'S'},{'D'},{'A','B'},{'A','C'}) if group <= failed]


def supported_checks(interface,checks,records,evidence):
    return {key for key,identifier in evidence.items() if (record := records.get(identifier)) is not None
        and record['interface'] == interface and record.get('claims',{}).get(key) == checks[key]}


def coverage(checks,supported):
    if release_ready(checks):
        passed = {key for key in supported if checks[key]['status'] == 'P'}
        return int('S' in passed)+int('D' in passed)+int('A' in passed or {'B','C'} <= passed),3
    return max(len(group & supported)/len(group) for group in blockers(checks)),1


def build(index):
    target,layout,old,affected,new,receipt = CONFIGS[index]
    other = 'ABCDEF'[('ABCDEF'.index(target)+1)%6]
    identifiers = dict(zip((*('H_'+key for key in CHECKS),'W',*('J_'+key for key in CHECKS),'Q','O','P'),
        (f'N{n:02d}' for n in LAYOUTS[layout]),strict=True))
    checks = {key:{'version':1,'status':value} for key,value in zip(CHECKS,old,strict=True)}
    evidence = {}
    history = History()
    history.add(1,'接口A—F保持连接。S是停流检查、D是残压处置检查、A是封帽隔离检查、B是上游阀隔离检查、C是下游阀隔离检查；'
        'A/B/C在检查字段中表示检查名称，不是接口对象。题内释放条件为S与D实际通过，且封帽实际通过，或上游阀与下游阀都实际通过：S∧D∧(A∨(B∧C))。'
        '这两种隔离方案互为替代，任一隔离方案足够；设备正常、动作已预置，无需外部工程知识。实际通过为P，实际失败为F，尚未实际检查为U。'
        '全部检查初始状态编号1；相关重开或调整只撤销明示项目，编号变为2，直至实际复检给出新结果之前为U；其他项目保持。'
        '旧P/F只适用于对应状态，未来计划不改变状态。同状态独立实际回执与仍适用原记录等价；调整记录可证明对应项目当前仍未验，排程不代表验收。'
        '符合释放条件则释放目标，否则保持；不能总保持已经具备条件的接口。操作真实且不可逆，错误对象不完成工单。'
        'select仅action/option/可选evidence，选项为菜单字符串；evidence仅S/D/A/B/C，每项最多一个严格N01—N20编号，或省略、null、空串，不接受列表或多号。'
        '目录包含未发生编号，未发生编号没有事实。没有现场复检工具，原生记忆读取不计操作。最多3次总提交，格式错反馈格式不符且耗次，首次有效决定立即结束。'
        '主动结束仅action=end；有效操作统一反馈补给收尾操作及引用依据已登记，不给安全真值或证据判定。'
        f'本工单目标接口{target}，检查名称及上述规程适用于本次收尾。',
        event='supply_safety_protocol',interface=target,checks=CHECKS,initial_version=1)
    history.add(2,f'接口{target}补给已实际结束，当前保持连接，尚未释放。',event='supply_finished',interface=target,connected=True)

    def emit(at,role,text,**facts):
        identifier = identifiers[role]
        history.add(at,f'{identifier}：'+text,record_id=identifier,**facts)
        evidence[identifier] = deepcopy(facts)

    def report(at,role,key,event):
        state = checks[key]
        result = {'P':'实际检查通过','F':'实际检查失败','U':'实际状态登记：当前尚未实际检查'}[state['status']]
        if role == 'Q':
            result = '独立实际状态回执：'+{'P':'当前通过','F':'当前失败','U':'当前尚未实际检查'}[state['status']]+'；未进行调整或新的检查'
        emit(at,role,f'接口{target}的{CHECKS[key]}检查（{key}），状态{state["version"]}，{result}。',
            event=event,interface=target,claims={key:deepcopy(state)})

    for position,key in enumerate(CHECKS):
        report(3+2*position,'H_'+key,key,'supply_safety_checked' if checks[key]['status'] != 'U' else 'supply_safety_status')
    if affected:
        for key in affected:
            checks[key] = {'version':2,'status':'U'}
        emit(12,'W',f'接口{target}已实际完成相关重开/调整，涉及{"、".join(CHECKS[key] for key in affected)}；'
            '这些项目状态变为2，旧检查撤销，尚未实际复检；其他项目保持原状态。',
            event='supply_safety_adjusted',interface=target,claims={key:deepcopy(checks[key]) for key in affected})
        for key,result in zip(affected,new,strict=True):
            at = 14+2*list(CHECKS).index(key)
            if result == 'U':
                emit(at,'J_'+key,f'接口{target}的{CHECKS[key]}检查（{key}），状态2复检已排程至10:00。',
                    event='supply_safety_scheduled',interface=target,check=key,version=2,scheduled_s=clock('10:00'))
            else:
                checks[key]['status'] = result
                report(at,'J_'+key,key,'supply_safety_checked')
    report(24,'Q',receipt,'supply_safety_status')
    emit(26,'O',f'其他接口{other}五检查停流、残压处置、封帽、上游阀、下游阀在状态1均实际通过；不属于接口{target}。',
        event='supply_safety_checked',interface=other,claims={key:{'version':1,'status':'P'} for key in CHECKS})
    emit(28,'P',f'接口{target}下一周期五检查均预约10:15，没有实际调整或复检。',
        event='supply_safety_scheduled',interface=target,scheduled_s=clock('10:15'))
    history.add(30,'等待本阶段接口收尾。',event='supply_safety_ready')
    task = task_shell('FM-S1-O3',index,current_input_group=f'FM-S1-O3-interface-{target}')
    task.public = {'instruction':f'继续接口{target}的补给收尾，提交下一项操作及已有凭据。','interface':target,
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':fixed_options({'description':f'{"释放" if release else "保持"}接口{name}',
            'operation':{'interface':name,'release':release}} for name in 'ABCDEF' for release in (True,False))}
    task.initial = {'connected':dict.fromkeys('ABCDEF',True)}
    task.world = {'interface':target,'checks':checks,'evidence':evidence}
    task.rubric = {'score':'correct and real evidence: release 20+80*g/3 functional prerequisites; hold 20+80*max blocker-set coverage; otherwise 0'}
    return history.finish(task)


class Runtime(EvidenceRuntime):
    evidence_slots = tuple(CHECKS)
    accepted_feedback = '补给收尾操作及引用依据已登记。'
    action_contract = evidence_contract(evidence_slots,
        '仅S/D/A/B/C：停流/残压处置/封帽/上游阀/下游阀检查；每项一个严格N01—N20编号、null或空串，可省略，不得列表或多号。')

    def execute(self,operation,evidence):
        world = self.task.world
        ready = release_ready(world['checks'])
        correct = operation == {'interface':world['interface'],'release':ready}
        occurred = any(identifier in world['evidence'] for identifier in evidence.values() if identifier is not None)
        supported = supported_checks(world['interface'],world['checks'],world['evidence'],evidence)
        numerator,denominator = coverage(world['checks'],supported)
        score = 20+80*numerator/denominator if correct and occurred else 0
        self.state['connected'][operation['interface']] = not operation['release']
        self.facts.update(executed_operation=operation,supported_checks=sorted(supported),operation_correct=correct,
            cited_existing_event=occurred,unsafe_target_release=operation['interface'] == world['interface'] and operation['release'] and not ready)
        return score


def _supply_record(text,target):
    if match := re.fullmatch(r'接口([A-F])的(.+)检查（([SDABC])），状态(\d+)，(.+)。',text):
        interface,name,key,version,result = match.groups()
        if name != CHECKS[key]:
            raise ValueError('A safety check name must match its printed key')
        outcomes = {'实际检查通过':('supply_safety_checked','P'),
            '实际检查失败':('supply_safety_checked','F'),
            '实际状态登记：当前尚未实际检查':('supply_safety_status','U')}
        for status,label in (('P','当前通过'),('F','当前失败'),('U','当前尚未实际检查')):
            outcomes[f'独立实际状态回执：{label}；未进行调整或新的检查'] = ('supply_safety_status',status)
        if result in outcomes:
            event,status = outcomes[result]
            return {'event':event,'interface':interface,'claims':{key:{'version':int(version),'status':status}}}
    if match := re.fullmatch(r'接口([A-F])已实际完成相关重开/调整，涉及(.+)；这些项目状态变为(\d+)，旧检查撤销，尚未实际复检；其他项目保持原状态。',text):
        names = {name:key for key,name in CHECKS.items()}
        affected = match[2].split('、')
        if any(name not in names for name in affected) or len(set(affected)) != len(affected):
            raise ValueError('Adjustment must explicitly name each affected safety check once')
        return {'event':'supply_safety_adjusted','interface':match[1],
            'claims':{names[name]:{'version':int(match[3]),'status':'U'} for name in affected}}
    if match := re.fullmatch(r'接口([A-F])的(.+)检查（([SDABC])），状态(\d+)复检已排程至(\d{2}:\d{2})。',text):
        if match[2] != CHECKS[match[3]]:
            raise ValueError('A safety check name must match its printed key')
        return {'event':'supply_safety_scheduled','interface':match[1],'check':match[3],
            'version':int(match[4]),'scheduled_s':clock(match[5])}
    if match := re.fullmatch(r'其他接口([A-F])五检查停流、残压处置、封帽、上游阀、下游阀在状态(\d+)均实际通过；不属于接口([A-F])。',text):
        if match[1] == target or match[3] != target:
            raise ValueError('Other-interface results must be distinct from the current target')
        return {'event':'supply_safety_checked','interface':match[1],
            'claims':{key:{'version':int(match[2]),'status':'P'} for key in CHECKS}}
    if match := re.fullmatch(r'接口([A-F])下一周期五检查均预约(\d{2}:\d{2})，没有实际调整或复检。',text):
        return {'event':'supply_safety_scheduled','interface':match[1],'scheduled_s':clock(match[2])}
    return None


def reconstruct(history,current):
    checks,evidence = {},{}
    for text in paragraphs(history):
        if match := re.search(r'本工单目标接口([A-F])，检查名称及上述规程适用于本次收尾。$',text):
            if match[1] != current['interface']:
                raise ValueError('Supply instruction must name its registered interface')
            initial = re.search(r'全部检查初始状态编号(\d+)；',text)
            if initial is None:
                raise ValueError('Supply history must print its initial check version')
            checks = {key:{'version':int(initial[1]),'status':'U'} for key in CHECKS}
        numbered = re.fullmatch(r'(N\d{2})：(.+)',text)
        if numbered is None:
            continue
        record = _supply_record(numbered[2],current['interface'])
        if record is None:
            continue
        event = record['event']
        if record['interface'] == current['interface'] and 'claims' in record:
            for key,state in record['claims'].items():
                if event == 'supply_safety_adjusted':
                    if state != {'version':checks[key]['version']+1,'status':'U'}:
                        raise ValueError('Only named adjustments advance local check versions')
                elif state['version'] != checks[key]['version']:
                    raise ValueError('Evidence must refer to its actual local check version')
                if event == 'supply_safety_status' and state != checks[key]:
                    raise ValueError('Status receipt must match the recorded current safety condition')
                checks[key] = deepcopy(state)
        if numbered[1] in CATALOG:
            evidence[numbered[1]] = deepcopy(record)
    return {'interface':current['interface'],'checks':checks,'evidence':evidence}


def next_action(facts,current):
    operation = {'interface':current['interface'],'release':release_ready(facts['checks'])}
    arguments = next(row['arguments'] for row in current['actions'] if row['details']['operation'] == operation)
    evidence = {}
    for key in CHECKS:
        evidence[key] = next(identifier for identifier,record in facts['evidence'].items()
            if record['interface'] == facts['interface'] and record.get('claims',{}).get(key) == facts['checks'][key])
    return {**arguments,'evidence':evidence}


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Supply safety and proofs must follow the two actual alternative isolation paths')


def audit_cases(task,facts,solution):
    command = solution[0]
    cases = [([{'action':'select','option':row['option'],'evidence':command['evidence']}],100 if row['option'] == command['option'] else 0)
        for row in task.public['actions']]
    choices = {key:[None,*[identifier for identifier,record in facts['evidence'].items()
        if record['interface'] == facts['interface'] and record.get('claims',{}).get(key) == facts['checks'][key]]] for key in CHECKS}
    candidates = [{key:identifier} for key in CHECKS for identifier in CATALOG]
    candidates += [dict(zip(CHECKS,values,strict=True)) for values in product(*choices.values())]
    for evidence in candidates:
        supported = supported_checks(facts['interface'],facts['checks'],facts['evidence'],evidence)
        numerator,denominator = coverage(facts['checks'],supported)
        occurred = any(identifier in facts['evidence'] for identifier in evidence.values() if identifier is not None)
        cases.append(([{**command,'evidence':evidence}],20+80*numerator/denominator if occurred else 0))
    return cases+[([{}]*2+solution,100),([{}]*3,0)]
