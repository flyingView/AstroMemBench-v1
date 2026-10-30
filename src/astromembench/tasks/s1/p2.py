"""FM-S1-P2: certify actual sample ancestry rather than the latest mother bottle."""
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs
from .evidence import CATALOG, EvidenceRuntime, evidence_contract

# Target, ID layout, early/late material line, replaced source, first new-batch result, retrospective results, receipt lineage.
CONFIGS = (
    ('E','c','E','L','U',(), 'L'),
    ('B','d','L','L','U',(), 'L'),
    ('F','b','L','L','P',(), None),
    ('A','c','E','L','P',(('L1','U'),), 'L'),
    ('C','c','L','L','P',(('L1','F'),), 'L'),
    ('E','d','L','L','P',(('L2','F'),), 'L'),
    ('F','d','E','M','U',(), 'L'),
    ('A','b','L','M','U',(), 'M'),
    ('E','a','L','L','P',(), 'M'),
    ('C','c','E','L','P',(('L1','F'),), None),
    ('A','d','L','M','F',(('M2','P'),), 'M'),
    ('B','a','L','L','U',(('M1','F'),), 'L'),
    ('F','d','E','M','U',(('M2','F'),), 'M'),
    ('B','b','L','N','U',(('L1','F'),), 'N'),
    ('C','c','L','M','P',(('N1','P'),), 'L'),
    ('F','d','L','M','U',(('M2','F'),('N1','U')), 'M'),
)
LAYOUTS = {
    'a':(8,14,3,11,17,5,19,2,12,6,15,20),
    'b':(16,4,12,7,2,18,9,15,5,20,1,13),
    'c':(3,17,9,14,6,12,20,8,1,15,11,5),
    'd':(13,6,18,3,10,1,15,7,19,4,12,8),
}


def initial_materials(other):
    containers = {name:{} for name in 'ABCDEF'}
    containers[other] = {'Q1':20}
    return {'sources':{name:{'batch':f'{name}1','mass_g':100} for name in 'LMN'},
        'reserve':{f'{name}2':100 for name in 'LMN'},'side':{},'intermediate':{},'containers':containers}


def initial_model(other):
    return {'materials':initial_materials(other),
        'batches':{name:{'status':'U','epoch':0} for name in ('L1','L2','M1','M2','N1','N2','Q1')},'evidence':{}}


def take_sources(materials,draws):
    portion = {}
    for draw in draws:
        source = materials['sources'][draw['source']]
        if source['batch'] != draw['batch'] or not 0 < draw['mass_g'] <= source['mass_g']:
            raise ValueError('A sample must come from the actually present source batch and mass')
        source['mass_g'] -= draw['mass_g']
        portion[draw['batch']] = portion.get(draw['batch'],0)+draw['mass_g']
    return portion


def apply_record(model,record):
    """Replay actual mass transfers and batch status changes; plans never change either."""
    materials,batches = model['materials'],model['batches']
    event = record['event']
    if event == 'sample_blended':
        materials['intermediate'] = take_sources(materials,record['draws'])
    elif event == 'sample_source_replaced':
        source = materials['sources'][record['source']]
        outgoing,incoming = record['outgoing'],record['incoming']
        if source != outgoing or materials['reserve'][incoming['batch']] != incoming['mass_g']:
            raise ValueError('Source replacement transfers all remaining old mass and the full sealed reserve')
        materials['side'][outgoing['batch']] = materials['side'].get(outgoing['batch'],0)+outgoing['mass_g']
        materials['reserve'][incoming['batch']] = 0
        materials['sources'][record['source']] = deepcopy(incoming)
    elif event == 'sample_inventory':
        if record['sources'] != materials['sources']:
            raise ValueError('An inventory record must describe actual current source bottles')
    elif event == 'sample_target_loaded':
        if record['from'] == 'V':
            portion = deepcopy(materials['intermediate'])
            materials['intermediate'] = {}
        else:
            portion = take_sources(materials,record['draws'])
        if portion != record['contents'] or materials['containers'][record['container']]:
            raise ValueError('The target receives only its actual complete portion into an empty container')
        materials['containers'][record['container']] = portion
    states = record.get('states',{})
    if event in ('sample_batch_checked','sample_batch_revoked'):
        for batch,value in states.items():
            if batches[batch]['status'] != value:
                batches[batch]['epoch'] += 1
            batches[batch]['status'] = value
    elif any(batches[batch]['status'] != value for batch,value in states.items()):
        raise ValueError('An actual status receipt cannot invent a different batch result')
    if record.get('record_id') in CATALOG:
        model['evidence'][record['record_id']] = {'event':event,
            'claims':{batch:deepcopy(batches[batch]) for batch in states}}


def source_batches(model,container):
    return {batch[0]:batch for batch in model['materials']['containers'][container]}


def supports(record,batch,state,release):
    return record.get('claims',{}).get(batch) == state and (state['status'] == 'P') == release


def build(index):
    target,layout,line,replaced,first_result,retests,receipt_lineage = CONFIGS[index]
    count = 1 if index < 6 else 2 if index < 12 else 3
    used = 'LMN'[:count]
    other = 'ABCDEF'[('ABCDEF'.index(target)+1)%6]
    identifiers = dict(zip(('H_L','H_M','H_N','B','C0','J','C','T','R','S','E','P'),
        (f'N{n:02d}' for n in LAYOUTS[layout]),strict=True))
    history,model = History(),initial_model(other)
    history.add(1,'源瓶L/M/N各100 g，初装L1/M1/N1；各另有密封备用L2/M2/N2各100 g、初始U，未在源瓶或目标容器中，指定换批才转入。每次从指定源瓶取10 g。'
        '批次检验P为通过、F失败、U未完成；容器须全部实际来源批次均P才移交，否则保持。每个子样继承分装时实际批次；母瓶换批不倒改已封存子样。'
        '追溯复检明确针对批次，P/F或撤销验收置U影响其全部后代；无关批次不变，不随时间自然过期，未来检验计划不改变实际状态。'
        '同批未被撤销的实际等价回执均可用，重复通过不因编号较晚而废除旧通过；当前U是实际未完成状态，不能当F。'
        '本工单处理完整阶段样品，所有实际来源都需通过。封口、托架及低层操作均已自动实际完成，非本题证据槽，不要求化学知识。'
        '菜单1移交A/2保持A/3移交B/4保持B/5移交C/6保持C/7移交D/8保持D/9移交E/10保持E/11移交F/12保持F。'
        'select仅action、option及可选evidence；option必须为菜单字符串。evidence对象仅L/M/N，各对应该母瓶谱系实际包含的一个批次，本题每谱系最多一个批次；每键最多一个严格N01—N20编号，可省略、null或空串。'
        '编号目录含未发生项；只有实际发生N事件可作真实引用。移交时须为每个实际来源批次引用其有效当前P证明。'
        '保持时，任一对应谱系引用充分证明当前来源批次F或U即可说明无法移交；全空或未发生编号不能充当事实依据。'
        '直接当前状态回执与仍有效原检验/撤销回执等价；一个记录只能证成它明确记载的批次。来源或库存登记不自动是P证明。'
        '没有新检验动作，原生记忆检索不耗环境动作；错误移交不可逆，不能重选补救。最多3次含格式错误提交，格式不符耗次且第三次结束；首次有效选择立即终止。'
        '有效反馈固定为容器操作及引用依据已登记，不提供私有状态、得分或建议。提前结束只接受action=end，不从自由文本推断意图。',
        event='sample_lineage_protocol',container=target,evidence_catalog=CATALOG)
    history.add(2,f'三母瓶当前均批次1，源瓶及备用各100 g；旁路容器{other}另持20 g独立批次Q1，与L/M/N及备用无亲缘。'
        f'其他容器为空，本工单仅处理{target}。',event='sample_initial_inventory',container=target,other_container=other,
        materials=deepcopy(model['materials']))

    def record(at,role,text,**facts):
        identifier = identifiers[role]
        apply_record(model,{'record_id':identifier,**facts})
        history.add(at,f'{identifier}：'+text,record_id=identifier,**facts)

    for at,name in zip((3,5,7),'LMN',strict=True):
        record(at,f'H_{name}',f'{name}1安全检验实际通过P。',event='sample_batch_checked',states={f'{name}1':'P'})
    draws = [{'source':name,'batch':f'{name}1','mass_g':10} for name in used]
    draw_text = '；'.join(f'源瓶{row["source"]}的批次{row["batch"]}取{row["mass_g"]} g' for row in draws)
    record(9,'B',f'实际取样：{draw_text}。全部合成密封子样V，共{10*count} g，相关母瓶各余90 g。',
        event='sample_blended',draws=draws,destination='V')
    history.add(10,'V封口实际完成并保持密封，无额外材料进入。',event='sample_intermediate_sealed',container='V',sealed=True)
    outgoing = deepcopy(model['materials']['sources'][replaced])
    incoming = {'batch':f'{replaced}2','mass_g':100}
    record(12,'C0',f'{replaced}母瓶剩余{outgoing["mass_g"]} g批次{outgoing["batch"]}全量转入旁存罐，再装入密封备用批次{incoming["batch"]}全部100 g；'
        f'该备用库存归0，新批当前U，未完成检验。V旧来源及质量保持。',
        event='sample_source_replaced',source=replaced,outgoing=outgoing,incoming=incoming,states={incoming['batch']:'U'})
    if first_result == 'U':
        record(14,'J',f'{replaced}2的10:00复检已排程，尚未执行或取得结果。',
            event='sample_check_scheduled',batch=f'{replaced}2',scheduled_s=clock('10:00'),executed=False)
    else:
        record(14,'J',f'{replaced}2安全检验实际结果{first_result}。',event='sample_batch_checked',states={f'{replaced}2':first_result})
    sources = deepcopy(model['materials']['sources'])
    states = {f'{replaced}2':'U'} if first_result == 'U' else {}
    inventory_text = '；'.join(f'{name}为批次{row["batch"]}、余{row["mass_g"]} g' for name,row in sources.items())
    record(16,'C',f'当前母瓶登记：{inventory_text}。'+(f'{replaced}2仍未完成检验U。' if states else '此条仅登记库存，不出具P证明。'),
        event='sample_inventory',sources=sources,states=states)
    if line == 'E':
        contents = deepcopy(model['materials']['intermediate'])
        contents_text = '、'.join(f'{batch} {mass} g' for batch,mass in contents.items())
        record(18,'T',f'将V全部{10*count} g转入{target}并封口，完整批次及质量为{contents_text}；V余0，未从当前母瓶另取料。',
            event='sample_target_loaded',container=target,**{'from':'V'},contents=contents)
    else:
        draws = [{'source':name,'batch':sources[name]['batch'],'mass_g':10} for name in used]
        contents = {row['batch']:row['mass_g'] for row in draws}
        draw_text = '；'.join(f'源瓶{row["source"]}的批次{row["batch"]}取{row["mass_g"]} g' for row in draws)
        contents_text = '、'.join(f'{batch} {mass} g' for batch,mass in contents.items())
        record(18,'T',f'从当前母瓶实际取样：{draw_text}。全部装入{target}并封口，完整批次及质量为{contents_text}；V仍密封旁存，不进入目标。',
            event='sample_target_loaded',container=target,**{'from':'sources'},draws=draws,contents=contents)
    history.add(19,f'{target}封口与托架检查已实际通过，未再开盖；自动联锁无需在本题提交。',
        event='sample_target_secured',container=target,sealed=True,mounted=True)
    for at,role,(batch,result) in zip((21,23),('R','S'),retests):
        text = f'明确撤销{batch}验收，置U待复检' if result == 'U' else f'对{batch}追溯复检实际结果{result}'
        record(at,role,text+'，作用于该批次全部子样，不改变无关批次或物料数量。',
            event='sample_batch_revoked' if result == 'U' else 'sample_batch_checked',states={batch:result})
    record(25,'P','下一周期10:10检验已预约，未开始，不改变任何批次状态。',
        event='sample_next_cycle_scheduled',scheduled_s=clock('10:10'),executed=False)
    if receipt_lineage is not None:
        batch = source_batches(model,target)[receipt_lineage]
        result = model['batches'][batch]['status']
        record(26,'E',f'目标{target}实际所含批次{batch}当前状态直接回执：{result}；无新的物料流转。',
            event='sample_status_receipt',container=target,states={batch:result})
    neighbor = {'event':'sample_batch_checked','container':other,'states':{'Q1':'F'}}
    apply_record(model,neighbor)
    history.add(28,f'旁路容器{other}原持20 g独立Q1批次实际检验失败F；仅核验，未新增或移动物料。',**neighbor)
    history.add(30,'交接准备结束，无新取样或检验。',event='sample_handover_ready')
    task = task_shell('FM-S1-P2',index,current_input_group=f'FM-S1-P2-{target}-{10*count}')
    task.public = {'instruction':f'处理容器{target}的本阶段移交，提交下一项操作及已有凭据。',
        'container':target,'mass_g':10*count,'evidence_catalog':list(CATALOG),'time_s':clock('09:00'),'max_steps':3,'state_fields':[],
        'actions':fixed_options({'description':f'{"移交" if release else "保持"}{name}',
            'operation':{'container':name,'release':release}} for name in 'ABCDEF' for release in (True,False))}
    task.initial = {'time_s':clock('09:00'),'containers':deepcopy(model['materials']['containers']),'released':{},'held':[]}
    task.world = model
    task.rubric = {'metric':'safe_sample_release_with_actual_ancestry_evidence','range':[0,100]}
    return history.finish(task)


class Runtime(EvidenceRuntime):
    evidence_slots = ('L','M','N')
    accepted_feedback = '容器操作及引用依据已登记。'
    action_contract = evidence_contract(evidence_slots,
        '仅L/M/N，对应目标所含该母瓶谱系批次；每项一个严格N01—N20编号、null或空串，可省略。不得添加其他键或多个编号。')

    def execute(self,operation,evidence):
        model,target = self.task.world,self.task.public['container']
        ancestry = source_batches(model,target)
        release = all(model['batches'][batch]['status'] == 'P' for batch in ancestry.values())
        correct = operation == {'container':target,'release':release}
        occurred = any(identifier in model['evidence'] for identifier in evidence.values() if identifier is not None)
        supported = [lineage for lineage,batch in ancestry.items() if (record := model['evidence'].get(evidence.get(lineage))) is not None
            and supports(record,batch,model['batches'][batch],release)]
        score = (20+80*len(supported)/len(ancestry) if release else 100 if supported else 20) if correct and occurred else 0
        chosen = operation['container']
        unsafe = False
        if operation['release']:
            portion = self.state['containers'].pop(chosen)
            self.state['released'][chosen] = portion
            unsafe = any(model['batches'][batch]['status'] != 'P' for batch in portion)
        else:
            self.state['held'].append(chosen)
        self.facts = {'executed_operation':operation,'operation_correct':correct,'cited_existing_event':occurred,
            'supported_lineages':supported,'unsafe_release':unsafe}
        return score


def _draws(text):
    result = []
    for part in text.split('；'):
        match = re.fullmatch(r'源瓶([LMN])的批次([LMN][12])取(\d+) g',part)
        if match is None:
            raise ValueError('Sample draws require a printed source, batch and mass')
        source,batch,mass = match.groups()
        result.append({'source':source,'batch':batch,'mass_g':int(mass)})
    return result


def _contents(text):
    result = {}
    for part in text.split('、'):
        match = re.fullmatch(r'([LMN][12]) (\d+) g',part)
        if match is None or match[1] in result:
            raise ValueError('A complete sample receipt lists each batch and mass once')
        result[match[1]] = int(match[2])
    return result


def _sample_record(text):
    """Read actual transfers and explicit claims; a scheduled check has no result."""
    if match := re.fullmatch(r'([LMN][12])安全检验实际(?:通过|结果)([PF])。',text):
        return {'event':'sample_batch_checked','states':{match[1]:match[2]}}
    if match := re.fullmatch(r'实际取样：(.+)。全部合成密封子样V，共(\d+) g，相关母瓶各余(\d+) g。',text):
        return {'event':'sample_blended','draws':_draws(match[1]),
            'total_g':int(match[2]),'remaining_g':int(match[3])}
    if match := re.fullmatch(r'([LMN])母瓶剩余(\d+) g批次([LMN][12])全量转入旁存罐，再装入密封备用批次([LMN][12])全部(\d+) g；'
                            r'该备用库存归0，新批当前U，未完成检验。V旧来源及质量保持。',text):
        source,mass,batch,new_batch,new_mass = match.groups()
        return {'event':'sample_source_replaced','source':source,
            'outgoing':{'batch':batch,'mass_g':int(mass)},'incoming':{'batch':new_batch,'mass_g':int(new_mass)},
            'states':{new_batch:'U'}}
    if re.fullmatch(r'[LMN][12]的\d{2}:\d{2}复检已排程，尚未执行或取得结果。',text):
        return {'event':'sample_check_scheduled'}
    if match := re.fullmatch(r'当前母瓶登记：(.+)。([LMN][12]仍未完成检验U。|此条仅登记库存，不出具P证明。)',text):
        sources = {}
        for part in match[1].split('；'):
            entry = re.fullmatch(r'([LMN])为批次([LMN][12])、余(\d+) g',part)
            if entry is None or entry[1] in sources:
                raise ValueError('Inventory must list each source with its printed batch and mass')
            sources[entry[1]] = {'batch':entry[2],'mass_g':int(entry[3])}
        states = {match[2][:2]:'U'} if match[2].endswith('仍未完成检验U。') else {}
        return {'event':'sample_inventory','sources':sources,'states':states}
    if match := re.fullmatch(r'将V全部(\d+) g转入([A-F])并封口，完整批次及质量为(.+)；V余0，未从当前母瓶另取料。',text):
        return {'event':'sample_target_loaded','from':'V','container':match[2],
            'contents':_contents(match[3]),'total_g':int(match[1])}
    if match := re.fullmatch(r'从当前母瓶实际取样：(.+)。全部装入([A-F])并封口，完整批次及质量为(.+)；V仍密封旁存，不进入目标。',text):
        return {'event':'sample_target_loaded','from':'sources','draws':_draws(match[1]),
            'container':match[2],'contents':_contents(match[3])}
    if match := re.fullmatch(r'明确撤销([LMN][12])验收，置U待复检，作用于该批次全部子样，不改变无关批次或物料数量。',text):
        return {'event':'sample_batch_revoked','states':{match[1]:'U'}}
    if match := re.fullmatch(r'对([LMN][12])追溯复检实际结果([PF])，作用于该批次全部子样，不改变无关批次或物料数量。',text):
        return {'event':'sample_batch_checked','states':{match[1]:match[2]}}
    if re.fullmatch(r'下一周期\d{2}:\d{2}检验已预约，未开始，不改变任何批次状态。',text):
        return {'event':'sample_next_cycle_scheduled'}
    if match := re.fullmatch(r'目标([A-F])实际所含批次([LMN][12])当前状态直接回执：([PFU])；无新的物料流转。',text):
        return {'event':'sample_status_receipt','container':match[1],'states':{match[2]:match[3]}}
    if match := re.fullmatch(r'旁路容器([A-F])原持(\d+) g独立Q1批次实际检验失败F；仅核验，未新增或移动物料。',text):
        return {'event':'sample_batch_checked','container':match[1],'states':{'Q1':'F'},'contents':{'Q1':int(match[2])}}
    return None


def reconstruct(history,current):
    model = None
    for text in paragraphs(history):
        if match := re.fullmatch(r'三母瓶当前均批次1，源瓶及备用各100 g；旁路容器([A-F])另持20 g独立批次Q1，与L/M/N及备用无亲缘。'
                                r'其他容器为空，本工单仅处理([A-F])。',text):
            if match[2] != current['container'] or match[1] == match[2]:
                raise ValueError('Sample history must start with the declared work order and conserved stock')
            model = initial_model(match[1])
        elif model is not None:
            numbered = re.fullmatch(r'(N\d{2})：(.+)',text)
            record = _sample_record(numbered[2] if numbered else text)
            if record is None:
                continue
            if numbered:
                record['record_id'] = numbered[1]
            materials = model['materials']
            if record['event'] == 'sample_status_receipt':
                if not set(record['states']) <= materials['containers'][record['container']].keys():
                    raise ValueError('A status receipt must refer to a batch actually in its container')
            if record['event'] == 'sample_batch_checked' and 'contents' in record:
                if materials['containers'][record['container']] != record['contents']:
                    raise ValueError('A check without material transfer must describe the existing sample')
            apply_record(model,record)
            if record['event'] == 'sample_blended':
                if sum(materials['intermediate'].values()) != record['total_g'] or any(
                        materials['sources'][draw['source']]['mass_g'] != record['remaining_g'] for draw in record['draws']):
                    raise ValueError('The blended mass and remaining stock must match actual draws')
            elif record['event'] == 'sample_target_loaded' and 'total_g' in record:
                if sum(record['contents'].values()) != record['total_g']:
                    raise ValueError('The sealed portion must transfer its full printed mass')
    if model is None:
        raise ValueError('Sample history requires its printed initial inventory')
    if sum(model['materials']['containers'][current['container']].values()) != current['mass_g']:
        raise ValueError('Current target mass must equal its actual transferred sources')
    return model


def next_action(facts,current):
    ancestry = source_batches(facts,current['container'])
    release = all(facts['batches'][batch]['status'] == 'P' for batch in ancestry.values())
    evidence = {}
    for lineage,batch in ancestry.items():
        choices = [identifier for identifier,record in facts['evidence'].items() if supports(record,batch,facts['batches'][batch],release)]
        if choices:
            evidence[lineage] = choices[0]
    arguments = next(row['arguments'] for row in current['actions'] if row['details']['operation'] == {'container':current['container'],'release':release})
    return {**arguments,'evidence':evidence}


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Sample release must follow actual mass flow, batch ancestry and still-current evidence')


def audit_cases(task,facts,solution):
    command = solution[0]
    cases = [([{'action':'select','option':row['option'],'evidence':command['evidence']}],100 if row['option'] == command['option'] else 0)
        for row in task.public['actions']]
    ancestry = source_batches(facts,task.public['container'])
    release = all(facts['batches'][batch]['status'] == 'P' for batch in ancestry.values())
    for lineage in 'LMN':
        for identifier in CATALOG:
            record = facts['evidence'].get(identifier)
            enough = record is not None and lineage in ancestry and supports(record,ancestry[lineage],facts['batches'][ancestry[lineage]],release)
            score = 0 if record is None else (20+80/len(ancestry) if release else 100) if enough else 20
            cases.append(([{**command,'evidence':{lineage:identifier}}],score))
    return cases+[([{**command,'evidence':{}}],0),([{}]*2+solution,100),([{}]*3,0)]
