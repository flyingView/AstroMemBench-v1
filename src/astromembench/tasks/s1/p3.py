"""FM-S1-P3: retain pair certificates for immutable cargo serial identities."""
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs
from .evidence import CATALOG, EvidenceRuntime, evidence_contract

PAIR_KEYS = ('ab','ac','ad','bc','bd','cd')
# Target, layout, initial pair results, replaced positions/new affected-pair results, reinstalled position, receipt pair.
CONFIGS = (
    ('E','c','P','a','P',None,None),
    ('B','d','P','b','U',None,'ab'),
    ('F','b','P','a','F','a','ab'),
    ('D','a','P','a','F',None,None),
    ('B','d','F','b','P',None,'ab'),
    ('A','c','F','a','P','a','ab'),
    ('B','c','PPP','','',None,'ac'),
    ('D','a','PFP','','',None,'ac'),
    ('F','d','PPP','a','PP',None,'bc'),
    ('A','b','PPP','a','UP',None,'ab'),
    ('A','d','PPP','c','FU','c','ac'),
    ('F','b','PFP','c','PP','c','ac'),
    ('F','d','PPPPPP','a','PPP',None,'bc'),
    ('E','a','PPPPPP','ad','PFPUP',None,'bd'),
    ('B','b','PPPPPP','d','FUU','d','ad'),
    ('F','d','PPPPFP','d','PPP','d','bd'),
)
LAYOUTS = {
    'a':(8,14,3,18,6,11,20,2,15,7,12,4,17,10,9,5,19),
    'b':(16,4,12,7,19,2,9,18,6,13,1,15,5,17,3,20,11),
    'c':(3,17,9,14,1,20,6,12,4,18,10,7,15,2,11,8,19),
    'd':(13,6,18,3,15,8,10,1,17,5,19,2,12,4,16,7,20),
}


def initial_model(target,count):
    return {'pallet':target,'manifest':{slot:f'{target}:{slot}1' for slot in 'abcd'[:count]},
        'stock':{f'{target}:{slot}2':10 for slot in 'abcd'},'side':{},'pairs':{},'evidence':{}}


def required_pairs(manifest):
    return tuple(key for key in PAIR_KEYS if all(slot in manifest for slot in key))


def pair_id(serials):
    return '|'.join(sorted(serials))


def pair_state(model,key):
    return model['pairs'][pair_id([model['manifest'][slot] for slot in key])]


def apply_record(model,record):
    event,claims = record['event'],{}
    if event in ('cargo_exchanged','cargo_reinstalled'):
        origin,destination = (model['stock'],model['side']) if event == 'cargo_exchanged' else (model['side'],model['stock'])
        for move in record['moves']:
            if model['manifest'][move['slot']] != move['outgoing'] or origin.get(move['incoming']) != move['mass_kg']:
                raise ValueError('Cargo changes must move the actual complete serial-numbered item')
            del origin[move['incoming']]
            destination[move['outgoing']] = move['mass_kg']
            model['manifest'][move['slot']] = move['incoming']
        changed = {move['slot'] for move in record['moves']}
        for key in required_pairs(model['manifest']):
            if changed.intersection(key):
                identity = pair_id([model['manifest'][slot] for slot in key])
                state = model['pairs'].setdefault(identity,{'status':'U','epoch':0})
                if state['status'] == 'U':
                    claims[identity] = deepcopy(state)
    elif event in ('cargo_pair_checked','cargo_pair_status'):
        identity = pair_id(record['serials'])
        state = model['pairs'].setdefault(identity,{'status':'U','epoch':0})
        if event == 'cargo_pair_checked':
            if state['status'] != record['status']:
                state['epoch'] += 1
            state['status'] = record['status']
        elif state['status'] != record['status']:
            raise ValueError('A direct pair receipt must reflect the actual unchanged serial pair')
        claims[identity] = deepcopy(state)
    if record.get('record_id') in CATALOG:
        model['evidence'][record['record_id']] = {'event':event,'claims':claims}


def supports(record,model,key,depart):
    identity = pair_id([model['manifest'][slot] for slot in key])
    state = model['pairs'][identity]
    return record.get('claims',{}).get(identity) == state and (state['status'] == 'P') == depart


def build(index):
    target,layout,old,changed,new,reinstalled,receipt_pair = CONFIGS[index]
    count = 2 if index < 6 else 3 if index < 12 else 4
    other = 'ABCDEF'[('ABCDEF'.index(target)+1)%6]
    roles = (*('H_'+key for key in PAIR_KEYS),'W',*('J_'+key for key in PAIR_KEYS),'V','Q','P','D')
    identifiers = dict(zip(roles,(f'N{n:02d}' for n in LAYOUTS[layout]),strict=True))
    history,model = History(),initial_model(target,count)
    pairs = required_pairs(model['manifest'])
    history.add(1,'六辆托盘A—F，目标含n个货位，从a开始，每件密闭标准货件10 kg，不可分且不消耗；货位未列者不在清单。'
        '初装各货位1号件，备用a2/b2/c2/d2各10 kg在库；序列号含托盘前缀，其他托盘同名货件是不同物体。'
        '配对证书只适用于其两个实际序列号，不依赖货件当前是否在车上。卸下不撤销证书，原件未改动装回时旧有效证书继续适用。'
        '新组合默认U未核验，不能从旧组合推断；实际配对核验P通过/F失败改变该序列号对关系，计划不改变结果。'
        '只有全部当前货件两两配对均P才发车，否则保持；不测路线、固定件装配或外部危险品知识。'
        'n2仅ab，n3为ab/ac/bc，n4为ab/ac/ad/bc/bd/cd，必需配对总数分别1/3/6，覆盖全部配对而非仅被改动的边。'
        '菜单1发车A/2保持A/3发车B/4保持B/5发车C/6保持C/7发车D/8保持D/9发车E/10保持E/11发车F/12保持F。'
        '提交仅action=select、菜单字符串option及可选evidence对象；仅ab/ac/ad/bc/bd/cd键，每键最多一个严格N01—N20编号，可省略/null/空串。'
        '操作须引用实际发生的N事件；发车须为每个实际配对提供有效当前P证明，保持时任一对应键充分证明当前配对F/U即可说明无法发车。'
        '全空或未发生编号不能充当事实依据。仍有效实际核验与同事实直接状态回执均可用，不只认最新；同一单对回执不能冒充另一对。'
        '实际换件和新组合未验规则可以证明相应当前U，未验检查计划不是独立U实态证明；旧已核验组合回装须采用其原配对证书。'
        '没有新检查动作，原生记忆检索不耗动作；一次有效选择立即执行并终止，不合格发车不可逆，事后改引不能补救。'
        '最多3次含格式错提交，格式不符耗次、第三次结束；end仅action=end并直接结束，不猜自由文本意图。'
        '固定反馈托盘操作和引用记录已登记，不提供真值、得分或证据支持集合。',
        event='cargo_pair_protocol',pallet=target,positions=list('abcd'[:count]),evidence_catalog=CATALOG)
    manifest_text = '、'.join(model['manifest'].values())
    stock_text = '、'.join(model['stock'])
    history.add(2,f'目标{target}装入货件{manifest_text}，每件10 kg、共{10*count} kg；四件备用{stock_text}各10 kg仍在库。',
        event='cargo_initial_manifest',pallet=target,manifest=deepcopy(model['manifest']),stock=deepcopy(model['stock']))

    def record(at,role,text,**facts):
        identifier = identifiers[role]
        apply_record(model,{'record_id':identifier,**facts})
        history.add(at,f'{identifier}：'+text,record_id=identifier,**facts)

    for key,result in zip(pairs,old,strict=True):
        serials = [model['manifest'][slot] for slot in key]
        at = dict(zip(PAIR_KEYS,(3,5,7,9,11,12),strict=True))[key]
        record(at,'H_'+key,f'目标{target}货件对{serials[0]}与{serials[1]}实际配对核验{result}。',
            event='cargo_pair_checked',pallet=target,key=key,serials=serials,status=result)
    if changed:
        moves = [{'slot':slot,'outgoing':model['manifest'][slot],'incoming':f'{target}:{slot}2','mass_kg':10} for slot in changed]
        move_text = '；'.join(f'货位{row["slot"]}由{row["outgoing"]}换为{row["incoming"]}，整件质量{row["mass_kg"]} kg' for row in moves)
        record(14,'W',f'实际换件：{move_text}。每个1号原件完整卸入旁存位，对应2号从库装入，其他货位不动，货件未改动；新组合尚未核验。',
            event='cargo_exchanged',moves=moves)
        affected = [key for key in pairs if set(key).intersection(changed)]
        for key,result in zip(affected,new,strict=True):
            serials = [model['manifest'][slot] for slot in key]
            if result == 'U':
                record(15+PAIR_KEYS.index(key),'J_'+key,f'配对{serials[0]}与{serials[1]}只排10:00检查，尚未执行和取得结果。',
                    event='cargo_pair_check_scheduled',pallet=target,key=key,serials=serials,scheduled_s=clock('10:00'),executed=False)
            else:
                record(15+PAIR_KEYS.index(key),'J_'+key,f'配对{serials[0]}与{serials[1]}实际核验{result}。',
                    event='cargo_pair_checked',pallet=target,key=key,serials=serials,status=result)
    if reinstalled:
        move = {'slot':reinstalled,'outgoing':model['manifest'][reinstalled],'incoming':f'{target}:{reinstalled}1','mass_kg':10}
        record(21,'V',f'实际回装：货位{move["slot"]}由{move["outgoing"]}换为{move["incoming"]}，整件质量{move["mass_kg"]} kg。'
            '2号完整卸回库，旁存原1号完整装回，确认原件没有改动，其他货位不动。',
            event='cargo_reinstalled',moves=[move])
    if receipt_pair:
        serials = [model['manifest'][slot] for slot in receipt_pair]
        result = pair_state(model,receipt_pair)['status']
        record(23,'Q',f'直接核实当前配对{serials[0]}与{serials[1]}，实际状态{result}；未改变任何货件或物料。',
            event='cargo_pair_status',pallet=target,key=receipt_pair,serials=serials,status=result)
    record(25,'P','下一周期10:15核验已预约，尚未开始，货件没有改变。',
        event='cargo_review_scheduled',scheduled_s=clock('10:15'),executed=False)
    record(27,'D',f'其他托盘{other}的独立货件{other}:a1与{other}:b1实际配对核验P；其前缀与目标不同。',
        event='cargo_pair_checked',pallet=other,key='ab',serials=[f'{other}:a1',f'{other}:b1'],status='P')
    history.add(29,'全部当前货件封装和约束装置保持完好，没有新换件。',event='cargo_condition_unchanged')
    history.add(30,'本阶段转运准备结束。',event='cargo_ready')
    task = task_shell('FM-S1-P3',index,current_input_group=f'FM-S1-P3-{target}-{10*count}')
    task.public = {'instruction':f'继续目标托盘{target}本阶段转运，提交下一项操作及已有凭据。',
        'pallet':target,'mass_kg':10*count,'evidence_catalog':list(CATALOG),'time_s':clock('09:00'),'max_steps':3,'state_fields':[],
        'actions':fixed_options({'description':f'{"发车" if depart else "保持"}{name}',
            'operation':{'pallet':name,'depart':depart}} for name in 'ABCDEF' for depart in (True,False))}
    task.initial = {'time_s':clock('09:00'),'pallet_locations':{name:'loading_bay' for name in 'ABCDEF'}}
    task.world = model
    task.rubric = {'metric':'safe_cargo_dispatch_with_current_serial_pair_evidence','range':[0,100]}
    return history.finish(task)


class Runtime(EvidenceRuntime):
    evidence_slots = PAIR_KEYS
    accepted_feedback = '托盘操作和引用记录已登记。'
    action_contract = evidence_contract(evidence_slots,
        '仅ab/ac/ad/bc/bd/cd，键对应当前货位的实际货件对；每项一个严格N01—N20编号、null或空串，可省略，不允许多个编号或额外键。')

    def execute(self,operation,evidence):
        model,target = self.task.world,self.task.public['pallet']
        pairs = required_pairs(model['manifest'])
        depart = all(pair_state(model,key)['status'] == 'P' for key in pairs)
        correct = operation == {'pallet':target,'depart':depart}
        occurred = any(identifier in model['evidence'] for identifier in evidence.values() if identifier is not None)
        supported = [key for key in pairs if (record := model['evidence'].get(evidence.get(key))) is not None and supports(record,model,key,depart)]
        score = (20+80*len(supported)/len(pairs) if depart else 100 if supported else 20) if correct and occurred else 0
        if operation['depart']:
            self.state['pallet_locations'][operation['pallet']] = 'in_transit'
        self.facts = {'executed_operation':operation,'operation_correct':correct,'cited_existing_event':occurred,
            'supported_pairs':supported,'unsafe_target_dispatch':operation['pallet'] == target and operation['depart'] and not depart}
        return score


SERIAL = r'[A-F]:[abcd][12]'


def _serial_pair(text,pallet=None):
    serials = text.split('与')
    if (len(serials) != 2 or len(set(serials)) != 2
            or any(re.fullmatch(SERIAL,serial) is None for serial in serials)
            or pallet is not None and any(serial[0] != pallet for serial in serials)):
        raise ValueError('A pair certificate must identify two distinct complete cargo serials')
    return serials


def _moves(text,reinstalled):
    moves = []
    for part in text.split('；'):
        match = re.fullmatch(rf'货位([abcd])由({SERIAL})换为({SERIAL})，整件质量(\d+) kg',part)
        if match is None:
            raise ValueError('A whole-item transfer requires its printed slot, serials and mass')
        slot,outgoing,incoming,mass = match.groups()
        old,new = ('2','1') if reinstalled else ('1','2')
        if outgoing[2:] != slot+old or incoming != outgoing[:2]+slot+new:
            raise ValueError('A declared replacement or return must use the corresponding serial-numbered item')
        moves.append({'slot':slot,'outgoing':outgoing,'incoming':incoming,'mass_kg':int(mass)})
    return moves


def _cargo_record(text):
    if match := re.fullmatch(r'目标([A-F])货件对(.+)实际配对核验([PF])。',text):
        return {'event':'cargo_pair_checked','serials':_serial_pair(match[2],match[1]),'status':match[3]}
    if match := re.fullmatch(r'配对(.+)实际核验([PF])。',text):
        return {'event':'cargo_pair_checked','serials':_serial_pair(match[1]),'status':match[2]}
    if re.fullmatch(rf'配对{SERIAL}与{SERIAL}只排\d{{2}}:\d{{2}}检查，尚未执行和取得结果。',text):
        return {'event':'cargo_pair_check_scheduled'}
    if match := re.fullmatch(r'实际换件：(.+)。每个1号原件完整卸入旁存位，对应2号从库装入，其他货位不动，货件未改动；新组合尚未核验。',text):
        return {'event':'cargo_exchanged','moves':_moves(match[1],False)}
    if match := re.fullmatch(r'实际回装：(.+)。2号完整卸回库，旁存原1号完整装回，确认原件没有改动，其他货位不动。',text):
        return {'event':'cargo_reinstalled','moves':_moves(match[1],True)}
    if match := re.fullmatch(r'直接核实当前配对(.+)，实际状态([PFU])；未改变任何货件或物料。',text):
        return {'event':'cargo_pair_status','serials':_serial_pair(match[1]),'status':match[2]}
    if re.fullmatch(r'下一周期\d{2}:\d{2}核验已预约，尚未开始，货件没有改变。',text):
        return {'event':'cargo_review_scheduled'}
    if match := re.fullmatch(r'其他托盘([A-F])的独立货件(.+)实际配对核验([PF])；其前缀与目标不同。',text):
        return {'event':'cargo_pair_checked','serials':_serial_pair(match[2],match[1]),'status':match[3]}
    return None


def reconstruct(history,current):
    model = None
    for text in paragraphs(history):
        if match := re.fullmatch(r'目标([A-F])装入货件(.+)，每件10 kg、共(\d+) kg；四件备用(.+)各10 kg仍在库。',text):
            target,serials,mass,stock = match.groups()
            serials,stock = serials.split('、'),stock.split('、')
            model = initial_model(target,len(serials))
            if (list(model['manifest'].values()) != serials or list(model['stock']) != stock
                    or target != current['pallet'] or int(mass) != 10*len(serials)):
                raise ValueError('Cargo inventory must identify the actual initial serials, mass and target')
        elif model is not None:
            numbered = re.fullmatch(r'(N\d{2})：(.+)',text)
            record = _cargo_record(numbered[2] if numbered else text)
            if record is None:
                continue
            if numbered:
                record['record_id'] = numbered[1]
            if record['event'] == 'cargo_pair_status' and not set(record['serials']) <= set(model['manifest'].values()):
                raise ValueError('A current pair receipt must describe items actually on the pallet')
            apply_record(model,record)
    if model is None:
        raise ValueError('Cargo history requires its printed initial manifest')
    if 10*len(model['manifest']) != current['mass_kg']:
        raise ValueError('Whole-item movements must retain the actual manifest mass')
    return model


def next_action(facts,current):
    pairs = required_pairs(facts['manifest'])
    depart = all(pair_state(facts,key)['status'] == 'P' for key in pairs)
    evidence = {}
    for key in pairs:
        choices = [identifier for identifier,record in facts['evidence'].items() if supports(record,facts,key,depart)]
        if choices:
            evidence[key] = choices[0]
    arguments = next(row['arguments'] for row in current['actions'] if row['details']['operation'] == {'pallet':current['pallet'],'depart':depart})
    return {**arguments,'evidence':evidence}


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Cargo compatibility must follow actual serial pairs, independent of unloading order')


def audit_cases(task,facts,solution):
    command = solution[0]
    cases = [([{'action':'select','option':row['option'],'evidence':command['evidence']}],100 if row['option'] == command['option'] else 0)
        for row in task.public['actions']]
    pairs = required_pairs(facts['manifest'])
    depart = all(pair_state(facts,key)['status'] == 'P' for key in pairs)
    for key in PAIR_KEYS:
        for identifier in CATALOG:
            record = facts['evidence'].get(identifier)
            enough = record is not None and key in pairs and supports(record,facts,key,depart)
            score = 0 if record is None else (20+80/len(pairs) if depart else 100) if enough else 20
            cases.append(([{**command,'evidence':{key:identifier}}],score))
    return cases+[([{**command,'evidence':{}}],0),([{}]*2+solution,100),([{}]*3,0)]
