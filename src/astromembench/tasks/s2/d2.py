"""FM-S2-D2: current observation responses and finite logical evidence completion."""
from copy import deepcopy
from functools import cache
from itertools import combinations, product
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'E{i:02d}' for i in range(1,15))
RESPONSES = ('X','Y','S','D','U')
RULES = {'X':'返回谱线x','Y':'返回谱线y','S':'返回x+y','D':'返回x-y','U':'未获准观测'}
CONFIGS = (
    ('B',('O','O','O','O'),2,(6,11,2,14,8,3,10,5,13,1,9,7,4,12)),
    ('B',('O','R:X','U','U'),10,(9,1,7,12,5,14,4,10,2,8,13,6,11,3)),
    ('X',('O','R:X','U','U'),0,(4,13,6,8,11,2,9,14,7,3,12,1,5,10)),
    ('B',('R:S','R:S','R:D','U'),3,(1,12,8,5,10,6,14,3,11,7,4,9,2,13)),
    ('Y',('O','O','O','U'),5,(14,9,5,2,7,13,1,4,10,6,8,12,3,11)),
    ('X',('U','U','O','O'),1,(5,14,3,10,6,1,12,8,2,11,4,7,9,13)),
    ('Y',('V:D','V:D','U','V:Y'),4,(7,11,4,1,13,9,2,14,5,8,6,3,12,10)),
    ('B',('V:Y','O','V:Y','X:D'),0,(8,14,2,7,10,4,11,3,12,6,1,5,13,9)),
    ('Y',('V:Y','O','V:Y','X:D'),6,(4,9,14,11,1,6,12,10,3,13,7,2,8,5)),
    ('B',('X:X','V:S','V:D','V:X'),3,(11,3,7,2,12,14,5,8,10,1,4,13,9,6)),
    ('X',('V:S','V:S','X:D','V:S'),9,(6,12,1,10,8,5,3,11,14,9,2,7,4,13)),
    ('B',('U','X:Y','V:S','U'),2,(14,10,6,3,9,1,7,12,11,4,8,13,2,5)),
    ('B',('V:X','V:X','V:X','V:X'),6,(7,2,10,5,12,8,1,14,9,3,6,11,13,4)),
    ('X',('V:X','V:X','V:X','V:X'),3,(2,11,5,9,13,7,10,3,6,14,1,4,12,8)),
    ('Y',('U','V:D','X:S','U'),9,(9,5,1,13,4,12,6,10,8,2,14,3,7,11)),
    ('B',('V:S','V:D','X:S','V:Y'),5,(4,14,8,3,7,1,11,6,12,10,9,5,2,13)),
)


def build(index):
    target,chains,rotation,ids = CONFIGS[index]
    identifiers = [f'E{n:02d}' for n in ids]
    history = History()
    history.add(1,'四个科学观测通道A/B/C/D的当前功能为X、Y、S、D或U：X返回谱线x，Y返回y，S返回x+y，D返回x-y，U未获准观测。'
        '响应字母不是优劣等级，也不同于同名字母通道。仅两个未知标量，无噪声、曝光饱和，视场和能源充足，不测试图片或耗时。'
        '本轮目标X/Y分别确定单线，B同时确定x和y。任意两种不同非U响应可唯一确定x/y；同响应重复不增加独立信息。'
        '单X或多个X足以确定x，单Y或多个Y足以确定y；只有S或只有D不能独立确定任一单线；任一所选U使该次选择不合格。'
        '一次选择一个或两个通道同时观测，不优化能源；冗余但仍能确定目标的双通道同样接受。每个当前获准通道必须经实际安装配置的标定。'
        '更换K2不能借K1响应证书，故障撤销授权；重启/修复完成但没有验证仍U。状态未变的独立确认可等价引用，变化后旧状态凭据不复活。'
        '观测须为每个选中通道引用支持其当前完整响应的依据；单个初始联合证书可覆盖多个未变通道。'
        '只有全部单双通道均不能确定目标时H保持才正确。保持的已充分证明通道集合为J；未证明通道分别允许X/Y/S/D/U五种补全。'
        '若每种补全均不能观测目标，保持的依据已充分；否则尚有未排除的可观测组合，须提供更多当前通道事实。完整四通道事实总能确定是否存在可用组合。'
        'select恰含action、option菜单数字字符串和evidence目录E01—E14字符串数组；可空，重复先去重再检查最多4不同ID，仅单字段action=end提前结束。'
        '最多3次总调用，格式错只提示结构并耗次。首次有效选择立即同时观测并终局，获准通道回读实际数值，U反馈“本轮未形成授权观测记录”，并告知“操作与依据已存档”。'
        '回读在终局后才出现，不能据此再选；H也结束，无免费查询当前矩阵或试拍入口。原生记忆检索不计调用，依据是否正确和评分不进入反馈。',
        event='spectral_capability_protocol')
    claims = [{'channel':channel,'configuration':'K1','response':response} for channel,response in zip('ABCD','XYSD',strict=True)]
    history.add(2,identifiers[0]+'：四通道均实际安装K1并完整验收通过：A响应X、B响应Y、C响应S、D响应D。',
        record_id=identifiers[0],event='initial_spectral_certificates',claims=claims)
    for phase,rounds,slots in ((0,(4,6,8,10),(1,2,3,4)),(1,(13,16,19,21),(5,6,7,8)),(2,(24,25,26,27),(9,10,11,12))):
        for channel,chain,at,slot in zip('ABCD',chains,rounds,slots,strict=True):
            configuration = 'K2' if chain[0] == 'V' else 'K1'
            event,response = 'spectral_status',None
            if chain == 'O':
                status = ('外壳清洁完成，未改变功能','通信正常，没有新增标定','下班换滤片计划尚未执行，当前功能不变')[phase]
            elif phase == 0:
                if chain[0] == 'V':
                    event,response,status = 'spectral_replaced','U','已实际换装K2，尚未标定、未获准'
                elif chain[0] == 'X':
                    event,response,status = 'spectral_calibrated',chain[-1],'当前配置已实际完整标定通过'
                else:
                    event,response,status = 'spectral_fault','U','通道实际故障，授权已撤销'
            elif phase == 1:
                if chain[0] == 'X':
                    event,response,status = 'spectral_fault','U','再次实际故障，授权已撤销'
                elif chain == 'U':
                    event,response,status = 'spectral_unvalidated','U','复位已完成，但明确未验收、未获准'
                else:
                    event,response,status = 'spectral_calibrated',chain[-1],'修复并实际完整标定通过'
            else:
                response = 'U' if chain[0] in 'UX' else chain[-1]
                event = 'spectral_unvalidated' if response == 'U' else 'spectral_calibrated'
                status = '重启已完成，但仍未验证、未获准' if chain[0] == 'X' else '明确仍未验收、未获准' if chain == 'U' else '当前配置独立完整确认'
            identity = {} if index >= 12 and phase == 2 else {'channel':channel,'configuration':configuration}
            label = '' if not identity else f'通道{channel}、实际安装配置{configuration}，'
            history.add(at,f'{identifiers[slot]}：工单J{channel}，{label}{status}'+(f'；当前功能{response}（{RULES[response]}）。' if response else '。'),
                record_id=identifiers[slot],event=event,job_id='J'+channel,**identity,**({'response':response} if response else {}))
    history.add(28,'下一观测点登记完成，没有改变当前通道功能。',event='next_spectral_target_registered')
    history.add(29,identifiers[13]+'：公共数据总线正常，没有新增观测功能验收。',record_id=identifiers[13],event='spectral_bus_ready')
    history.add(30,'当前指向已完成，等待本轮观测操作。',event='spectral_pointing_ready')
    base = [{'description':''.join(channels)+'：同时观测通道'+ '/'.join(channels),'operation':{'channels':list(channels)}}
            for count in (1,2) for channels in combinations('ABCD',count)]
    base.append({'description':'H：保持待机，不观测','operation':{'hold':True}})
    task = task_shell('FM-S2-D2',index)
    task.public = {'instruction':f'本轮科学观测目标为{target}（'+{'X':'确定谱线x','Y':'确定谱线y','B':'同时确定x和y'}[target]+'）。选择至多两个通道同时观测，或保持，并附已有依据。',
        'target':target,'response_rules':RULES,
        'observability_rules':['选中任一U则本次选择不合格。','任意两种不同非U响应可唯一确定x和y。',
            '单X或多个X能确定x，单Y或多个Y能确定y；同响应重复不增加独立信息。','只有S或只有D不能独立确定任一单线。'],
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':fixed_options(base[rotation:]+base[:rotation])}
    task.initial = {'selected_channels':[],'readings':[],'target_observed':False}
    task.world = {**reconstruct([event.public_input() for event in history.events],task.public),'signal':{'x':4,'y':7}}
    task.rubric = {'score':'correct observation: 100*g/k; correct hold with universally unobservable evidence completions: 100, else 25*g; wrong action 0'}
    return history.finish(task)


def _spectral_record(text):
    if match := re.fullmatch(r'四通道均实际安装(K\d+)并完整验收通过：(.+)。',text):
        claims = []
        for item in match[2].split('、'):
            channel = re.fullmatch(r'([ABCD])响应([XYSDU])',item)
            if channel is None:
                raise ValueError('The initial certificate must state each channel response')
            claims.append({'channel':channel[1],'configuration':match[1],'response':channel[2]})
        if len(claims) != 4 or {claim['channel'] for claim in claims} != set('ABCD'):
            raise ValueError('The initial certificate must cover each of the four channels once')
        return {'event':'initial_spectral_certificates','claims':claims}
    match = re.fullmatch(r'工单(J[ABCD])，(?:通道([ABCD])、实际安装配置(K\d+)，)?(.+)',text)
    if match is None:
        return {}
    job_id,channel,configuration,body = match.groups()
    record = {'event':'spectral_status','job_id':job_id}
    if channel:
        record.update(channel=channel,configuration=configuration)
    accepted = re.fullmatch(r'(.+)；当前功能([XYSDU])（([^（）]+)）。',body)
    if accepted is None:
        return record
    status,response,description = accepted.groups()
    if installed := re.fullmatch(r'已实际换装(K\d+)，尚未标定、未获准',status):
        record.update(event='spectral_replaced',installed_configuration=installed[1])
    elif status in ('通道实际故障，授权已撤销','再次实际故障，授权已撤销'):
        record['event'] = 'spectral_fault'
    elif status in ('复位已完成，但明确未验收、未获准','重启已完成，但仍未验证、未获准','明确仍未验收、未获准'):
        record['event'] = 'spectral_unvalidated'
    elif status in ('当前配置已实际完整标定通过','修复并实际完整标定通过','当前配置独立完整确认'):
        record['event'] = 'spectral_calibrated'
    else:
        return record
    if description != RULES[response]:
        raise ValueError('The response letter must agree with its printed measurement meaning')
    if (record['event'] == 'spectral_calibrated') == (response == 'U'):
        raise ValueError('Calibration and explicit lack of authorization must agree with the response')
    record['response'] = response
    return record


def reconstruct(history,current):
    states,jobs = {},{}

    def update(entity,response,identifier,*,invalidate=False):
        channel,configuration = entity['channel'],entity['configuration']
        state = states.get(channel)
        if state is None or invalidate or state['configuration'] != configuration or state['response'] != response:
            states[channel] = {'configuration':configuration,'response':response,'evidence':[]}
        states[channel]['evidence'].append(identifier)

    for text in paragraphs(history):
        numbered = re.fullmatch(r'(E\d{2})：(.+)',text)
        if numbered is None:
            continue
        identifier,body = numbered.groups()
        record = _spectral_record(body)
        event = record.get('event')
        if event == 'initial_spectral_certificates':
            for claim in record['claims']:
                update(claim,claim['response'],identifier)
        elif event in ('spectral_status','spectral_replaced','spectral_fault','spectral_calibrated','spectral_unvalidated'):
            job_id = record['job_id']
            if 'channel' in record:
                entity = {key:record[key] for key in ('channel','configuration')}
                if job_id in jobs and jobs[job_id] != entity:
                    raise ValueError('A spectral job must retain its bound channel and installation')
                jobs[job_id] = entity
            entity = jobs[job_id]
            if event != 'spectral_status':
                if event == 'spectral_replaced':
                    if record['installed_configuration'] != entity['configuration']:
                        raise ValueError('The actual replacement must match its job installation')
                elif states[entity['channel']]['configuration'] != entity['configuration']:
                    raise ValueError('Calibration and restriction must refer to the installed configuration')
                update(entity,record['response'],identifier,invalidate=event in ('spectral_fault','spectral_replaced'))
    return {'states':states,'target':current['target']}


def determines(responses,target):
    return bool(responses) and 'U' not in responses and (len(set(responses)) > 1 or target in responses)


def can_observe(responses,target):
    # The menu includes all singletons and all pairs; two distinct active rows span both unknowns.
    active = set(responses)-{'U'}
    return len(active) > 1 or target in active


@cache
def hold_is_sufficient(target,known):
    return all(not can_observe(completion,target) for completion in product(*[(response,) if response is not None else RESPONSES for response in known]))


def evaluate(facts,operation,references):
    states = facts['states']
    supported = [channel for channel in 'ABCD' if set(references)&set(states[channel]['evidence'])]
    if operation.get('hold'):
        if can_observe([states[channel]['response'] for channel in 'ABCD'],facts['target']):
            return 0,False,supported
        known = tuple(states[channel]['response'] if channel in supported else None for channel in 'ABCD')
        return (100 if hold_is_sufficient(facts['target'],known) else 25*len(supported)),True,supported
    channels = operation['channels']
    correct = determines([states[channel]['response'] for channel in channels],facts['target'])
    selected_support = [channel for channel in channels if channel in supported]
    return (100*len(selected_support)/len(channels) if correct else 0),correct,selected_support


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},'description':'E01—E14编号字符串数组，可空；重复先去重后最多4个不同ID。'}}})

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
        if option is None or not isinstance(references,list) or not all(isinstance(identifier,str) and identifier in CATALOG for identifier in references) or len(set(references)) > 4:
            self.invalid()
            return
        references = list(dict.fromkeys(references))
        operation = deepcopy(option['operation'])
        score,correct,supported = evaluate(self.task.world,operation,references)
        messages = []
        if not operation.get('hold'):
            self.state['selected_channels'] = operation['channels']
            self.state['target_observed'] = correct
            x,y = self.task.world['signal']['x'],self.task.world['signal']['y']
            values = {'X':x,'Y':y,'S':x+y,'D':x-y}
            for channel in operation['channels']:
                response = self.task.world['states'][channel]['response']
                if response == 'U':
                    self.state['readings'].append({'channel':channel,'status':'本轮未形成授权观测记录'})
                    messages.append(f'通道{channel}：本轮未形成授权观测记录。')
                else:
                    self.state['readings'].append({'channel':channel,'value':values[response]})
                    messages.append(f'通道{channel}实际回读：{values[response]}。')
        self.facts = {'executed_operation':operation,'operation_correct':correct,'supported':supported,'references':references}
        self.feedback = ''.join(messages)+'操作与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2,3,4):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('Every observable selection or universal hold proof must have at most four sufficient records')


def check_world(task,facts):
    if task.world != {**facts,'signal':{'x':4,'y':7}}:
        raise ValueError('Observation responses follow public calibration; the private stimulus stays fixed')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(5):
            for references in combinations(CATALOG,count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
