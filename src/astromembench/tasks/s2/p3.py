"""FM-S2-P3: capacity-one vehicles, current certificates and all legal matchings."""
from copy import deepcopy
from itertools import combinations, product
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'E{i:02d}' for i in range(1,16))
ENVELOPES = {'A':('PB',10,3),'B':('P',8,2),'C':('B',6,3),'D':('PB',6,2),'E':('PB',10,1),
             'F':('',10,3),'G':('P',12,3),'I':('B',10,2),'J':('PB',4,3)}
CONFIGS = (
    ((('P',8,2),('B',6,2)),('R:B','D:C','U'),2,(6,12,3,15,8,1,10,4,14,7,2,11,5,13,9)),
    ((('P',8,2),('B',6,2)),('O','U','D:D'),5,(2,9,5,12,15,6,1,11,7,14,4,13,8,10,3)),
    ((('P',6,2),('B',6,2)),('U','O','O'),8,(9,2,13,6,1,11,4,14,8,3,10,15,7,12,5)),
    ((('P',8,2),('B',8,2)),('R:B','R:D','U'),6,(15,8,12,1,7,14,3,10,5,13,6,9,11,4,2)),
    ((('P',10,2),('B',10,2)),('O','U','U'),9,(7,1,15,9,6,4,11,13,2,5,14,10,8,12,3)),
    ((('P',8,3),('B',8,3)),('R:E','O','O'),1,(10,13,4,8,12,2,7,6,15,11,1,3,9,14,5)),
    ((('P',8,2),('B',6,2)),('V:B','V:C','X:A'),10,(8,5,11,2,14,10,6,12,3,9,15,1,7,4,13)),
    ((('P',8,2),('B',6,3)),('V:A','R:C','O'),7,(6,10,1,14,7,3,11,15,4,8,2,12,5,9,13)),
    ((('P',8,1),('B',8,1)),('V:E','R:B','O'),11,(4,12,15,9,3,6,10,5,13,1,8,11,14,7,2)),
    ((('P',6,2),('B',10,2)),('O','O','V:I'),5,(14,9,3,6,12,8,2,13,7,11,1,5,10,15,4)),
    ((('P',10,3),('B',10,3)),('V:A','U','O'),8,(5,1,10,7,13,2,14,4,9,15,6,3,11,8,12)),
    ((('P',6,3),('B',6,3)),('X:A','V:D','O'),3,(12,8,4,15,6,11,9,2,5,14,3,10,7,13,1)),
    ((('P',8,2),('B',8,2)),('X:A','V:E','O'),6,(15,4,7,13,10,9,8,6,1,12,5,2,11,3,14)),
    ((('P',8,1),('B',8,1)),('V:E','V:B','X:I'),1,(10,3,12,4,9,13,6,14,5,7,15,1,8,11,2)),
    ((('P',6,2),('B',6,2)),('U','X:D','V:E'),13,(4,10,1,15,8,12,3,7,11,5,9,13,6,2,14)),
    ((('P',4,2),('B',4,2)),('V:J','O','R:I'),7,(11,7,14,3,6,9,2,12,4,1,13,8,15,5,10)),
)


def envelope(code):
    categories,capacity,height = ENVELOPES[code]
    return {'categories':list(categories),'capacity_kg':capacity,'height_m':height}


def describe(certificate):
    categories = '、'.join({'P':'托盘P','B':'封闭箱B'}[c] for c in certificate['categories']) or '无'
    return f'获准类别={categories}，承载C={certificate["capacity_kg"]} kg，举升H={certificate["height_m"]} m'


def build(index):
    cargo,chains,shift,ids = CONFIGS[index]
    identifiers = [f'E{n:02d}' for n in ids]
    history = History()
    history.add(1,'X/Y/Z运载单元各一个货位，两件货物本轮同时分派，一台不能接两件，不能拆货、拼载或分两次。'
        '货物P为托盘、B为封闭箱，需当前获准该类别且质量≤承载C kg、提送高度≤H m，等号允许。'
        '场地、道路、供电与标签已知正常，夹持及路线为固定完整操作，不另选路径。'
        '完整能力证书绑定当前夹具安装K1/K2；故障撤销功能许可，恢复完成和通信正常不能替代验收，明确未验收就是仍未获准。'
        '换夹具后旧证不移用；无变更的旧证与同值完整复核均有效，不因证号或时间更早失效；实际失效后的旧证不会因相同值复现复活。'
        '菜单顺序对应第一货/第二货，-为不分派；重复同车是可提交的真实冲突指令，接受后货位冲突并结束任务。'
        '分配中的每项转运均须合格，并提供充分的当前完整证书；在此条件下尽量多运货物，不限定唯一最大分配。'
        '若两货均没有任何合格载具，只能都不分派，并分别引用能证明X/Y/Z都不能服务两货的当前完整状态。'
        '未选货物不会自动运走，错误分配不能撤销；不提供现场能力查询或试载。select恰含action/option/evidence，option为菜单数字字符串。'
        'evidence为E01—E15字符串数组，可空，先去重再检查最多3不同编号；主动结束只含action=end。'
        '总调用3次，格式错误只提示字段并耗次，首次合法选择立即终局，固定反馈“转运分配与依据已存档。”，不提示能力、正确性或得分。原生记忆检索不计动作。',event='cargo_capability_protocol')

    def emit(at,slot,text,*,vehicle=None,job_id=None,bind=False,only_job=False,event='cargo_capability_record',**facts):
        if vehicle is not None and not only_job:
            facts['vehicle'] = vehicle
        if job_id:
            facts['job_id'] = job_id
            if bind:
                facts['job_vehicle'] = vehicle
        history.add(at,identifiers[slot-1]+'：'+text,record_id=identifiers[slot-1],event=event,**facts)

    for at,vehicle,code in zip((2,3,4),'XYZ','ADI',strict=True):
        certificate = envelope(code)
        emit(at,at-1,f'{vehicle}初始当前夹具K1完整证书：'+describe(certificate)+'，实际验收通过。',
            vehicle=vehicle,event='cargo_initial_certificate',configuration='K1',certificate=certificate)
    for phase,times in enumerate(((6,8,10),(13,16,19),(22,24,26))):
        for position,(at,vehicle,chain) in enumerate(zip(times,'XYZ',chains,strict=True)):
            kind = chain[0]
            config = 'K2' if kind == 'V' else 'K1'
            code = chain[-1] if ':' in chain else None
            facts = {}
            if kind == 'O':
                text = ('其他图像功能正常，运输证书未变。','下班换夹具方案未执行，运输证书未变。','通信正常，运输证书未变。')[phase]
            elif kind == 'D':
                if phase == 0:
                    text = '当前夹具K1的全部运输功能实际故障，使用限制生效。'
                    facts = {'revoke':True}
                elif phase == 1:
                    text = '维修已完成，运输功能仍未验证，限制未解除。'
                else:
                    text = '夹具K1已实际验证通过，签发完整证书：'+describe(envelope(code))+'。'
                    facts = {'certificate':envelope(code)}
            elif kind == 'R':
                if phase == 1:
                    text = '恢复更高运输能力的申请尚未执行，现有证书未变。'
                else:
                    text = ('夹具K1调整或复核后实际完整验收：' if phase == 0 else '夹具K1当前能力再次完整确认：')+describe(envelope(code))+'。'
                    facts = {'certificate':envelope(code)}
            elif kind == 'V':
                if phase == 0:
                    text = '已实际更换夹具为K2，尚未验收，全部运输功能受限，旧K1证书不移用。'
                    facts = {'replace':True}
                elif phase == 1:
                    text = '夹具K2实际验收并签发完整证书：'+describe(envelope(code))+'。'
                    facts = {'certificate':envelope(code)}
                else:
                    text = '通信正常，没有新的运输验证。'
            elif kind == 'U':
                text = ('全部运输功能实际故障并限制。','修复已完成但仍未验收。','当前运输限制明确仍在。')[phase]
                text += '夹具K1完整状态：'+describe(envelope('F'))+'。'
                facts = {'certificate':envelope('F')}
            else:
                code = code if phase == 0 else 'F'
                text = ('夹具K1曾实际完整验收通过。','随后再次实际故障，全部运输功能限制。','重启完成，运输仍未验收、限制未解除。')[phase]
                text += '夹具K1完整状态：'+describe(envelope(code))+'。'
                facts = {'certificate':envelope(code)}
            job_id = 'J'+vehicle if index >= 12 else None
            only_job = index >= 12 and phase == 2
            prefix = f'作业{job_id}：' if only_job else vehicle+(f'（作业{job_id}）' if job_id else '')+'：'
            emit(at,4+3*phase+position,prefix+text,vehicle=vehicle,job_id=job_id,bind=phase < 2,only_job=only_job,configuration=config,**facts)
    emit(27,13,'另一工位W已完成运输，与本轮两货无关。')
    emit(28,14,'新一轮全部货位扩为两位的方案尚未执行。')
    emit(29,15,'驱动自检正常，不改变夹具或承载许可。')
    history.add(30,'两件货物摆入各自独立等待位，尚未完成转运。',event='cargo_waiting')
    assignments = list(product('XYZ-',repeat=2))
    assignments = assignments[shift:]+assignments[:shift]
    task = task_shell('FM-S2-P3',index)
    task.public = {'instruction':'请为两件货物提交本轮联合转运分配，并附已有依据。',
        'cargo':[{'cargo_type':kind,'mass_kg':mass,'height_m':height} for kind,mass,height in cargo],
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':fixed_options({'description':f'{first}{second}：货1'+('不分派' if first == '-' else f'分派{first}')+'，货2'+('不分派' if second == '-' else f'分派{second}'),
            'operation':{'assignment':[first,second]}} for first,second in assignments)}
    task.initial = {'assigned':[None,None],'cargo_waiting':[True,True],'allocation_conflict':False}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'any invalid edge or vehicle collision: 0; otherwise 100*completed evidenced cargo/maximum matching; if maximum zero: 100*proved unusable vehicles/3 for --'}
    return history.finish(task)


def _certificate(text):
    match = re.fullmatch(r'获准类别=(.+)，承载C=(\d+) kg，举升H=(\d+) m',text)
    if match is None:
        raise ValueError('A complete transport certificate must print its categories, capacity and height')
    names,capacity,height = match.groups()
    labels = {'托盘P':'P','封闭箱B':'B'}
    categories = [] if names == '无' else [labels[name] for name in names.split('、')]
    return {'categories':sorted(set(categories),key='PB'.index),
            'capacity_kg':int(capacity),'height_m':int(height)}


def _transport_update(text):
    if match := re.fullmatch(r'当前夹具(K\d+)的全部运输功能实际故障，使用限制生效。',text):
        return {'configuration':match[1],'revoke':True}
    if match := re.fullmatch(r'已实际更换夹具为(K\d+)，尚未验收，全部运输功能受限，旧(K\d+)证书不移用。',text):
        return {'configuration':match[1],'previous_configuration':match[2],'replace':True}
    if match := re.fullmatch(r'夹具(K\d+)(?:调整或复核后实际完整验收|当前能力再次完整确认|'
                            r'已实际验证通过，签发完整证书|实际验收并签发完整证书)：(.+)。',text):
        return {'configuration':match[1],'certificate':_certificate(match[2])}
    if match := re.fullmatch(r'(全部运输功能实际故障并限制。|修复已完成但仍未验收。|当前运输限制明确仍在。|'
                            r'夹具K\d+曾实际完整验收通过。|随后再次实际故障，全部运输功能限制。|'
                            r'重启完成，运输仍未验收、限制未解除。)夹具(K\d+)完整状态：(.+)。',text):
        prefix,configuration,description = match.groups()
        certificate = _certificate(description)
        if installed := re.fullmatch(r'夹具(K\d+)曾实际完整验收通过。',prefix):
            if installed[1] != configuration:
                raise ValueError('A complete transport receipt must name one fixture installation')
        elif certificate['categories']:
            raise ValueError('An explicitly unapproved vehicle cannot claim authorized cargo categories')
        return {'configuration':configuration,'certificate':certificate}
    return {}


def reconstruct(history,current):
    states,evidence,jobs = {},{},{}
    for paragraph in paragraphs(history):
        numbered = re.fullmatch(r'(E\d{2})：(.+)',paragraph)
        if numbered is None:
            continue
        identifier,text = numbered.groups()
        evidence[identifier] = {}
        if match := re.fullmatch(r'([XYZ])初始当前夹具(K\d+)完整证书：(.+)，实际验收通过。',text):
            vehicle,configuration,description = match.groups()
            states[vehicle] = {'configuration':configuration,
                'fields':{field:{'value':value,'revision':1} for field,value in _certificate(description).items()}}
            evidence[identifier] = {vehicle:deepcopy(states[vehicle])}
            continue
        if match := re.fullmatch(r'([XYZ])（作业(J[XYZ])）：(.+)',text):
            vehicle,job_id,text = match.groups()
            if jobs.setdefault(job_id,vehicle) != vehicle:
                raise ValueError('A vehicle job cannot be rebound')
        elif match := re.fullmatch(r'作业(J[XYZ])：(.+)',text):
            job_id,text = match.groups()
            if job_id not in jobs:
                raise ValueError('A job-only receipt requires its printed vehicle assignment')
            vehicle = jobs[job_id]
        elif match := re.fullmatch(r'([XYZ])：(.+)',text):
            vehicle,text = match.groups()
        else:
            continue
        state = states[vehicle]
        update = _transport_update(text)
        if update.get('replace'):
            if state['configuration'] != update['previous_configuration']:
                raise ValueError('A fixture replacement must identify the previous installation')
            state['configuration'] = update['configuration']
            state['fields'] = {field:{'value':[] if field == 'categories' else None,'revision':old['revision']+1} for field,old in state['fields'].items()}
        if 'configuration' in update and state['configuration'] != update['configuration']:
            raise ValueError('Certificate must bind the current fixture installation')
        if update.get('revoke'):
            field = state['fields']['categories']
            field.update(value=[],revision=field['revision']+1)
        if 'certificate' in update:
            for field,value in update['certificate'].items():
                old = state['fields'][field]
                if old['value'] != value:
                    state['fields'][field] = {'value':deepcopy(value),'revision':old['revision']+1}
            evidence[identifier] = {vehicle:deepcopy(state)}
    return {'states':states,'evidence':evidence,'cargo':deepcopy(current['cargo'])}


def edges(facts):
    result = []
    for cargo in facts['cargo']:
        result.append([vehicle for vehicle,state in facts['states'].items()
            if cargo['cargo_type'] in state['fields']['categories']['value']
            and cargo['mass_kg'] <= state['fields']['capacity_kg']['value']
            and cargo['height_m'] <= state['fields']['height_m']['value']])
    return result


def legal(assignment,connections):
    selected = [vehicle for vehicle in assignment if vehicle != '-']
    return len(selected) == len(set(selected)) and all(vehicle == '-' or vehicle in connections[position] for position,vehicle in enumerate(assignment))


def maximum(connections):
    return max(sum(vehicle != '-' for vehicle in pair) for pair in product('XYZ-',repeat=2) if legal(pair,connections))


def proved_vehicles(facts,references):
    return {vehicle for identifier in references for vehicle,proof in facts['evidence'][identifier].items()
            if proof == facts['states'][vehicle]}


def evaluate(facts,assignment,references):
    connections = edges(facts)
    best = maximum(connections)
    valid = legal(assignment,connections)
    proved = proved_vehicles(facts,references)
    supported = len(proved) if best == 0 else sum(vehicle in proved for vehicle in assignment if vehicle != '-')
    return (100*supported/(best or 3) if valid else 0),valid,proved


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},'description':'E01—E15编号数组；可空，重复先去重再检查最多3个不同ID。'}}})

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
        if option is None or not isinstance(references,list) or not all(isinstance(n,str) and n in CATALOG for n in references) or len(set(references)) > 3:
            self.invalid()
            return
        references = list(dict.fromkeys(references))
        assignment = option['operation']['assignment']
        score,valid,proved = evaluate(self.task.world,assignment,references)
        self.state['assigned'] = [None if vehicle == '-' else vehicle for vehicle in assignment]
        selected = [v for v in assignment if v != '-']
        self.state['allocation_conflict'] = len(selected) != len(set(selected))
        # Only valid independent edges complete a transfer; every assignment is recorded.
        connections = edges(self.task.world)
        self.state['cargo_waiting'] = [vehicle == '-' or vehicle not in connections[position] or self.state['allocation_conflict']
                                      for position,vehicle in enumerate(assignment)]
        self.facts = {'executed_operation':deepcopy(option['operation']),'legal_assignment':valid,'proved_vehicles':sorted(proved),'references':references}
        self.feedback = '转运分配与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in range(1,4):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation']['assignment'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('The optimal joint allocation must have sufficient evidence within three references')


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Joint allocation must follow current fixture and complete capability certificates')


def audit_cases(task,facts,solution):
    references = solution[0]['evidence']
    cases = [([{'action':'select','option':row['option'],'evidence':references}],evaluate(facts,row['operation']['assignment'],references)[0]) for row in task.public['actions']]
    command = solution[0]
    operation = next(row['operation'] for row in task.public['actions'] if row['option'] == command['option'])
    for count in range(4):
        for references in combinations(CATALOG,count):
            cases.append(([{**command,'evidence':list(references)}],evaluate(facts,operation['assignment'],references)[0]))
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
