"""FM-S2-O2: installed tool permissions and complete torque-speed envelopes."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'H{i:02d}' for i in range(1,13))
PROGRAMS = {'L':(8,2),'F':(4,6),'M':(6,4),'S':(2,8)}
ENVELOPES = {'A':(8,32),'B':(8,20),'C':(4,24),'D':(6,24),'E':(8,16),'F':(8,12),'G':(6,20),'I':(4,16)}
# Work requirements, first processes, second scopes (current or spare envelope),
# menu rotation, and independently assigned record IDs.
CONFIGS = (
    (4,6,('R:B','R:C'),('current','E'),7,(5,12,2,9,7,4,11,1,8,3,10,6)),
    (2,8,('U:A','R:I'),('D','current'),9,(2,9,7,12,4,1,10,5,6,11,8,3)),
    (4,4,('R:B','R:D'),('current','B'),5,(11,4,8,3,6,12,5,9,2,7,1,10)),
    (8,2,('R:D','R:C'),('A','current'),4,(12,5,9,2,11,6,1,8,7,4,3,10)),
    (4,6,('U:A','R:B'),('current','C'),8,(7,11,1,5,9,2,8,3,10,12,6,4)),
    (6,2,('R:D','R:B'),('C','G'),3,(1,10,6,4,8,5,9,2,3,12,11,7)),
    (8,2,('V:E','N:A'),('A','current'),8,(5,9,12,6,2,10,7,1,4,8,3,11)),
    (2,8,('X:A','R:I'),('current','A'),0,(10,4,1,9,6,12,5,3,8,7,11,2)),
    (4,4,('V:D','V:C'),('current','F'),10,(2,6,9,5,12,7,11,8,3,1,10,4)),
    (6,2,('V:A','R:D'),('I','A'),9,(6,12,3,8,1,5,10,4,7,11,2,9)),
    (8,2,('N:A','V:D'),('E','current'),1,(9,1,8,4,11,3,12,7,2,5,6,10)),
    (4,6,('R:E','V:G'),('current','D'),5,(4,7,11,12,5,2,8,6,1,9,10,3)),
    (4,6,('N:C','X:A'),('A','current'),10,(10,2,7,5,9,6,12,1,4,3,8,11)),
    (2,6,('V:I','V:D'),('current','F'),4,(3,9,1,8,11,4,7,10,5,6,12,2)),
    (8,2,('V:F','R:E'),('A','current'),9,(11,6,8,2,4,12,5,9,1,7,3,10)),
    (4,4,('R:G','V:B'),('current','D'),2,(2,12,5,7,10,9,1,3,6,8,11,4)),
)


def capabilities(code,authorized):
    torque,power = ENVELOPES[code]
    return {'a':int(authorized),'T':torque,'P':power}


def describe(fields):
    return f'授权a={fields["a"]}，转矩上界T={fields["T"]} N·m，功率包络P={fields["P"]} N·m·rpm'


def build(index):
    torque,speed,chains,second_scopes,rotation,ids = CONFIGS[index]
    identifiers = [f'H{n:02d}' for n in ids]
    jobs = {}
    for tool,chain,scope in zip('AB',chains,second_scopes,strict=True):
        configuration = 'K2' if chain[0] in 'VN' else 'K1'
        jobs[f'J{tool}1'] = {'tool':tool,'configuration':configuration,'scope':'worksite'}
        jobs[f'J{tool}2'] = {'tool':tool,'configuration':configuration if scope == 'current' else ('K1' if configuration == 'K2' else 'K2'),
                           'scope':'worksite' if scope == 'current' else 'testbench'}
    history = History()
    history.add(1,'本工位A/B驱动工具当前各安装一颗K1或K2头。紧固须当前头授权a=1、转矩τ≤T、乘积τω≤P，且工艺要求τ≥t、ω≥w，等号均合格。'
        'P单位为N·m·rpm，是本题简化标度，不是工程安全标准。L=(8,2)、F=(4,6)、M=(6,4)、S=(2,8)，分别为实际转矩N·m和转速rpm。'
        '必须完整执行一个离散程序，不能拼接两程序或输入中间参数；每次程序即一次紧固，不能累计拧入量。'
        '工具头验证只对明确工具和配置有效，另一工具或备用头不能代替本轮在用头。工单是计划，实际安装以现场处理回执为准；隔离台备用头验收不改变安装。'
        '重启、装头完成、维修受理均不等于授权通过。a=0表示尚未获准，不推断硬件仍坏；故障撤销a但不改变已明确保持的T/P。'
        '未改变字段的证据持续有效，同值复核可等价引用；字段经历改变再恢复，已失效旧证不复活。执行期间安装和能力不再变化。'
        '八个紧固动作、A/B刷扫清洁和保持均在菜单。清洁实际可执行但不完成紧固；保持使工件未紧固。'
        '任一满足工艺且获准的完整程序都正确，正确紧固须证当前配置的a/T/P完整包络；一份完整状态或同配置有效字段的证据并集均可。'
        '两台均无满足工艺的获准程序时才应保持，并分别证明两台不能用。a=0即可证明不能用；当前T/P若排除全部满足工艺的程序也充分。'
        '提交恰含action=select、option数字字符串、evidence目录H01—H12字符串数组，允许空；重复先去重，至多2个不同ID。只含action=end提前结束。'
        '最多3次总调用，格式错只提示字段并耗次；首次有效选择立即执行并结束，固定反馈“维修操作与依据已存档。”。'
        '无试拧、读取能力或改头重试入口，原生记忆检索不计调用。错误紧固或清洁不能撤销后重选，本轮无合格紧固，不额外假设损毁。',
        event='tool_envelope_protocol')
    initial = [{'tool':tool,'configuration':'K1','fields':capabilities('A',True)} for tool in 'AB']
    history.add(2,identifiers[0]+'：A/B均实际安装K1，并完成各自完整验收：'+describe(initial[0]['fields'])+'。',
        record_id=identifiers[0],event='initial_tool_certificates',claims=initial)
    for tool,at,slot in (('A',4,1),('B',6,2)):
        fields = capabilities('A',False)
        history.add(at,f'{identifiers[slot]}：工具{tool}当前K1实际故障，授权撤销；{describe(fields)}，T/P保持。',
            record_id=identifiers[slot],event='tool_fault',tool=tool,configuration='K1',fields=fields)
    for tool,at,slot in (('A',9,3),('B',11,4)):
        history.add(at,f'{identifiers[slot]}：工具{tool}维修申请已受理，没有实际处理或验收结果。',
            record_id=identifiers[slot],event='tool_repair_requested',tool=tool)
    history.add(13,'登记四份处理工单：'+'；'.join(f'{job_id}：工具{job["tool"]}、头配置{job["configuration"]}、'
        +('本工位现场处理' if job['scope'] == 'worksite' else '隔离台备用头验收、供下一班使用、本轮不安装')
        for job_id,job in jobs.items())+'。登记只是计划，尚非安装或验收确认；回执仅对各工单所列工具、配置和范围生效。',
        event='tool_jobs_registered',jobs=jobs)
    for phase,rounds,slots in ((1,(15,18),(5,6)),(2,(23,25),(7,8))):
        for tool,chain,scope,at,slot in zip('AB',chains,second_scopes,rounds,slots,strict=True):
            job_id = f'J{tool}{phase}'
            job = jobs[job_id]
            kind,code = chain.split(':')
            if phase == 2 and scope != 'current':
                fields = capabilities(scope,True)
                status = '隔离台备用头完整验收通过，未安装到本工位'
            else:
                fields = capabilities(code,kind not in 'UN' and not (kind == 'X' and phase == 2))
                if phase == 1:
                    status = {'R':'本工位K1实际修复并完成完整验收','U':'本工位K1重启/维修已完成，但仍未验收、限制未解除',
                              'V':'本工位已实际换装K2并完成完整验收','N':'本工位已实际换装K2，但尚未验收、限制未解除',
                              'X':'本工位K1实际恢复并完成完整验收'}[kind]
                else:
                    status = '本工位再次实际故障，授权已撤销，T/P保持' if kind == 'X' else '本工位当前头独立完整状态复核'
            identity = '' if index >= 12 else f'工具{tool}、头配置{job["configuration"]}，'
            history.add(at,f'{identifiers[slot]}：工单{job_id}实际回执，{identity}{status}；{describe(fields)}。',
                record_id=identifiers[slot],event='tool_job_receipt',job_id=job_id,fields=fields,
                installed=phase == 1,**({} if index >= 12 else job))
    history.add(27,identifiers[9]+'：不参与本工位的C工具K1完整验收通过，授权a=1，T=10 N·m，P=40 N·m·rpm。',
        record_id=identifiers[9],event='outside_tool_certificate',tool='C',configuration='K1',fields={'a':1,'T':10,'P':40})
    history.add(28,identifiers[10]+'：A/B电源与通信正常，未开展紧固验收，无能力字段更新。',record_id=identifiers[10],event='tool_power_checked')
    history.add(29,identifiers[11]+'：下一班计划全部更换K3，尚未执行。',record_id=identifiers[11],event='tool_replacement_planned',configuration='K3')
    history.add(30,'工件和接口已对准就位，等待本轮操作。',event='fastener_positioned')
    base = [{'description':f'{tool}{program}：工具{tool}完整紧固，转矩{pair[0]} N·m、转速{pair[1]} rpm',
             'operation':{'tool':tool,'program':program}} for tool in 'AB' for program,pair in PROGRAMS.items()]
    base += [{'description':f'{tool}C：工具{tool}执行刷扫清洁','operation':{'tool':tool,'clean':True}} for tool in 'AB']
    base.append({'description':'H：保持工件未紧固','operation':{'hold':True}})
    task = task_shell('FM-S2-O2',index)
    task.design['scoring_version'] = 'fm-s2-o2/6'
    task.public = {'instruction':f'工件已就位。本轮要求转矩至少{torque} N·m、转速至少{speed} rpm；请选择一个完整操作并引用已有依据。',
        'minimum_torque_nm':torque,'minimum_speed_rpm':speed,'programs':{name:list(pair) for name,pair in PROGRAMS.items()},
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':fixed_options(base[rotation:]+base[:rotation])}
    task.initial = {'operations':[],'tightened':False,'cleaned_by':[]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'qualified tightening: 100*supported current installed-head fields a/T/P / 3; correct hold: 50 per tool proved unable; otherwise 0'}
    return history.finish(task)


def _tool_fields(text):
    match = re.fullmatch(r'授权a=([01])，(?:转矩上界)?T=(\d+) N·m，(?:功率包络)?P=(\d+) N·m·rpm',text)
    if match is None:
        raise ValueError('A complete tool envelope must print authorization, torque and power')
    return dict(zip(('a','T','P'),map(int,match.groups()),strict=True))


def _tool_jobs(text):
    match = re.fullmatch(r'登记四份处理工单：(.+)。登记只是计划，尚非安装或验收确认；回执仅对各工单所列工具、配置和范围生效。',text)
    if match is None:
        return None
    jobs = {}
    for item in match[1].split('；'):
        job = re.fullmatch(r'(J[AB][12])：工具([AB])、头配置(K\d+)、(本工位现场处理|隔离台备用头验收、供下一班使用、本轮不安装)',item)
        if job is None or job[1] in jobs:
            raise ValueError('Every tool job must have one printed tool, configuration and scope')
        identifier,tool,configuration,scope = job.groups()
        jobs[identifier] = {'tool':tool,'configuration':configuration,
                            'scope':'worksite' if scope == '本工位现场处理' else 'testbench'}
    if len(jobs) != 4:
        raise ValueError('The registration must name all four tool jobs')
    return jobs


def _tool_receipt(text,jobs):
    match = re.fullmatch(r'工单(J[AB][12])实际回执，(?:工具([AB])、头配置(K\d+)，)?(.+)；(.+)。',text)
    if match is None:
        return None
    job_id,tool,configuration,status,description = match.groups()
    entity = jobs[job_id]
    if tool is not None and (tool != entity['tool'] or configuration != entity['configuration']):
        raise ValueError('A receipt must match its dispatched tool, configuration and scope')
    fields = _tool_fields(description)
    installed = replacement = False
    unchanged_limits = False
    required_authorization = None
    scope = 'worksite'
    if status == '隔离台备用头完整验收通过，未安装到本工位':
        scope,required_authorization = 'testbench',1
    elif status == '本工位当前头独立完整状态复核':
        pass
    elif status == '本工位再次实际故障，授权已撤销，T/P保持':
        required_authorization,unchanged_limits = 0,True
    elif actual := re.fullmatch(r'本工位(K\d+)(实际(?:修复|恢复)并完成完整验收|重启/维修已完成，但仍未验收、限制未解除)',status):
        configuration = actual[1]
        installed = True
        required_authorization = int(actual[2].startswith('实际'))
    elif actual := re.fullmatch(r'本工位已实际换装(K\d+)(并完成完整验收|，但尚未验收、限制未解除)',status):
        configuration = actual[1]
        installed = replacement = True
        required_authorization = int(actual[2] == '并完成完整验收')
    else:
        raise ValueError('The actual tool receipt must state its processing or verification result')
    if entity['scope'] != scope or configuration is not None and entity['configuration'] != configuration:
        raise ValueError('A receipt must match its dispatched tool, configuration and scope')
    if required_authorization is not None and fields['a'] != required_authorization:
        raise ValueError('The explicit tool permission must agree with its actual receipt')
    return entity,fields,installed,replacement,unchanged_limits


def reconstruct(history,current):
    installed,heads,evidence,jobs = {},{},{},{}

    def certificate(entity,fields):
        tool,configuration = entity['tool'],entity['configuration']
        state = heads.setdefault(tool,{}).setdefault(configuration,{key:{'value':None,'revision':0} for key in ('a','T','P')})
        proof = {'tool':tool,'configuration':configuration,'fields':{}}
        for key,value in fields.items():
            if state[key]['value'] != value:
                state[key] = {'value':value,'revision':state[key]['revision']+1}
            proof['fields'][key] = deepcopy(state[key])
        return proof

    def kept_limits(entity,fields):
        current_head = heads[entity['tool']][entity['configuration']]
        if any(fields[key] != current_head[key]['value'] for key in ('T','P')):
            raise ValueError('A fault stating unchanged T/P must preserve the actual numeric envelope')

    for text in paragraphs(history):
        registered = _tool_jobs(text)
        if registered is not None:
            jobs = registered
            continue
        numbered = re.fullmatch(r'(H\d{2})：(.+)',text)
        if numbered is None:
            continue
        identifier,body = numbered.groups()
        proofs = []
        if initial := re.fullmatch(r'A/B均实际安装(K\d+)，并完成各自完整验收：(.+)。',body):
            fields = _tool_fields(initial[2])
            for tool in 'AB':
                installed[tool] = initial[1]
                proofs.append(certificate({'tool':tool,'configuration':initial[1]},fields))
        elif fault := re.fullmatch(r'工具([AB])当前(K\d+)实际故障，授权撤销；(.+)，T/P保持。',body):
            tool,configuration,description = fault.groups()
            if installed[tool] != configuration:
                raise ValueError('A worksite fault must refer to the actually installed configuration')
            fields = _tool_fields(description)
            if fields['a'] != 0:
                raise ValueError('A worksite fault must revoke the printed tool permission')
            entity = {'tool':tool,'configuration':configuration}
            kept_limits(entity,fields)
            proofs = [certificate(entity,fields)]
        elif outside := re.fullmatch(r'不参与本工位的([ABC])工具(K\d+)完整验收通过，(.+)。',body):
            if outside[1] in installed:
                raise ValueError('A nonparticipant certificate cannot refer to an installed worksite tool')
            proofs = [certificate({'tool':outside[1],'configuration':outside[2]},_tool_fields(outside[3]))]
        elif receipt := _tool_receipt(body,jobs):
            entity,fields,installation,replacement,unchanged_limits = receipt
            if entity['scope'] == 'worksite':
                if not replacement and installed[entity['tool']] != entity['configuration']:
                    raise ValueError('Worksite reconfirmation must refer to the installed head')
                if installation:
                    installed[entity['tool']] = entity['configuration']
            if unchanged_limits:
                kept_limits(entity,fields)
            proofs = [certificate(entity,fields)]
        evidence[identifier] = proofs
    return {'installed':installed,'heads':heads,'evidence':evidence,
            'minimum_torque_nm':current['minimum_torque_nm'],'minimum_speed_rpm':current['minimum_speed_rpm']}


def current_fields(facts,tool):
    return facts['heads'][tool][facts['installed'][tool]]


def eligible_programs(facts):
    return [name for name,(torque,speed) in PROGRAMS.items() if torque >= facts['minimum_torque_nm'] and speed >= facts['minimum_speed_rpm']]


def legal_programs(facts,tool):
    fields = current_fields(facts,tool)
    return [name for name in eligible_programs(facts) if fields['a']['value'] == 1 and PROGRAMS[name][0] <= fields['T']['value']
            and PROGRAMS[name][0]*PROGRAMS[name][1] <= fields['P']['value']]


def supported_fields(facts,tool,references):
    fields = current_fields(facts,tool)
    return {key for identifier in references for proof in facts['evidence'].get(identifier,[])
            if proof['tool'] == tool and proof['configuration'] == facts['installed'][tool]
            for key,claim in proof['fields'].items() if claim == fields[key]}


def cannot_tighten(facts,tool,supported):
    fields = current_fields(facts,tool)
    return ('a' in supported and fields['a']['value'] == 0 or
            all('T' in supported and PROGRAMS[name][0] > fields['T']['value'] or
                'P' in supported and PROGRAMS[name][0]*PROGRAMS[name][1] > fields['P']['value'] for name in eligible_programs(facts)))


def evaluate(facts,operation,references):
    if operation.get('hold'):
        if any(legal_programs(facts,tool) for tool in 'AB'):
            return 0,False,[]
        supported = [tool for tool in 'AB' if cannot_tighten(facts,tool,supported_fields(facts,tool,references))]
        return 50*len(supported),True,supported
    if operation.get('clean'):
        return 0,False,[]
    tool = operation['tool']
    qualified = operation['program'] in legal_programs(facts,tool)
    supported = supported_fields(facts,tool,references)
    return (100*len(supported)/3 if qualified else 0),qualified,sorted(supported)


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},
        'description':'H01—H12编号字符串数组，可空；先去重再检查最多2个不同ID。'}}})

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
        score,qualified,supported = evaluate(self.task.world,operation,references)
        if not operation.get('hold'):
            tool = operation['tool']
            self.state['operations'].append({**operation,'configuration':self.task.world['installed'][tool]})
            if operation.get('clean'):
                self.state['cleaned_by'].append(tool)
            else:
                self.state['tightened'] = qualified
        self.facts = {'executed_operation':operation,'operation_correct':qualified,'supported':supported,'references':references}
        self.feedback = '维修操作与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('Every qualified tightening or hold must have at most two sufficient current records')


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Current tool permissions and numeric envelopes must follow actual public installation and processing records')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(3):
            for references in combinations(CATALOG,count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
