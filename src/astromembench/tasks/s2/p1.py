"""FM-S2-P1: complete scan arcs and independent, entity-bound field validity."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'H{i:02d}' for i in range(1,13))
CAPABILITIES = {
    'A':('012345',12),'B':('012',12),'C':('123',12),'D':('234',12),'E':('345',12),
    'F':('450',12),'G':('501',12),'H':('0123',10),'I':('2345',10),'J':('0145',10),
    'L':('01345',20),'M':('01245',20),'N':('12345',20),'Z':('',12),
}
# Target, distance, A/B events, spare results, partial scope, dispatch, receipts,
# installed heads, independently authored menu and evidence permutations.
CONFIGS = (
    ('23',10,('R:H','R:I'),'MG',('备R','本S'),'Ap Bc Ad Bp Ac Bd','Bc Ad Ap Bd Ac Bp',('A17','B09'),
     (11,3,7,1,8,5,12,6,10,13,2,4,9),(9,1,2,11,6,4,10,8,7,3,12,5)),
    ('50',10,('R:J','R:G'),'DM',('备S','本R'),'Ad Bp Ac Bc Ap Bd','Bp Ac Bd Ap Bc Ad',('A17','B26'),
     (8,1,12,5,11,4,9,3,6,2,13,10,7),(11,3,7,8,12,9,1,4,5,6,2,10)),
    ('12',12,('R:B','R:C'),'EJ',('本R','本S'),'Bp Ad Bc Ap Bd Ac','Ap Bd Ac Bp Ad Bc',('A17','B09'),
     (13,7,3,10,2,6,12,5,1,11,8,9,4),(3,12,5,10,11,9,7,6,2,1,4,8)),
    ('01',12,('O','U'),'BN',('本S','本R'),'Ap Ad Bp Bc Ac Bd','Bc Ad Ap Bd Bp Ac',('A42','B09'),
     (10,8,3,9,1,7,2,5,11,4,6,12,13),(5,10,11,6,8,1,2,12,4,9,7,3)),
    ('01',11,('R:H','R:I'),'MG',('本R','本S'),'Bp Ap Ad Bc Bd Ac','Ad Ap Bc Bd Ac Bp',('A17','B26'),
     (5,13,2,10,4,9,6,12,1,7,3,8,11),(10,6,5,3,7,2,9,4,11,1,8,12)),
    ('24',12,('R:B','R:C'),'NL',('本S','备R'),'Ac Bp Bd Ap Ad Bc','Bc Bd Ap Ac Bp Ad',('A42','B09'),
     (12,1,9,4,6,8,3,13,10,7,2,11,5),(1,4,12,8,10,7,5,9,2,11,6,3)),
    ('01',14,('V:L','V:M'),'CF',('备R','本S'),'Bd Ap Bc Ac Ad Bp','Ap Ad Bc Bp Ac Bd',('A17','B09'),
     (7,2,11,4,13,8,1,10,5,12,3,9,6),(9,8,1,2,5,3,7,6,11,4,12,10)),
    ('45',20,('V:M','X:A'),'AL',('本R','本S'),'Ad Bc Ap Bd Ac Bp','Bp Ac Ad Bc Bd Ap',('A42','B09'),
     (11,6,1,13,7,10,4,8,3,2,9,5,12),(6,11,9,12,7,4,5,2,1,10,3,8)),
    ('50',14,('V:L','V:M'),'IN',('本S','备S'),'Bp Ac Ad Bc Ap Bd','Bc Ap Bd Ac Ad Bp',('A42','B26'),
     (8,13,4,11,2,5,9,6,12,10,1,3,7),(1,9,11,8,5,3,7,6,12,10,2,4)),
    ('23',12,('V:H','O'),'NC',('本R','本S'),'Ac Bc Bd Ad Bp Ap','Bd Bp Ac Ad Ap Bc',('A17','B09'),
     (13,4,10,6,12,2,9,11,7,3,8,1,5),(11,2,3,1,10,8,4,6,7,9,5,12)),
    ('345',12,('V:E','V:N'),'MJ',('本S','备R'),'Bc Bp Ap Bd Ad Ac','Ac Ad Bp Ap Bc Bd',('A42','B09'),
     (10,5,8,2,7,13,4,1,12,6,9,3,11),(7,2,11,4,5,1,6,10,12,8,9,3)),
    ('23',14,('V:L','V:M'),'NC',('本S','本R'),'Bp Bd Ac Ap Bc Ad','Ac Bp Bd Ap Ad Bc',('A42','B09'),
     (9,4,13,7,5,12,2,8,11,3,6,1,10),(1,5,8,2,4,9,10,6,12,11,7,3)),
    ('01',20,('X:M','V:L'),'NH',('本S','备R'),'Bd Bp Ap Ad Bc Ac','Ap Bd Bc Ac Bp Ad',('A42','B26'),
     (12,6,4,8,2,11,7,5,9,1,10,13,3),(3,1,6,12,5,2,10,4,9,8,11,7)),
    ('12',12,('V:C','V:B'),'ME',('备R','本S'),'Ap Bp Ac Bd Bc Ad','Ac Ap Bd Bc Ad Bp',('A42','B09'),
     (11,1,6,10,8,3,7,12,4,13,9,5,2),(12,10,6,8,9,11,1,5,3,7,4,2)),
    ('24',20,('V:M','X:D'),'NL',('本S','本R'),'Bd Ac Ad Bp Ap Bc','Bc Ap Bd Bp Ac Ad',('A42','B26'),
     (13,7,3,10,2,6,12,5,1,11,8,9,4),(1,9,10,3,11,7,6,8,12,5,4,2)),
    ('50',21,('V:L','V:M'),'HJ',('本R','备S'),'Bc Bd Ap Ac Ad Bp','Ap Ad Bc Ac Bd Bp',('A17','B09'),
     (6,11,9,3,10,1,13,4,2,8,12,7,5),(9,1,2,11,6,4,10,8,7,3,12,5)),
)


def capability(code):
    sectors,metres = CAPABILITIES[code]
    return {'S':sorted(map(int,sectors)),'R':metres}


def arc(program):
    return [(program+i)%6 for i in range(3)]


def describe(fields):
    return '；'.join('获准角区S为'+('、'.join(map(str,value)) if value else '空') if field == 'S'
        else f'有效测距上界R={value}米' for field,value in fields.items())


def entity_text(entity):
    return f'{entity["station"]}站扫描头{entity["head"]}、配置{entity["configuration"]}'


def build(index):
    targets,metres,chains,spare_codes,partial,dispatch,receipts,serials,menu,ids = CONFIGS[index]
    identifiers = [f'H{n:02d}' for n in ids]
    installed,spares,old = {},{},{}
    current_capabilities,jobs = {},{}
    for station,chain,serial,spare_code,scope in zip('AB',chains,serials,spare_codes,partial,strict=True):
        heads = ('A17','A42') if station == 'A' else ('B26','B09')
        spare_serial = next(head for head in heads if head != serial)
        installed[station] = {'station':station,'head':serial,'configuration':'K2' if chain[0] == 'V' else 'K1'}
        spares[station] = {'station':station,'head':spare_serial,'configuration':'K1' if chain[0] == 'V' else 'K2'}
        old[station] = spares[station] if chain[0] == 'V' else installed[station]
        current_capabilities[station] = capability('A' if chain == 'O' else 'Z' if chain[0] in 'UX' else chain[-1])
        jobs[station+'c'] = {**installed[station],'scope':['S','R'],'fields':current_capabilities[station]}
        jobs[station+'d'] = {**spares[station],'scope':['S','R'],'fields':capability(spare_code)}
        partial_entity = installed[station] if scope[0] == '本' else spares[station]
        partial_values = current_capabilities[station] if scope[0] == '本' else capability(spare_code)
        jobs[station+'p'] = {**partial_entity,'scope':[scope[1]],'fields':{scope[1]:partial_values[scope[1]]}}
    history = History()
    history.add(1,'A/B两扫描器的扇区0—5环状相邻，6等同0。程序j完整扫过{j,(j+1)mod6,(j+2)mod6}，一次只执行整段程序，不能跳过坏角区或拼接两段。'
        '目标T必须全含于程序，完整三个扇区均须在所用头当前获准S内，且当前距离r≤该头当前R米；扫过其他获准角区允许。'
        'S是功能授权而非是否能机械转到，测距正常不证明角区获准。仅当前实际安装的序列号和配置可执行本轮扫描，备件只在隔离台检验，未来计划不改变安装。'
        '故障撤销S不改变R；维修或复位不自动恢复角区授权，实际检验只更新明示字段。未改变字段的原证据持续有效，同值复核不撤销原证；'
        '字段经历改变再变回时，已失效旧证不复活；换头不能跨头复用任一字段。执行期间安装与已验能力不再改变。'
        '所有12程序和保持待机都可提交，不按能力隐藏。合法完整且覆盖目标的扫描须引据覆盖当前头S与R两个字段，完整证或两份有效分项组合均可。'
        '只有两台均无任何合法完整程序时应保持，并分别引据证明；当前角区或测距字段若单独已排除全部候选弧，也可证明该台不能用。'
        'select必须恰含action、option、evidence，option是菜单数字字符串，evidence为H01—H12字符串数组，先去重再检查最多2不同ID，可空。'
        '只接受单字段action=end结束。总调用最多3次；格式错仅提示字段并耗次，不执行扫描。首次合法业务选择立即执行并终局，反馈统一“勘察扫描与依据已存档。”。'
        '错扫不能回滚重选，没有合格本轮成果；不产生永久硬件损坏。无在线试扫或查询能力操作；原生记忆访问不计本题动作。',event='capability_protocol')
    claims = [{**old[station],'fields':capability('A')} for station in 'AB']
    history.add(2,identifiers[0]+'：两站初始实际安装并完成校准：'+'；'.join(entity_text(c)+'，'+describe(c['fields']) for c in claims)+'。',
        record_id=identifiers[0],event='initial_scan_certificate',claims=claims)
    for station,chain in zip('AB',chains,strict=True):
        entity = old[station]
        if chain == 'O':
            history.add(3,entity_text(entity)+'已清洁镜罩，无功能失效。',event='scan_cover_cleaned',**entity)
        elif chain[0] == 'V':
            history.add(3,entity_text(entity)+'已实际从转台卸下。',event='scan_head_removed',**entity)
        elif chain[0] == 'X':
            fields = capability(chain[-1])
            history.add(3,entity_text(entity)+'完成实际整机验收，'+describe(fields)+'。',event='scan_earlier_certificate',fields=fields,**entity)
        else:
            history.add(3,entity_text(entity)+'扫描服务故障，全部S授权撤销，测距上界不变。',event='scan_sector_fault',**entity)
    for station,chain in zip('AB',chains,strict=True):
        if chain[0] == 'X':
            history.add(4,entity_text(old[station])+'再次实际发生扫描故障，全部S授权撤销，测距上界不变。',event='scan_sector_fault',**old[station])
    for station,chain in zip('AB',chains,strict=True):
        state_text = {'O':'在用配置未变，无功能失效','R':'实际维修完成，尚未校准','V':'已实际装入转台，尚待验收','U':'实际复位完成，尚无角区恢复验证','X':'实际复位完成，尚无角区恢复验证'}[chain[0]]
        history.add(6,entity_text(installed[station])+f'，{state_text}；'+entity_text(spares[station])+'在隔离台作为下一班备件，本轮未安装。',
            event='scan_installation_handover',installed=installed[station],spare=spares[station])
    job_ids = dict(zip(dispatch.split(),('J11','J23','J08','J36','J17','J42'),strict=True))
    bindings = {job_ids[role]:{key:deepcopy(job[key]) for key in ('station','head','configuration','scope')} for role,job in jobs.items()}
    bindings = {job_ids[role]:bindings[job_ids[role]] for role in dispatch.split()}
    history.add(7,'实际派发六项验收：'+'；'.join(f'{job_id}：{entity_text(binding)}，检验范围'+('/'.join(binding['scope'])) for job_id,binding in bindings.items())+'。分项只报告所检字段，不推断其他字段。',
        event='scan_jobs_dispatched',jobs=bindings)
    for slot,(at,role) in enumerate(zip((9,12,15,19,23,26),receipts.split(),strict=True),1):
        job = jobs[role]
        identity = '' if index >= 12 else entity_text(job)+'，检验范围'+('/'.join(job['scope']))+'，'
        fields = deepcopy(job['fields'])
        detail = {} if index >= 12 else {key:deepcopy(job[key]) for key in ('station','head','configuration','scope')}
        history.add(at,f'{identifiers[slot]}：工单{job_ids[role]}实际检验回执，{identity}{describe(fields)}。'+('角区授权为空，限制未解除。' if fields.get('S') == [] else ''),
            record_id=identifiers[slot],event='scan_job_receipt',job_id=job_ids[role],fields=fields,**detail)
    outside = {'station':'C','head':'C31','configuration':'K1','fields':{'S':list(range(6)),'R':30}}
    history.add(27,identifiers[7]+'：站外'+entity_text(outside)+'完成验收，'+describe(outside['fields'])+'。',record_id=identifiers[7],event='outside_scan_certificate',claims=[outside])
    history.add(28,identifiers[8]+'：下一班10:00计划更换两站扫描头，目前未执行。',record_id=identifiers[8],event='scan_replacement_planned',scheduled_s=clock('10:00'))
    history.add(28,identifiers[9]+'：别地块已完成勘察成果归档，不是本轮成果。',record_id=identifiers[9],event='other_plot_archived')
    history.add(29,identifiers[10]+'：站点供电正常，未实施功能校准。',record_id=identifiers[10],event='scan_power_checked')
    history.add(29,identifiers[11]+'：支架固定确认，未实施功能校准。',record_id=identifiers[11],event='scan_bracket_checked')
    history.add(30,'站点定位完成，目标均在可指向区域。',event='scan_positioned')
    base = [{'description':f'{station}{j}：扫描器{station}完整执行程序{j}，扫描扇区{arc(j)}',
             'operation':{'scanner':station,'program':j}} for station in 'AB' for j in range(6)]
    base.append({'description':'H：保持待机','operation':{'hold':True}})
    task = task_shell('FM-S2-P1',index)
    task.design['scoring_version'] = 'fm-s2-p1/6'
    task.public = {'instruction':f'当前地块目标扇区T={list(map(int,targets))}，距离r={metres}米。提交完整勘察扫描或保持，并附已有依据。',
        'target_sectors':list(map(int,targets)),'distance_m':metres,'programs':{str(j):arc(j) for j in range(6)},
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':fixed_options(base[n-1] for n in menu)}
    task.initial = {'scans':[],'qualified_survey':False}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'valid complete scan: 50 per supported current installed-head field S/R; otherwise 0; correct hold: 50 per scanner proved unable'}
    return history.finish(task)


ENTITY = r'[ABC]站扫描头[ABC]\d+、配置K\d+'


def _entity(text):
    match = re.fullmatch(r'([ABC])站扫描头([ABC]\d+)、配置(K\d+)',text)
    if match is None:
        raise ValueError('A scan certificate must identify its station, serial and configuration')
    return dict(zip(('station','head','configuration'),match.groups(),strict=True))


def _fields(text):
    fields = {}
    for part in text.split('；'):
        if match := re.fullmatch(r'获准角区S为(空|[0-5](?:、[0-5])*)',part):
            field,value = 'S',[] if match[1] == '空' else sorted(set(map(int,match[1].split('、'))))
        elif match := re.fullmatch(r'有效测距上界R=(\d+)米',part):
            field,value = 'R',int(match[1])
        else:
            raise ValueError('A capability receipt must explicitly print each measured field')
        if field in fields:
            raise ValueError('A capability receipt cannot give multiple results for one field')
        fields[field] = value
    return fields


def _scan_record(text):
    if match := re.fullmatch(r'两站初始实际安装并完成校准：(.+)。',text):
        claims = []
        for part in re.split(r'；(?=[ABC]站扫描头)',match[1]):
            claim = re.fullmatch(rf'({ENTITY})，(.+)',part)
            if claim is None:
                raise ValueError('Initial calibration must print each installed head and its fields')
            claims.append({**_entity(claim[1]),'fields':_fields(claim[2])})
        return {'event':'initial_scan_certificate','claims':claims}
    if match := re.fullmatch(rf'({ENTITY})已实际从转台卸下。',text):
        return {'event':'scan_head_removed',**_entity(match[1])}
    if match := re.fullmatch(rf'({ENTITY})(?:扫描服务故障|再次实际发生扫描故障)，全部S授权撤销，测距上界不变。',text):
        return {'event':'scan_sector_fault',**_entity(match[1])}
    if match := re.fullmatch(rf'({ENTITY})完成实际整机验收，(.+)。',text):
        return {'event':'scan_earlier_certificate',**_entity(match[1]),'fields':_fields(match[2])}
    if match := re.fullmatch(rf'({ENTITY})，(?:在用配置未变，无功能失效|实际维修完成，尚未校准|已实际装入转台，尚待验收|实际复位完成，尚无角区恢复验证)；({ENTITY})在隔离台作为下一班备件，本轮未安装。',text):
        return {'event':'scan_installation_handover','installed':_entity(match[1]),'spare':_entity(match[2])}
    if match := re.fullmatch(r'实际派发六项验收：(.+)。分项只报告所检字段，不推断其他字段。',text):
        jobs = {}
        for part in match[1].split('；'):
            job = re.fullmatch(rf'(J\d+)：({ENTITY})，检验范围(S/R|S|R)',part)
            if job is None or job[1] in jobs:
                raise ValueError('Each dispatched job must bind a distinct ID to one entity and field scope')
            jobs[job[1]] = {**_entity(job[2]),'scope':job[3].split('/')}
        return {'event':'scan_jobs_dispatched','jobs':jobs}
    if match := re.fullmatch(rf'工单(J\d+)实际检验回执，(?:({ENTITY})，检验范围(S/R|S|R)，)?(.+?)。(?:角区授权为空，限制未解除。)?',text):
        record = {'event':'scan_job_receipt','job_id':match[1],'fields':_fields(match[4])}
        if match[2]:
            record.update(_entity(match[2]),scope=match[3].split('/'))
        return record
    if match := re.fullmatch(rf'站外({ENTITY})完成验收，(.+)。',text):
        return {'event':'outside_scan_certificate','claims':[{**_entity(match[1]),'fields':_fields(match[2])}]}
    return {}


def reconstruct(history,current):
    installed,heads,evidence,jobs = {},{},{},{}

    def head(entity):
        serial = entity['head']
        if serial not in heads:
            heads[serial] = {key:entity[key] for key in ('station','configuration')}
            heads[serial]['fields'] = {field:{'value':None,'revision':0} for field in ('S','R')}
        if any(heads[serial][key] != entity[key] for key in ('station','configuration')):
            raise ValueError('A head must retain its recorded station and installation configuration')
        return heads[serial]

    def certificate(entity,fields):
        state = head(entity)
        proof = {key:entity[key] for key in ('station','head','configuration')}
        proof['fields'] = {}
        for field,value in fields.items():
            old = state['fields'][field]
            if old['value'] != value:
                state['fields'][field] = {'value':deepcopy(value),'revision':old['revision']+1}
            proof['fields'][field] = deepcopy(state['fields'][field])
        return proof

    for text in paragraphs(history):
        numbered = re.fullmatch(r'(H\d{2})：(.+)',text)
        record = _scan_record(numbered[2] if numbered else text)
        event = record.get('event')
        proofs = []
        if event == 'initial_scan_certificate':
            for claim in record['claims']:
                installed[claim['station']] = {key:claim[key] for key in ('station','head','configuration')}
                proofs.append(certificate(claim,claim['fields']))
        elif event == 'scan_head_removed':
            if installed[record['station']]['head'] != record['head']:
                raise ValueError('Only the actually installed head can be removed')
            del installed[record['station']]
        elif event == 'scan_sector_fault':
            state = head(record)['fields']['S']
            state.update(value=[],revision=state['revision']+1)
        elif event == 'scan_earlier_certificate':
            certificate(record,record['fields'])
        elif event == 'scan_installation_handover':
            entity = record['installed']
            head(entity)
            head(record['spare'])
            installed[entity['station']] = deepcopy(entity)
        elif event == 'scan_jobs_dispatched':
            jobs = deepcopy(record['jobs'])
        elif event == 'scan_job_receipt':
            entity = jobs[record['job_id']]
            if set(record['fields']) != set(entity['scope']) or any(record[key] != entity[key] for key in ('station','head','configuration','scope') if key in record):
                raise ValueError('A receipt must cover exactly its dispatched entity and fields')
            proofs.append(certificate(entity,record['fields']))
        elif event == 'outside_scan_certificate':
            proofs = [certificate(claim,claim['fields']) for claim in record['claims']]
        if numbered and numbered[1] in CATALOG:
            evidence[numbered[1]] = proofs
    return {'installed':installed,'heads':heads,'evidence':evidence,
            'target':current['target_sectors'],'distance_m':current['distance_m']}


def fields_for(facts,station):
    return facts['heads'][facts['installed'][station]['head']]['fields']


def legal_programs(facts,station):
    fields = fields_for(facts,station)
    sectors,metres = fields['S']['value'],fields['R']['value']
    return [j for j in range(6) if sectors is not None and metres is not None and facts['distance_m'] <= metres
            and set(facts['target']) <= set(arc(j)) <= set(sectors)]


def supported_fields(facts,station,references):
    entity = facts['installed'][station]
    current = fields_for(facts,station)
    return {field for identifier in references for proof in facts['evidence'].get(identifier,[])
            if all(proof[key] == entity[key] for key in ('station','head','configuration'))
            for field,claim in proof['fields'].items() if claim == current[field]}


def cannot_scan(facts,station,fields):
    current = fields_for(facts,station)
    return ('R' in fields and facts['distance_m'] > current['R']['value'] or
            'S' in fields and not any(set(facts['target']) <= set(arc(j)) <= set(current['S']['value']) for j in range(6)))


def evaluate(facts,operation,references):
    if operation.get('hold'):
        if any(legal_programs(facts,station) for station in 'AB'):
            return 0,False,[]
        supported = [station for station in 'AB' if cannot_scan(facts,station,supported_fields(facts,station,references))]
        return 50*len(supported),True,supported
    station = operation['scanner']
    qualified = operation['program'] in legal_programs(facts,station)
    fields = supported_fields(facts,station,references)
    return (50*len(fields) if qualified else 0),qualified,sorted(fields)


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},
        'description':'H01—H12编号字符串数组；可空，重复先去重，再检查最多2个不同ID。'}}})

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
            entity = self.task.world['installed'][operation['scanner']]
            self.state['scans'].append({**entity,'program':operation['program'],'sectors':arc(operation['program']),'complete':True,'qualified':correct})
            self.state['qualified_survey'] = correct
        self.facts = {'executed_operation':operation,'operation_correct':correct,'supported':supported,'references':references}
        self.feedback = '勘察扫描与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('A valid complete survey or hold must be supported by at most two records')


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Installed entities and independent field revisions must follow the public events')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(3):
            for references in combinations(CATALOG,count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
