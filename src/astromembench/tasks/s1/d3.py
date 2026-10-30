"""FM-S1-D3: independent switch state and mode-specific coexistence evidence."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...schema import story_timestamp
from ..common import History, clock, fixed_options, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds
from .evidence import CATALOG, EvidenceRuntime

FREQUENCIES = {'L':8,'H':26}
RECEIVERS = ('R1','R2','R3')
# Packet, layout, selected mode, original L/H results, switch paths, reconfigured receivers/results, receipt.
CONFIGS = (
    ('A','a','L','P','F','I',(),'',1), ('C','b','H','P','F','I',(),'',None),
    ('E','c','H','P','P','O',(1,),'U',1), ('B','d','L','P','F','R',(1,),'U',1),
    ('A','c','H','P','P','R',(1,),'F',None), ('D','a','H','F','F','O',(),'',1),
    ('A','b','H','PP','PF','OI',(),'',1), ('E','a','L','FP','FF','OI',(2,),'P',2),
    ('C','c','L','PP','PP','RI',(1,),'U',1), ('A','d','H','PP','FF','OO',(1,2),'UU',None),
    ('D','b','L','PP','FP','IR',(2,),'P',1), ('B','a','H','PP','FU','II',(),'',2),
    ('D','c','H','PPP','PPF','IRI',(2,),'U',2), ('F','d','L','FPP','FFF','OIR',(3,),'P',3),
    ('C','c','H','PPP','FFF','OOO',(1,2,3),'UUU',1), ('F','d','H','PPP','PPP','ROR',(1,3),'FU',3),
)
LAYOUTS = {
    'a':(8,14,3,18,6,11,20,2,15,7,12,4,17,9,5,19),
    'b':(16,4,12,7,19,2,9,18,6,13,1,15,5,17,3,20),
    'c':(3,17,9,14,1,20,6,12,4,18,10,7,15,2,11,8),
    'd':(13,6,18,3,15,8,10,1,17,5,19,2,12,4,16,7),
}


def initial_receivers(count):
    return {name:{'configuration':1,'active':False,'switch_epoch':0,'certificates':{'L':'U','H':'U'}} for name in RECEIVERS[:count]}


def certificate(state,mode):
    return {'configuration':state['configuration'],'status':state['certificates'][mode]}


def switch(receivers,names,active):
    for name in names:
        state = receivers[name]
        if state['active'] == active:
            raise ValueError('A physical switch receipt must describe an actual transition')
        state['active'] = active
        state['switch_epoch'] += 1


def proof(record,receivers):
    return {'transmitter':record.get('transmitter','T1'),
        'switches':{name:{'active':active,'epoch':receivers[name]['switch_epoch']} for name,active in record.get('switch_claims',{}).items()},
        'certificates':deepcopy(record.get('certificate_claims',{}))}


def blocked(state,mode):
    return state['active'] and state['certificates'][mode] != 'P'


def evidence_parts(name,state,mode,records,references):
    on = off = passed = nonpass = False
    for identifier in references:
        record = records.get(identifier)
        if record is None or record['transmitter'] != 'T1':
            continue
        claim = record['switches'].get(name)
        if claim == {'active':state['active'],'epoch':state['switch_epoch']}:
            on |= state['active']
            off |= not state['active']
        if record['certificates'].get(name,{}).get(mode) == certificate(state,mode):
            passed |= state['certificates'][mode] == 'P'
            nonpass |= state['certificates'][mode] != 'P'
    return {'on':on,'off':off,'passed':passed,'nonpass':nonpass}


def supported_fraction(facts,evidence):
    receivers,mode = facts['receivers'],facts['mode']
    parts = {name:evidence_parts(name,state,mode,facts['evidence'],evidence.get(name,[])) for name,state in receivers.items()}
    if not any(blocked(state,mode) for state in receivers.values()):
        return sum(p['off'] or p['passed'] for p in parts.values()),len(receivers),parts
    return max(int(parts[name]['on'])+int(parts[name]['nonpass']) for name,state in receivers.items() if blocked(state,mode)),2,parts


def build(index):
    target,layout,mode,old_l,old_h,paths,affected,new,receipt = CONFIGS[index]
    count = len(paths)
    roles = ('HL1','HH1','HL2','HH2','HL3','HH3','ON0','OFF','W','J1','J2','J3','ON','Q','O_other','P')
    identifiers = dict(zip(roles,(f'N{n:02d}' for n in LAYOUTS[layout]),strict=True))
    receivers = initial_receivers(count)
    evidence = {}
    history = History()
    history.add(1,'数据包A—F均由本机发射机T1回传，模式L为8 GHz、H为26 GHz，只表示模式身份，不能由频率大小推断安全。'
        f'前{count}台敏感接收机{"、".join(receivers)}纳入共存保护，配置初始1；其他接收机无供电且有独立联锁。'
        '每台保护机条件为已实际停用，或它当前配置与当前发射模式已有实际共存核验P。全部保护机条件满足才回传，否则保持。'
        'P为实际通过，F为实际未通过，U为尚无有效核验；在用机的F/U均不够保护。实际重配仅撤销明示机L/H两模式的旧证，其他机保留。'
        '切换发射模式只改变证书适用范围，不撤销另一模式证书；返回原模式可用仍有效原证。封装数据包不改变射频模式或接收机配置。'
        '开关以实际回执为准，未来停用计划不算；停用后重新启用使旧停用回执失效。开关和重配分别维护，重配不会自动改变开关。'
        '各设备功能正常，停用仅为调度状态。收件端正常、带宽能源充足、包有完整副本；发送完整执行，不评分速度、删包或到达确认。'
        '错误发送为不可逆违规，错包不完成工单，具备条件却保持也不完成。select仅action/option/可选evidence，option为菜单字符串。'
        'evidence仅R1/R2/R3，各键最多2个不同严格N01—N20编号的数组，可空或省略，总最多6个；同一个记录可在不同机槽引用，但不能在同槽重复。'
        '目录含未发生编号，未发生编号没有事实。最多3次总调用，格式错反馈格式不符并耗次，首次有效决定即终局。主动结束仅action=end。'
        '没有再检查或开关工具，原生记忆访问不计动作；有效反馈固定为回传操作及引用依据已登记，不提供当前状态判断或推荐。'
        f'本阶段目标数据包{target}。',event='coexistence_protocol',packet=target,receiver_count=count,frequencies_ghz=FREQUENCIES,initial_configuration=1)

    def emit(at,role,text,**facts):
        identifier = identifiers[role]
        history.add(at,f'{identifier}：'+text,record_id=identifier,**facts)
        evidence[identifier] = proof(facts,receivers)
        return deepcopy(history.events[at-1].records[-1].data)

    switch(receivers,list(receivers),True)
    original_on = emit(2,'ON0',f'{story_timestamp(clock("08:02"))}，{"、".join(receivers)}已实际在用，本机T1当前发射模式L，尚未回传。',
        event='receiver_switched',transmitter='T1',switch_claims=dict.fromkeys(receivers,True),current_mode='L')

    def review(at,role,name,selected_mode,result):
        state = receivers[name]
        state['certificates'][selected_mode] = result
        text = {'P':'共存控制试验实际通过','F':'共存控制试验实际未通过','U':'实际状态登记：尚无有效共存核验'}[result]
        emit(at,role,f'本机T1与{name}配置{state["configuration"]}、{selected_mode}模式（{FREQUENCIES[selected_mode]} GHz）：{text}。',
            event='coexistence_reviewed' if result != 'U' else 'coexistence_status',transmitter='T1',
            certificate_claims={name:{selected_mode:certificate(state,selected_mode)}})

    for position,name in enumerate(receivers):
        review(3+2*position,f'HL{position+1}',name,'L',old_l[position])
        review(4+2*position,f'HH{position+1}',name,'H',old_h[position])
    stopped = [name for name,path in zip(receivers,paths,strict=True) if path in 'OR']
    if stopped:
        switch(receivers,stopped,False)
        emit(9,'OFF',f'接收机{"、".join(stopped)}已实际停用；未列接收机继续保持原开关状态。',
            event='receiver_switched',transmitter='T1',switch_claims=dict.fromkeys(stopped,False))
    if affected:
        for number in affected:
            state = receivers[f'R{number}']
            state['configuration'] += 1
            state['certificates'] = dict.fromkeys(FREQUENCIES,'U')
        emit(11,'W',f'接收机{"、".join(f"R{n}" for n in affected)}已实际重配为配置2，各机L/H两模式旧证均撤销且尚无新核验；'
            '未列接收机配置和证书不变，开关状态不因重配自动改变。',
            event='receiver_reconfigured',transmitter='T1',certificate_claims={f'R{n}':{m:certificate(receivers[f'R{n}'],m) for m in FREQUENCIES} for n in affected})
        for number,result in zip(affected,new,strict=True):
            name = f'R{number}'
            if result == 'U':
                emit(11+2*number,f'J{number}',f'本机T1与{name}配置2、{mode}模式的共存测试已预约10:00，尚未完成。',
                    event='coexistence_scheduled',transmitter='T1',receiver=name,configuration=2,mode=mode,scheduled_s=clock('10:00'))
            else:
                review(11+2*number,f'J{number}',name,mode,result)
    restarted = [name for name,path in zip(receivers,paths,strict=True) if path == 'R']
    if restarted:
        switch(receivers,restarted,True)
        emit(18,'ON',f'接收机{"、".join(restarted)}已实际重新启用，原停用回执不再代表当前状态；未列接收机不变。',
            event='receiver_switched',transmitter='T1',switch_claims=dict.fromkeys(restarted,True))
    if receipt is not None:
        name = f'R{receipt}'
        state = receivers[name]
        emit(20,'Q',f'独立实际状态回执：{name}当前{"在用" if state["active"] else "停用"}，配置{state["configuration"]}；'
            f'本机T1的{mode}模式共存事实为'+{'P':'实际通过','F':'实际未通过','U':'当前尚无有效核验'}[state['certificates'][mode]]+'；未进行新的开关、重配或检查。',
            event='receiver_status_receipt',transmitter='T1',switch_claims={name:state['active']},certificate_claims={name:{mode:certificate(state,mode)}})
    history.add(21,f'本机T1发射模式实际设为{mode}（{FREQUENCIES[mode]} GHz）'+('，确认继续保持L' if mode == 'L' else '')+'；未改变接收机配置或开关。',
        event='transmitter_mode_set',transmitter='T1',mode=mode,frequency_ghz=FREQUENCIES[mode])
    history.add(22,f'数据包{target}已重新封装，射频模式及全部接收机配置保持，不撤销共存证据。',event='packet_repacked',packet=target)
    other_configurations = '、'.join(f'{name}配置{receivers[name]["configuration"] if name in receivers else 1}' for name in RECEIVERS)
    emit(24,'O_other',f'另一发射机T2对{other_configurations}的L/H共存控制试验均通过；不属于本机T1，不能借用。',
        event='coexistence_reviewed',transmitter='T2',certificate_claims={name:{m:{'configuration':receivers[name]['configuration'] if name in receivers else 1,'status':'P'} for m in FREQUENCIES} for name in RECEIVERS})
    history.add(25,f'仅档案抄录，不是新的接收机启用。原{original_on["record_id"]}发生于{original_on["occurred_at"]}：{original_on["text"]}',
        occurred=original_on['occurred_s'],event='receiver_archive_copy',source_reference=original_on['record_id'],source_occurred_s=original_on['occurred_s'],source_text=original_on['text'])
    emit(26,'P','下一班接收机调度与共存核验预约10:15，当前不执行。',event='coexistence_scheduled',transmitter='T1',scheduled_s=clock('10:15'))
    history.add(28,'发射硬件自检正常，不能代替共存核验，接收机状态未变。',event='transmitter_hardware_check')
    history.add(30,'回传准备结束。',event='coexistence_ready')
    task = task_shell('FM-S1-D3',index,current_input_group=f'FM-S1-D3-{target}-{mode}-{count}')
    task.public = {'instruction':f'将数据包{target}按当前{mode}模式回传，请提交下一项操作及已有凭据。','packet':target,'mode':mode,
        'frequency_ghz':FREQUENCIES[mode],'receiver_count':count,'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':fixed_options({'description':f'{"回传" if transmit else "保持"}{name}',
            'operation':{'packet':name,'transmit':transmit}} for name in 'ABCDEF' for transmit in (True,False))}
    task.initial = {'transmissions':[],'retained_packets':list('ABCDEF')}
    task.world = {'packet':target,'mode':mode,'receivers':receivers,'evidence':evidence}
    task.rubric = {'score':'correct and real evidence: transmit 20+80*g/n protected receivers; hold 20+80*max blocker two-fact coverage; otherwise 0'}
    return history.finish(task)


class Runtime(EvidenceRuntime):
    evidence_slots = RECEIVERS
    accepted_feedback = '回传操作及引用依据已登记。'
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'object','required':False,
        'description':'仅R1/R2/R3，各值为最多2个不同严格N01—N20编号的数组，可省略或空数组；总最多6个，允许同一编号在不同机槽使用。',
        'properties':{name:{'type':'array','items':{'type':'string','enum':list(CATALOG)},'maxItems':2,'uniqueItems':True} for name in RECEIVERS},'additionalProperties':False}}})

    def valid_evidence(self,evidence):
        return isinstance(evidence,dict) and not evidence.keys()-set(RECEIVERS) and all(isinstance(refs,list) and len(refs) <= 2
            and all(isinstance(n,str) and n in CATALOG for n in refs) and len(set(refs)) == len(refs) for refs in evidence.values())

    def execute(self,operation,evidence):
        world = self.task.world
        transmit = not any(blocked(state,world['mode']) for state in world['receivers'].values())
        correct = operation == {'packet':world['packet'],'transmit':transmit}
        occurred = any(identifier in world['evidence'] for refs in evidence.values() for identifier in refs)
        numerator,denominator,parts = supported_fraction(world,evidence)
        score = 20+80*numerator/denominator if correct and occurred else 0
        if operation['transmit']:
            self.state['transmissions'].append({'packet':operation['packet'],'mode':world['mode'],'transmitter':'T1','complete':True})
        self.facts.update(executed_operation=operation,evidence_parts=parts,operation_correct=correct,cited_existing_event=occurred,
            unsafe_transmission=operation['transmit'] and not transmit)
        return score


def _receivers(text):
    if re.fullmatch(r'R[123](?:、R[123])*',text) is None:
        raise ValueError('A coexistence receipt must explicitly name its receivers')
    names = text.split('、')
    if len(set(names)) != len(names):
        raise ValueError('A coexistence receipt must name each receiver once')
    return names


def _coexistence_record(text,records):
    if match := re.fullmatch(rf'({STORY_STAMP})，(.+)已实际在用，本机T1当前发射模式([LH])，尚未回传。',text):
        return {'event':'receiver_switched','transmitter':'T1','switch_claims':dict.fromkeys(_receivers(match[2]),True),
            'current_mode':match[3],'occurred_s':seconds(match[1])}
    if match := re.fullmatch(r'本机T1与(R[123])配置(\d+)、([LH])模式（(\d+) GHz）：(.+)。',text):
        name,configuration,mode,frequency,result = match.groups()
        if FREQUENCIES[mode] != int(frequency):
            raise ValueError('A coexistence test must identify its registered mode frequency')
        outcomes = {'共存控制试验实际通过':('coexistence_reviewed','P'),
            '共存控制试验实际未通过':('coexistence_reviewed','F'),
            '实际状态登记：尚无有效共存核验':('coexistence_status','U')}
        if result in outcomes:
            event,status = outcomes[result]
            return {'event':event,'transmitter':'T1',
                'certificate_claims':{name:{mode:{'configuration':int(configuration),'status':status}}}}
    if match := re.fullmatch(r'接收机(.+)已实际停用；未列接收机继续保持原开关状态。',text):
        return {'event':'receiver_switched','transmitter':'T1','switch_claims':dict.fromkeys(_receivers(match[1]),False)}
    if match := re.fullmatch(r'接收机(.+)已实际重新启用，原停用回执不再代表当前状态；未列接收机不变。',text):
        return {'event':'receiver_switched','transmitter':'T1','switch_claims':dict.fromkeys(_receivers(match[1]),True)}
    if match := re.fullmatch(r'接收机(.+)已实际重配为配置(\d+)，各机L/H两模式旧证均撤销且尚无新核验；未列接收机配置和证书不变，开关状态不因重配自动改变。',text):
        return {'event':'receiver_reconfigured','transmitter':'T1',
            'certificate_claims':{name:{mode:{'configuration':int(match[2]),'status':'U'} for mode in FREQUENCIES} for name in _receivers(match[1])}}
    if match := re.fullmatch(r'本机T1与(R[123])配置(\d+)、([LH])模式的共存测试已预约(\d{2}:\d{2})，尚未完成。',text):
        return {'event':'coexistence_scheduled','transmitter':'T1','receiver':match[1],
            'configuration':int(match[2]),'mode':match[3],'scheduled_s':clock(match[4])}
    if match := re.fullmatch(r'独立实际状态回执：(R[123])当前(在用|停用)，配置(\d+)；本机T1的([LH])模式共存事实为(实际通过|实际未通过|当前尚无有效核验)；未进行新的开关、重配或检查。',text):
        name,active,configuration,mode,result = match.groups()
        status = {'实际通过':'P','实际未通过':'F','当前尚无有效核验':'U'}[result]
        return {'event':'receiver_status_receipt','transmitter':'T1','switch_claims':{name:active == '在用'},
            'certificate_claims':{name:{mode:{'configuration':int(configuration),'status':status}}}}
    if match := re.fullmatch(r'本机T1发射模式实际设为([LH])（(\d+) GHz）(?:，确认继续保持([LH]))?；未改变接收机配置或开关。',text):
        if FREQUENCIES[match[1]] != int(match[2]) or match[3] not in (None,match[1]):
            raise ValueError('A mode-setting event must name one consistent mode and frequency')
        return {'event':'transmitter_mode_set','transmitter':'T1','mode':match[1]}
    if match := re.fullmatch(r'另一发射机T2对(.+)的L/H共存控制试验均通过；不属于本机T1，不能借用。',text):
        claims = {}
        for part in match[1].split('、'):
            item = re.fullmatch(r'(R[123])配置(\d+)',part)
            if item is None or item[1] in claims:
                raise ValueError('Other-transmitter evidence must print each receiver configuration')
            claims[item[1]] = {mode:{'configuration':int(item[2]),'status':'P'} for mode in FREQUENCIES}
        return {'event':'coexistence_reviewed','transmitter':'T2','certificate_claims':claims}
    if match := re.fullmatch(rf'仅档案抄录，不是新的接收机启用。原(N\d{{2}})发生于({STORY_STAMP})：(.+)',text):
        original = records.get(match[1])
        if original is None or original.get('text') != match[3] or original.get('occurred_s') != seconds(match[2]):
            raise ValueError('Archived initial activation must retain its original content and occurrence')
        return {'event':'receiver_archive_copy'}
    if match := re.fullmatch(r'下一班接收机调度与共存核验预约(\d{2}:\d{2})，当前不执行。',text):
        return {'event':'coexistence_scheduled','transmitter':'T1','scheduled_s':clock(match[1])}
    return None


def reconstruct(history,current):
    receivers,evidence,records,mode = {},{}, {},None
    for text in paragraphs(history):
        if match := re.search(r'本阶段目标数据包([A-F])。$',text):
            scope = re.search(r'前([123])台敏感接收机(.+?)纳入共存保护，配置初始(\d+)；',text)
            if scope is None:
                raise ValueError('Downlink history must print its protected receivers and initial configuration')
            count,names,configuration = int(scope[1]),_receivers(scope[2]),int(scope[3])
            if match[1] != current['packet'] or count != current['receiver_count'] or names != list(RECEIVERS[:count]):
                raise ValueError('Downlink instruction must match its packet and protected receiver set')
            receivers = initial_receivers(count)
            for state in receivers.values():
                state['configuration'] = configuration
        numbered = re.fullmatch(r'(N\d{2})：(.+)',text)
        record = _coexistence_record(numbered[2] if numbered else text,records)
        if record is None:
            continue
        event = record['event']
        if event == 'receiver_switched':
            for name,active in record['switch_claims'].items():
                switch(receivers,[name],active)
            if 'current_mode' in record:
                mode = record['current_mode']
        elif event == 'receiver_reconfigured':
            for name,claims in record['certificate_claims'].items():
                state = receivers[name]
                expected = {m:{'configuration':state['configuration']+1,'status':'U'} for m in FREQUENCIES}
                if claims != expected:
                    raise ValueError('Reconfiguration must revoke both modes for exactly the affected receiver')
                state['configuration'] += 1
                state['certificates'] = dict.fromkeys(FREQUENCIES,'U')
        elif event in ('coexistence_reviewed','coexistence_status') and record['transmitter'] == 'T1':
            for name,claims in record['certificate_claims'].items():
                for selected_mode,claim in claims.items():
                    if receivers[name]['configuration'] != claim['configuration']:
                        raise ValueError('Coexistence evidence must belong to the actual receiver configuration')
                    receivers[name]['certificates'][selected_mode] = claim['status']
        elif event == 'receiver_status_receipt':
            if any(receivers[name]['active'] != active for name,active in record['switch_claims'].items()) or any(
                certificate(receivers[name],m) != claim for name,claims in record['certificate_claims'].items() for m,claim in claims.items()):
                raise ValueError('Status receipt must name actual switch state and selected-mode certificate facts')
        elif event == 'transmitter_mode_set':
            mode = record['mode']
        if numbered and numbered[1] in CATALOG:
            records[numbered[1]] = {**deepcopy(record),'text':text}
            evidence[numbered[1]] = proof(record,receivers)
    if mode != current['mode'] or FREQUENCIES[mode] != current['frequency_ghz']:
        raise ValueError('Current transmission mode must follow its actual mode-setting event')
    return {'packet':current['packet'],'mode':mode,'receivers':receivers,'evidence':evidence}


def next_action(facts,current):
    transmit = not any(blocked(state,facts['mode']) for state in facts['receivers'].values())
    evidence = {}
    for name,state in facts['receivers'].items():
        if not transmit and not blocked(state,facts['mode']):
            continue
        found = False
        for count in (1,2):
            for refs in combinations(sorted(facts['evidence']),count):
                parts = evidence_parts(name,state,facts['mode'],facts['evidence'],refs)
                enough = parts['off'] or parts['passed'] if transmit else parts['on'] and parts['nonpass']
                if enough:
                    evidence[name] = list(refs)
                    found = True
                    break
            if found:
                break
        if not transmit and found:
            break
    operation = {'packet':current['packet'],'transmit':transmit}
    return {**next(row['arguments'] for row in current['actions'] if row['details']['operation'] == operation),'evidence':evidence}


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Coexistence must follow switch epochs and mode/configuration facts independently')


def audit_cases(task,facts,solution):
    command = solution[0]
    cases = [([{'action':'select','option':row['option'],'evidence':command['evidence']}],100 if row['option'] == command['option'] else 0)
        for row in task.public['actions']]
    for name in RECEIVERS:
        for count in (0,1,2):
            for refs in combinations(CATALOG,count):
                evidence = {name:list(refs)}
                numerator,denominator,_ = supported_fraction(facts,evidence)
                occurred = any(identifier in facts['evidence'] for identifier in refs)
                cases.append(([{**command,'evidence':evidence}],20+80*numerator/denominator if occurred else 0))
    return cases+[([{}]*2+solution,100),([{}]*3,0)]
