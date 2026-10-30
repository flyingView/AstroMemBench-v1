"""FM-S2-O3: serial pump/adapter capabilities and field-level evidence coverage."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'E{i:02d}' for i in range(1,17))
NODES = 'ABXYZ'
SERIALS = {'A':('A17','A42'),'B':('B26','B09'),'X':('X31','X08'),'Y':('Y14','Y37'),'Z':('Z22','Z05')}
INITIAL = dict(zip(NODES,('W4','N4','W4','N4','D2'),strict=True))
# Medium, minimum flow, regulated pressure, events, installed components, spares,
# partial fields, actual receipt order, explicit menu, independent record IDs.
CONFIGS = (
    ('W',2,4,('O','O','O','O','O'),'21212','N2 W4 D2 W4 N4','mNnMm',
     'Ac Yd Bp Xc Zp Ad Bc Xp Yc Zd Ap Bd Xd Yp Zc',
     (9,4,13,7,5,12,2,8,11,3,6,1,10),(12,3,15,7,1,10,5,16,9,4,13,8,2,11,6,14)),
    ('W',2,2,('R:W2','U','O','O','O'),'22111','N4 D2 W2 D4 N2','mNnMN',
     'Xd Ac Zp Bc Yp Xc Ad Yc Bp Zd Ap Bd Zc Xp Yd',
     (12,6,4,8,2,11,7,5,9,1,10,13,3),(9,1,13,6,16,4,11,2,14,7,3,12,5,15,8,10)),
    ('N',4,4,('R:D4','R:N2','O','U','R:D4'),'12212','W4 D4 N4 D2 W2','mnMmn',
     'Ad Zc Xp Yd Bc Ac Zd Bp Xc Yp Bd Ap Yc Zp Xd',
     (8,13,4,11,2,5,9,6,12,10,1,3,7),(8,16,10,1,13,5,3,12,7,15,9,2,14,6,11,4)),
    ('W',2,4,('O','R:D4','R:W2','O','R:D4'),'21221','N4 W2 D4 D2 N2','nmnMm',
     'Bp Yc Ac Xd Zp Bc Ad Yp Zc Xp Bd Zd Xc Ap Yd',
     (4,12,1,9,6,3,11,7,13,2,10,5,8),(1,10,5,14,7,12,16,3,11,6,4,13,8,2,15,9)),
    ('W',4,4,('R:W2','O','O','O','O'),'22211','D4 W2 N4 D2 W4','nMNmn',
     'Yp Bd Zc Ac Xd Yc Ap Xp Bc Zd Ad Yd Zp Bp Xc',
     (6,10,2,12,1,4,13,7,9,5,11,8,3),(6,13,8,2,15,11,7,14,4,12,5,16,1,9,3,10)),
    ('N',2,4,('O','O','O','R:N2','O'),'11122','N2 W4 D2 D4 W2','mNMnn',
     'Zc Bp Yd Xc Ap Zd Yc Ac Bc Xp Zp Ad Bd Yp Xd',
     (13,4,10,6,12,2,9,11,7,3,8,1,5),(16,9,1,5,12,6,10,4,13,2,14,3,7,11,8,15)),
    ('W',4,4,('V:D4','X:D4','V:W4','U','O'),'22122','N4 W2 D2 N4 W4','mNnmN',
     'Xp Zc Yd Bc Ac Xc Bd Yp Ad Zp Xd Yc Bp Zd Ap',
     (10,2,8,6,13,9,3,12,7,1,5,4,11),(13,6,11,3,9,15,2,7,16,5,12,4,10,8,14,1)),
    ('N',4,4,('V:D4','O','V:D4','X:N4','O'),'12122','W2 D4 W4 D2 N4','MnmmN',
     'Ac Zp Yc Bd Xp Ap Zc Bc Xd Yd Ad Xc Yp Zd Bp',
     (5,13,2,10,4,9,6,12,1,7,3,8,11),(15,5,9,13,1,3,12,10,7,8,6,14,11,4,2,16)),
    ('W',2,4,('V:D4','V:D4','V:W4','O','V:D4'),'21122','N2 W2 D2 D4 N4','nmnMm',
     'Bd Yp Ac Xc Zd Bc Yd Ap Xp Zc Bp Xd Yc Ad Zp',
     (8,1,12,5,11,4,9,3,6,2,13,10,7),(3,16,8,5,12,2,7,14,10,6,13,1,9,15,4,11)),
    ('W',4,2,('V:W2','V:N4','V:D4','O','O'),'21222','D4 W2 N4 W2 D4','nmNnM',
     'Ac Yd Bp Xc Zp Ad Bc Xp Yc Zd Ap Bd Xd Yp Zc',
     (11,6,1,13,7,10,4,8,3,2,9,5,12),(8,4,12,16,10,6,1,9,5,14,2,11,7,13,3,15)),
    ('W',2,2,('U','X:W4','U','X:D4','U'),'22212','W4 N4 D4 N2 W2','mmmnm',
     'Bc Xp Ad Zc Yp Bd Xc Zp Ac Yd Bp Zd Yc Ap Xd',
     (13,7,3,10,2,6,12,5,1,11,8,9,4),(10,5,14,2,16,8,12,6,3,15,7,13,1,11,9,4)),
    ('N',2,2,('V:D4','O','V:D2','O','O'),'11121','W2 D4 N4 D2 W4','nmmNn',
     'Ad Zc Xp Yd Bc Ac Zd Bp Xc Yp Bd Ap Yc Zp Xd',
     (7,2,11,4,13,8,1,10,5,12,3,9,6),(5,11,1,7,13,3,15,10,8,2,14,4,12,6,16,9)),
    ('N',4,4,('V:D4','X:N4','V:D4','V:N4','O'),'21111','N2 W4 W2 D2 D4','nmmnN',
     'Bp Yc Ac Xd Zp Bc Ad Yp Zc Xp Bd Zd Xc Ap Yd',
     (10,5,8,2,7,13,4,1,12,6,9,3,11),(9,14,7,3,11,5,2,16,6,12,4,10,15,1,13,8)),
    ('W',2,2,('V:W2','O','X:W4','V:D2','O'),'22112','D4 W2 N4 W4 D4','mNmnn',
     'Ac Zp Yc Bd Xp Ap Zc Bc Xd Yd Ad Xc Yp Zd Bp',
     (2,12,6,9,4,7,11,1,5,13,10,8,3),(4,1,10,6,15,12,8,2,14,5,11,9,3,16,7,13)),
    ('W',4,2,('V:W2','X:D4','O','V:D4','O'),'21212','D4 W4 N2 W2 D4','nmmNn',
     'Ap Xd Bc Zp Yc Ac Xp Zd Bd Yd Ad Zc Bp Xc Yp',
     (5,3,10,7,9,1,12,2,11,6,8,13,4),(7,15,9,4,14,1,5,12,3,8,10,16,2,13,11,6)),
    ('N',4,4,('V:D4','O','X:D4','V:N2','O'),'12121','N2 W2 D4 W4 N4','mNmnn',
     'Xp Zc Yd Bc Ac Xc Bd Yp Ad Zp Xd Yc Bp Zd Ap',
     (12,6,4,8,2,11,7,5,9,1,10,13,3),(2,10,13,8,6,11,3,15,9,1,12,7,16,5,14,4)),
)


def capabilities(code):
    return {'allowed_media':[] if code == 'U' else ['W','N'] if code[0] == 'D' else [code[0]],
            'limit':4 if code == 'U' else int(code[1])}


def entity_text(entity):
    return f'节点{entity["node"]}、组件{entity["component"]}、配置{entity["configuration"]}'


def describe(node,fields):
    parts = []
    if 'allowed_media' in fields:
        media = '、'.join({'W':'水W','N':'氮气N'}[medium] for medium in fields['allowed_media'])
        parts.append('当前获准介质为'+media if media else '当前获准介质为空，W/N均未获准')
    if 'limit' in fields:
        parts.append(f'最大流量={fields["limit"]}标准单位/分钟' if node in 'AB' else f'压力上限={fields["limit"]}题内压力单位')
    return '；'.join(parts)


def build(index):
    medium,flow,pressure,chains,codes,spare_codes,partial,receipt_order,menu,ids = CONFIGS[index]
    installed,spares,old,jobs = {},{},{},{}
    for node,chain,code,spare_code,scope in zip(NODES,chains,codes,spare_codes.split(),partial,strict=True):
        serial = SERIALS[node][int(code)-1]
        spare_serial = SERIALS[node][2-int(code)]
        configuration = 'K2' if chain[0] == 'V' else 'K1'
        installed[node] = {'node':node,'component':serial,'configuration':configuration}
        spares[node] = {'node':node,'component':spare_serial,'configuration':'K1' if configuration == 'K2' else 'K2'}
        old[node] = spares[node] if chain[0] == 'V' else installed[node]
        current_fields = capabilities(INITIAL[node] if chain == 'O' else 'U' if chain[0] in 'UX' else chain.split(':')[1])
        spare_fields = capabilities(spare_code)
        jobs[node+'c'] = {**installed[node],'fields':current_fields}
        jobs[node+'d'] = {**spares[node],'fields':spare_fields}
        entity,values = (installed[node],current_fields) if scope.islower() else (spares[node],spare_fields)
        field = 'allowed_media' if scope.lower() == 'm' else 'limit'
        jobs[node+'p'] = {**entity,'fields':{field:deepcopy(values[field])}}
    identifiers = [f'E{n:02d}' for n in ids]
    history = History()
    history.add(1,'补给工位有泵A/B和适配器X/Y/Z，任一泵可串联任一适配器；阀路已连接，选择自动隔离其他支路，对接锁合、供电和接收容量保障。'
        'W=水、N=氮气，各用本介质标准供给量单位，不代表相同实际体积或密度。本次固定8单位；档2/4分别每分钟2/4单位，自动运行4/2分钟后关闭，不另考截止时间。'
        '泵须当前获准本次介质、最大流量≥选档≥最低需求q。两泵供压上界已验证为6题内单位，预置调压器把实际经过适配器及接收口的压力设为当前p，并非固定输出6。'
        '适配器须当前获准本介质且压力上限≥p；等号可用，合格高档同样接受，不因省能只认低档。两类数值单位不同，不互相比较。'
        '验收须对应实际安装的节点、组件序号和K配置；备件在隔离台检验供下一任务选装，不能授权在用件，当前无换件入口。'
        '工单和计划不是实际安装或通过；维修/复位完成不自动恢复介质授权。故障撤销全部介质授权但不改变数值上限，分项只更新所写字段。'
        '未改变字段的旧证持续有效，同值复核可等价引用；字段改变后再变回，旧证不复活。换组件或配置不能跨用字段。'
        '选择真实泵、档、适配器一次完成8单位补给，或H不启输。完整合法组合必须同时满足两个节点，任一合格组合均接受。'
        '启输每节点需依据支持该实体当前介质及数值两字段，完整证或有效分项并集均可。'
        '无合法组合才保持：须证明全部泵不能满足，或全部适配器不能满足；每节点任一明确失败字段即充分，不能用部分泵与部分适配器拼出全部组合均失败的结论。'
        'select恰含action、option、evidence，option为菜单数字字符串，evidence为E01—E16数组，可空、重复先去重后最多3不同ID。仅单字段action=end结束。'
        '总调用最多3次，格式错只指出字段/目录/数量并耗次；目录内错误或不足依据仍是合法业务提交，首次合法选择立即执行并终局。'
        '反馈固定“补给操作与依据已存档。”，无免费测流、证书查询或试输入口，原生记忆检索不计动作。错输不能撤销重选、无合格补给，不另假定灾难。'
        '自动输送2或4分钟期间配置、已验能力和预置供压保持，无其他作业换件或新授权。',event='supply_capability_protocol')
    claims = [{**old[node],'fields':capabilities(INITIAL[node])} for node in NODES]
    history.add(2,identifiers[0]+'：五节点初始实际安装与完整验收：'+'；'.join(entity_text(c)+'，'+describe(c['node'],c['fields']) for c in claims)+'。',
        record_id=identifiers[0],event='initial_supply_certificates',claims=claims)
    for node,chain in zip(NODES,chains,strict=True):
        entity = old[node]
        if chain == 'O':
            history.add(3,entity_text(entity)+'外壳已清洁，无能力变化。',event='supply_shell_cleaned',**entity)
        elif chain[0] == 'V':
            history.add(3,entity_text(entity)+'已实际卸下。',event='supply_component_removed',**entity)
        elif chain[0] == 'X':
            fields = capabilities(chain.split(':')[1])
            history.add(3,entity_text(entity)+'已完成完整验收，'+describe(node,fields)+'。',event='supply_earlier_certificate',fields=fields,**entity)
        else:
            history.add(3,entity_text(entity)+'供给功能实际故障，全部介质授权已撤销，数值上限保持。',event='supply_media_fault',**entity)
    for node,chain in zip(NODES,chains,strict=True):
        if chain[0] == 'X':
            history.add(4,entity_text(old[node])+'再次实际故障，全部介质授权撤销，数值上限保持。',event='supply_media_fault',**old[node])
    for node,chain in zip(NODES,chains,strict=True):
        status = {'O':'仍在用，能力无变化','R':'实际修复完成，尚待介质功能验收','V':'已实际安装，尚待验收',
                  'U':'复位完成，尚无介质恢复验证','X':'复位完成，尚无介质恢复验证'}[chain[0]]
        history.add(6,entity_text(installed[node])+f'，{status}；'+entity_text(spares[node])+'为隔离台备件，下一任务选装，本轮未安装。',
            event='supply_installation_handover',installed=installed[node],spare=spares[node])
    order = receipt_order.split()
    job_ids = {role:f'J{n:02d}' for n,role in enumerate(order,1)}
    bindings = {job_ids[role]:{**{key:jobs[role][key] for key in ('node','component','configuration')},'scope':list(jobs[role]['fields'])} for role in order}
    history.add(8,'本班十五项检验对象和范围：'+'；'.join(f'{identifier}：{entity_text(binding)}，检验范围'+
        '/'.join('介质授权' if field == 'allowed_media' else '最大流量' if binding['node'] in 'AB' else '压力上限' for field in binding['scope'])
        for identifier,binding in bindings.items())+'。分项不推断未检字段，离线检验不安装组件。',event='supply_jobs_registered',jobs=bindings)
    for slot,role in enumerate(order,1):
        job = jobs[role]
        entity = {key:job[key] for key in ('node','component','configuration')}
        scope = list(job['fields'])
        history.add(slot+8,identifiers[slot]+f'：工单{job_ids[role]}，{entity_text(entity)}，实际检验范围'+
            '/'.join('介质授权' if field == 'allowed_media' else '最大流量' if entity['node'] in 'AB' else '压力上限' for field in scope)+
            '，'+describe(entity['node'],job['fields'])+'。',record_id=identifiers[slot],event='supply_job_receipt',
            job_id=job_ids[role],scope=scope,fields=job['fields'],**entity)
    history.add(24,'下一班选装备用组件的计划尚未执行，本轮不换件。',event='supply_installation_planned')
    history.add(25,'当前接收舱已就绪，对接锁合保障。',event='supply_receiver_ready')
    history.add(26,'另一接收舱的旧补给已经结束，不是本次8单位交付。',event='other_supply_completed')
    history.add(27,'把组件上限提升到6的设想尚未施工，没有新增能力验收。',event='supply_upgrade_proposed')
    history.add(28,'W/N各自供料均剩50标准单位，当前所选接收容器还可接收50单位，本次固定8单位足够。',
        event='supply_quantity_available',source_units={'W':50,'N':50},receiver_capacity_units=50)
    history.add(29,'电源、阀路及预置调压正常；实际输送压力将保持当前p，没有新增节点能力验收。',event='supply_regulator_ready')
    history.add(30,'本次补给任务交接完成，等待启输或保持。',event='supply_handover_complete')
    base = [{'description':f'{pump}{rate}{adapter}：泵{pump}以档{rate}标准单位/分钟经适配器{adapter}自动输送8单位后关闭',
             'operation':{'pump':pump,'rate':rate,'adapter':adapter}} for pump in 'AB' for rate in (2,4) for adapter in 'XYZ']
    base.append({'description':'H：保持，不启输','operation':{'hold':True}})
    task = task_shell('FM-S2-O3',index)
    task.public = {'instruction':f'本轮补给介质{medium}，固定交付8标准单位，最低流量q={flow}标准单位/分钟，实际调压p={pressure}题内压力单位。请选择完整补给操作并附依据。',
        'medium':medium,'minimum_flow':flow,'pressure':pressure,'quantity_units':8,'time_s':clock('09:00'),
        'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],'actions':fixed_options(base[n-1] for n in menu)}
    task.initial = {'time_s':clock('09:00'),'transfers':[],'qualified_delivery_units':0,'valve_open':False}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'correct supply: 50 per complete current node proof; correct hold: maximum proved fraction of an entirely failed side; wrong action 0'}
    return history.finish(task)


ENTITY = r'节点[ABXYZ]、组件[A-Z]\d+、配置K\d+'


def _entity(text):
    match = re.fullmatch(r'节点([ABXYZ])、组件([A-Z]\d+)、配置(K\d+)',text)
    if match is None:
        raise ValueError('A supply entity must print its node, serial and configuration')
    return dict(zip(('node','component','configuration'),match.groups(),strict=True))


def _fields(node,text):
    fields = {}
    for part in text.split('；'):
        if part == '当前获准介质为空，W/N均未获准':
            field,value = 'allowed_media',[]
        elif media := re.fullmatch(r'当前获准介质为(.+)',part):
            names = {'水W':'W','氮气N':'N'}
            field,value = 'allowed_media',sorted({names[name] for name in media[1].split('、')},key='WN'.index)
        else:
            pattern = r'最大流量=(\d+)标准单位/分钟' if node in 'AB' else r'压力上限=(\d+)题内压力单位'
            limit = re.fullmatch(pattern,part)
            if limit is None:
                raise ValueError('Supply fields must use the actual node quantity and units')
            field,value = 'limit',int(limit[1])
        if field in fields:
            raise ValueError('A supply receipt cannot state the same field twice')
        fields[field] = value
    return fields


def _scope(node,text):
    labels = {'介质授权':'allowed_media',('最大流量' if node in 'AB' else '压力上限'):'limit'}
    scope = [labels[label] for label in text.split('/')]
    if len(set(scope)) != len(scope):
        raise ValueError('A supply inspection scope must name each field once')
    return scope


def _supply_record(text):
    if match := re.fullmatch(r'五节点初始实际安装与完整验收：(.+)。',text):
        claims = []
        for part in re.split(r'；(?=节点)',match[1]):
            item = re.fullmatch(rf'({ENTITY})，(.+)',part)
            if item is None:
                raise ValueError('Each initial supply certificate must identify one installed entity')
            entity = _entity(item[1])
            fields = _fields(entity['node'],item[2])
            if set(fields) != {'allowed_media','limit'}:
                raise ValueError('Each initial supply certificate must contain both capability fields')
            claims.append({**entity,'fields':fields})
        if len(claims) != 5 or {claim['node'] for claim in claims} != set(NODES):
            raise ValueError('The initial supply table must cover all five different nodes')
        return {'event':'initial_supply_certificates','claims':claims}
    if match := re.fullmatch(rf'({ENTITY})已实际卸下。',text):
        return {'event':'supply_component_removed',**_entity(match[1])}
    if match := re.fullmatch(rf'({ENTITY})(?:供给功能实际故障，全部介质授权已撤销|再次实际故障，全部介质授权撤销)，数值上限保持。',text):
        return {'event':'supply_media_fault',**_entity(match[1])}
    if match := re.fullmatch(rf'({ENTITY})已完成完整验收，(.+)。',text):
        entity = _entity(match[1])
        return {'event':'supply_earlier_certificate',**entity,'fields':_fields(entity['node'],match[2])}
    if match := re.fullmatch(rf'({ENTITY})，(?:仍在用，能力无变化|实际修复完成，尚待介质功能验收|已实际安装，尚待验收|复位完成，尚无介质恢复验证)；'
                            rf'({ENTITY})为隔离台备件，下一任务选装，本轮未安装。',text):
        return {'event':'supply_installation_handover','installed':_entity(match[1]),'spare':_entity(match[2])}
    if match := re.fullmatch(r'本班十五项检验对象和范围：(.+)。分项不推断未检字段，离线检验不安装组件。',text):
        jobs = {}
        for part in match[1].split('；'):
            item = re.fullmatch(rf'(J\d+)：({ENTITY})，检验范围(.+)',part)
            if item is None or item[1] in jobs:
                raise ValueError('Every supply job must bind its own ID to one entity and field scope')
            entity = _entity(item[2])
            jobs[item[1]] = {**entity,'scope':_scope(entity['node'],item[3])}
        return {'event':'supply_jobs_registered','jobs':jobs}
    if match := re.fullmatch(rf'工单(J\d+)，({ENTITY})，实际检验范围([^，]+)，(.+)。',text):
        entity = _entity(match[2])
        return {'event':'supply_job_receipt','job_id':match[1],**entity,
                'scope':_scope(entity['node'],match[3]),'fields':_fields(entity['node'],match[4])}
    return {}


def reconstruct(history,current):
    installed,components,evidence,jobs = {},{},{},{}

    def component(entity):
        serial = entity['component']
        state = components.setdefault(serial,{'node':entity['node'],'configuration':entity['configuration'],
            'fields':{field:{'value':None,'revision':0} for field in ('allowed_media','limit')}})
        if any(state[key] != entity[key] for key in ('node','configuration')):
            raise ValueError('Component identity and configuration cannot change during offline acceptance')
        return state

    def certificate(entity,fields):
        state = component(entity)['fields']
        proof = {key:entity[key] for key in ('node','component','configuration')}
        proof['fields'] = {}
        for field,value in fields.items():
            if state[field]['value'] != value:
                state[field] = {'value':deepcopy(value),'revision':state[field]['revision']+1}
            proof['fields'][field] = deepcopy(state[field])
        return proof

    for text in paragraphs(history):
        numbered = re.fullmatch(r'(E\d{2})：(.+)',text)
        record = _supply_record(numbered[2] if numbered else text)
        event,proofs = record.get('event'),[]
        if event == 'initial_supply_certificates':
            for claim in record['claims']:
                installed[claim['node']] = {key:claim[key] for key in ('node','component','configuration')}
                proofs.append(certificate(claim,claim['fields']))
        elif event == 'supply_component_removed':
            if any(installed[record['node']][key] != record[key] for key in ('component','configuration')):
                raise ValueError('Only the installed component can be removed')
            del installed[record['node']]
        elif event == 'supply_media_fault':
            if any(installed[record['node']][key] != record[key] for key in ('component','configuration')):
                raise ValueError('A supply fault must refer to the installed component')
            certificate(record,{'allowed_media':[]})
        elif event == 'supply_earlier_certificate':
            certificate(record,record['fields'])
        elif event == 'supply_installation_handover':
            entity = record['installed']
            component(entity)
            component(record['spare'])
            installed[entity['node']] = deepcopy(entity)
        elif event == 'supply_jobs_registered':
            jobs = record['jobs']
        elif event == 'supply_job_receipt':
            entity = jobs[record['job_id']]
            if set(record['fields']) != set(entity['scope']) or any(record[key] != entity[key] for key in ('node','component','configuration','scope')):
                raise ValueError('An actual receipt must cover exactly its registered entity and fields')
            proofs = [certificate(entity,record['fields'])]
        if numbered and numbered[1] in CATALOG:
            evidence[numbered[1]] = proofs
    return {'installed':installed,'components':components,'evidence':evidence,
            'medium':current['medium'],'minimum_flow':current['minimum_flow'],'pressure':current['pressure']}


def current_fields(facts,node):
    return facts['components'][facts['installed'][node]['component']]['fields']


def node_usable(facts,node,minimum=None):
    fields = current_fields(facts,node)
    demand = minimum if minimum is not None else facts['minimum_flow'] if node in 'AB' else facts['pressure']
    return facts['medium'] in fields['allowed_media']['value'] and fields['limit']['value'] >= demand


def supported_fields(facts,node,references):
    entity,fields = facts['installed'][node],current_fields(facts,node)
    return {key for identifier in references for proof in facts['evidence'].get(identifier,[])
            if all(proof[key] == entity[key] for key in ('node','component','configuration'))
            for key,claim in proof['fields'].items() if claim == fields[key]}


def node_proved_unusable(facts,node,references):
    fields,supported = current_fields(facts,node),supported_fields(facts,node,references)
    demand = facts['minimum_flow'] if node in 'AB' else facts['pressure']
    return ('allowed_media' in supported and facts['medium'] not in fields['allowed_media']['value'] or
            'limit' in supported and fields['limit']['value'] < demand)


def evaluate(facts,operation,references):
    if operation.get('hold'):
        failed_sides = [side for side in ('AB','XYZ') if all(not node_usable(facts,node) for node in side)]
        if not failed_sides:
            return 0,False,{}
        supported = {side:[node for node in side if node_proved_unusable(facts,node,references)] for side in failed_sides}
        return max(100*len(nodes)/len(side) for side,nodes in supported.items()),True,supported
    pump,rate,adapter = operation['pump'],operation['rate'],operation['adapter']
    correct = rate >= facts['minimum_flow'] and node_usable(facts,pump,rate) and node_usable(facts,adapter)
    supported = [node for node in (pump,adapter) if supported_fields(facts,node,references) == {'allowed_media','limit'}]
    return (50*len(supported) if correct else 0),correct,supported


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},
        'description':'E01—E16编号字符串数组，可空；重复先去重，再检查最多3个不同ID。'}}})

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
        if option is None or not isinstance(references,list) or not all(isinstance(identifier,str) and identifier in CATALOG for identifier in references) or len(set(references)) > 3:
            self.invalid()
            return
        references = list(dict.fromkeys(references))
        operation = deepcopy(option['operation'])
        score,correct,supported = evaluate(self.task.world,operation,references)
        if not operation.get('hold'):
            duration = 8*60//operation['rate']
            started = self.state['time_s']
            self.state['time_s'] += duration
            self.state['transfers'].append({**operation,'medium':self.task.public['medium'],'pressure':self.task.public['pressure'],
                'requested_quantity_units':8,'qualified_units':8 if correct else 0,
                'started_s':started,'finished_s':self.state['time_s'],'qualified':correct,
                'pump_component':deepcopy(self.task.world['installed'][operation['pump']]),
                'adapter_component':deepcopy(self.task.world['installed'][operation['adapter']])})
            self.state['qualified_delivery_units'] = 8 if correct else 0
        self.facts = {'executed_operation':operation,'operation_correct':correct,'supported':supported,'references':references}
        self.feedback = '补给操作与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2,3):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('Every full supply decision must have at most three sufficient current records')


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Current supply capabilities must follow installed components and actual field updates')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(4):
            for references in combinations(CATALOG,count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
