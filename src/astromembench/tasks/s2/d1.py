"""FM-S2-D1: exact reachable impulses after channel derating and replacement."""
from copy import deepcopy
from itertools import combinations, product
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'E{i:02d}' for i in range(1,13))
CONFIGS = (
    ((1,0),('O','O','O'),3,(8,3,11,5,2,12,7,1,9,4,10,6)),
    ((-1,-1),('O','O','O'),8,(11,6,1,8,4,10,3,12,5,2,7,9)),
    ((1,1),('R1','R1','U'),24,(5,12,7,2,9,3,11,6,1,8,4,10)),
    ((1,0),('U','O','O'),27,(1,7,10,6,12,4,8,2,11,9,3,5)),
    ((-1,0),('O','U','O'),14,(10,5,3,7,1,11,6,9,2,12,4,8)),
    ((-2,-2),('U','U','O'),22,(7,2,5,10,8,9,4,12,6,3,1,11)),
    ((1,0),('V2','R1','V1'),9,(9,4,12,7,1,6,11,3,8,5,2,10)),
    ((-1,-1),('X2','V1','V2'),12,(6,2,11,9,4,7,1,10,5,12,3,8)),
    ((-1,0),('V1','V2','V2'),23,(2,8,1,10,7,11,5,9,12,3,4,6)),
    ((2,0),('V1','O','V2'),0,(5,12,4,8,9,2,10,6,1,7,11,3)),
    ((-2,-1),('V1','V1','V1'),5,(3,9,2,11,5,8,4,10,7,1,6,12)),
    ((-1,-2),('V1','U','V2'),21,(7,6,9,2,11,4,3,8,10,12,5,1)),
    ((1,-1),('V2','U','V2'),15,(8,2,6,4,10,12,3,9,5,1,11,7)),
    ((-1,1),('O','V1','X2'),8,(10,7,3,12,5,1,9,8,2,11,6,4)),
    ((-2,-2),('V0','U','V1'),24,(2,12,9,7,4,10,1,3,8,6,5,11)),
    ((1,1),('V2','V2','V1'),11,(9,5,12,3,8,6,11,10,1,4,7,2)),
)


def build(index):
    target,chains,rotation,ids = CONFIGS[index]
    identifiers = [f'E{n:02d}' for n in ids]
    history = History()
    history.add(1,'三个姿态执行通道A/B/C每单位脉冲分别贡献二维角冲量(1,0)/(0,1)/(-1,-1)，一次程序a/b/c为0、1或2整数，净量(a-c,b-c)。'
        '本题是离散教学模型；当前目标须精确达到，不接受近似。每通道当前获准幅值上界为0、1或2，0表示停用或尚未验证；任一所选幅值超界即本轮指令不合格。'
        '零脉冲不要求该通道工作；未变的其他通道能力保持。功率充足，不优化能耗，相消脉冲同样可以合格。000是真实零输出，与保持未校正H不同。'
        '证据须对应通道及实际安装K配置，换执行单元后旧配置证书不适用；维修、重启或受理不是验证，明确未验证/限制回执可证明仍停用。'
        '同配置同一连续状态中的等价验收或明确限制均有效；实际故障、能力变化或更换配置使此前状态凭据失效，后来恢复不使已失效证据复活。'
        '合格目标程序须为各非零脉冲通道提供当前能力依据，零脉冲通道不要求证据。'
        '无可行脉冲时才保持；可行性等价于存在整数c满足L=max(0,-dX,-dY)≤c≤U=min(cC,cA-dX,cB-dY)。'
        '保持时任一通道的当前充分证书证明其对应上界低于L就足够，不要求额外提交所有通道证书。'
        '所有27个三位程序和H都显示，不按能力隐藏。select恰含action、option数字字符串、evidence目录E01—E12字符串数组；可空，重复先去重后最多3不同ID。'
        '仅单字段action=end提前结束。三次总调用，格式错只给字段提示并耗次；第一合法业务选择即实际下发并结束，统一反馈“姿态指令与依据已存档。”。'
        '错误脉冲不能撤销再校正，无回合内读取限幅或试点火入口；原生记忆检索不计环境调用，不评分语言说明。',event='attitude_capability_protocol')
    history.add(2,identifiers[0]+'：A/B/C三个执行通道均实际安装K1，各获准幅值上界2，完整验收通过。',
        record_id=identifiers[0],event='initial_attitude_certificates',claims=[{'channel':channel,'configuration':'K1','amplitude':2} for channel in 'ABC'])
    for phase,rounds,slots in ((0,(4,6,8),(1,2,3)),(1,(12,16,20),(4,5,6)),(2,(22,24,26),(7,8,9))):
        for channel,chain,at,slot in zip('ABC',chains,rounds,slots,strict=True):
            configuration = 'K2' if chain[0] == 'V' else 'K1'
            identity = {'channel':channel,'configuration':configuration}
            event,amplitude = 'attitude_status',None
            if chain == 'O':
                text = ('外壳清洁完成，无能力变化','通信正常，未进行能力验收','下一班降额计划尚未实施，没有改变当前能力')[phase]
            elif phase == 0:
                if chain[0] == 'V':
                    event,amplitude,text = 'attitude_replaced',0,'K2执行单元已实际装入，尚未验证、停用上界0'
                elif chain[0] == 'X':
                    event,amplitude,text = 'attitude_validated',int(chain[1]),'当前配置已实际验收'
                else:
                    event,amplitude,text = 'attitude_fault',0,'通道实际故障，授权撤销、上界0'
            elif phase == 1:
                if chain[0] == 'X':
                    event,amplitude,text = 'attitude_fault',0,'再次实际故障，上界0'
                elif chain == 'U':
                    event,amplitude,text = 'attitude_unvalidated',0,'修复操作已完成，但明确仍未验证、限制未解除'
                else:
                    event,amplitude = 'attitude_validated',int(chain[1])
                    text = '实际维修和验收完成' if amplitude else '实际验收明确未通过，继续禁用'
            else:
                amplitude = 0 if chain[0] in 'UX' else int(chain[1])
                event = 'attitude_unvalidated' if chain[0] in 'UX' else 'attitude_validated'
                text = '重启已完成，但仍未验证、上界0' if chain[0] == 'X' else '限制仍在、上界0' if chain == 'U' else '当前配置独立完整复核'
            label = '' if index >= 12 and phase == 2 else f'通道{channel}、安装配置{configuration}，'
            history.add(at,f'{identifiers[slot]}：作业J{channel}，{label}{text}'+(f'；当前获准幅值上界{amplitude}。' if amplitude is not None else '。'),
                record_id=identifiers[slot],event=event,job_id='J'+channel,
                **({} if index >= 12 and phase == 2 else identity),**({} if amplitude is None else {'amplitude':amplitude}))
    history.add(27,'下一班任务登记完成，不改变本班执行通道能力。',event='next_attitude_task_registered')
    history.add(28,identifiers[10]+'：第四实验通道D、配置K1获准幅值2，完整验收通过；D不接入本轮控制矩阵。',
        record_id=identifiers[10],event='outside_attitude_certificate',channel='D',configuration='K1',amplitude=2)
    history.add(29,identifiers[11]+'：电源与指令总线正常，没有新增执行通道验证。',record_id=identifiers[11],event='attitude_bus_ready')
    history.add(30,'当前目标已装载，等待本轮指令。',event='attitude_target_loaded')
    base = [{'description':''.join(map(str,pulses))+f'：分别向A/B/C下发脉冲{list(pulses)}','operation':{'pulses':list(pulses)}} for pulses in product(range(3),repeat=3)]
    base.append({'description':'H：保持当前未校正状态','operation':{'hold':True}})
    task = task_shell('FM-S2-D1',index)
    task.public = {'instruction':f'本轮需要精确校正二维角冲量({target[0]},{target[1]})。选择一个完整脉冲程序或保持，并附已有依据。',
        'target':list(target),'unit_vectors':{'A':[1,0],'B':[0,1],'C':[-1,-1]},'time_s':clock('09:00'),
        'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],'actions':fixed_options(base[rotation:]+base[:rotation])}
    task.initial = {'issued_program':None,'requested_net':None,'correction_completed':False}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'valid exact correction: 100*g/k over nonzero channels; correct hold with any current bottleneck certificate: 100; otherwise 0'}
    return history.finish(task)


def _attitude_record(text):
    if match := re.fullmatch(r'A/B/C三个执行通道均实际安装(K\d+)，各获准幅值上界([012])，完整验收通过。',text):
        return {'event':'initial_attitude_certificates','claims':[
            {'channel':channel,'configuration':match[1],'amplitude':int(match[2])} for channel in 'ABC']}
    match = re.fullmatch(r'作业(J[ABC])，(?:通道([ABC])、安装配置(K\d+)，)?(.+)',text)
    if match is None:
        return {}
    job_id,channel,configuration,body = match.groups()
    record = {'event':'attitude_status','job_id':job_id}
    if channel:
        record.update(channel=channel,configuration=configuration)
    accepted = re.fullmatch(r'(.+)；当前获准幅值上界([012])。',body)
    if accepted is None:
        return record
    status,amplitude = accepted[1],int(accepted[2])
    if installed := re.fullmatch(r'(K\d+)执行单元已实际装入，尚未验证、停用上界0',status):
        record.update(event='attitude_replaced',installed_configuration=installed[1])
    elif status in ('通道实际故障，授权撤销、上界0','再次实际故障，上界0'):
        record['event'] = 'attitude_fault'
    elif status in ('修复操作已完成，但明确仍未验证、限制未解除','重启已完成，但仍未验证、上界0','限制仍在、上界0'):
        record['event'] = 'attitude_unvalidated'
    elif status in ('当前配置已实际验收','实际维修和验收完成','当前配置独立完整复核','实际验收明确未通过，继续禁用'):
        record['event'] = 'attitude_validated'
    else:
        return record
    if (record['event'] != 'attitude_validated' or status == '实际验收明确未通过，继续禁用') and amplitude != 0:
        raise ValueError('An explicitly disabled channel must have zero authorized amplitude')
    record['amplitude'] = amplitude
    return record


def reconstruct(history,current):
    states,jobs = {},{}

    def update(entity,amplitude,identifier,*,invalidate=False):
        channel,configuration = entity['channel'],entity['configuration']
        state = states.get(channel)
        if state is None or invalidate or state['configuration'] != configuration or state['amplitude'] != amplitude:
            states[channel] = {'configuration':configuration,'amplitude':amplitude,'evidence':[]}
        states[channel]['evidence'].append(identifier)

    for text in paragraphs(history):
        numbered = re.fullmatch(r'(E\d{2})：(.+)',text)
        if numbered is None:
            continue
        identifier,body = numbered.groups()
        record = _attitude_record(body)
        event = record.get('event')
        if event == 'initial_attitude_certificates':
            for claim in record['claims']:
                update(claim,claim['amplitude'],identifier)
        elif event in ('attitude_status','attitude_replaced','attitude_fault','attitude_validated','attitude_unvalidated'):
            job_id = record['job_id']
            if 'channel' in record:
                entity = {key:record[key] for key in ('channel','configuration')}
                if job_id in jobs and jobs[job_id] != entity:
                    raise ValueError('A channel job must retain its explicitly bound installation')
                jobs[job_id] = entity
            entity = jobs[job_id]
            if event != 'attitude_status':
                if event == 'attitude_replaced':
                    if record['installed_configuration'] != entity['configuration']:
                        raise ValueError('The actual replacement must match its job installation')
                elif states[entity['channel']]['configuration'] != entity['configuration']:
                    raise ValueError('Validation or fault must refer to the current installed configuration')
                update(entity,record['amplitude'],identifier,invalidate=event in ('attitude_replaced','attitude_fault'))
    dx,dy = current['target']
    lower = max(0,-dx,-dy)
    upper = {'A':states['A']['amplitude']-dx,'B':states['B']['amplitude']-dy,'C':states['C']['amplitude']}
    return {'states':states,'target':list(current['target']),'lower':lower,'upper':upper,
            'bottlenecks':[channel for channel in 'ABC' if upper[channel] < lower]}


def evaluate(facts,operation,references):
    if operation.get('hold'):
        supported = [channel for channel in facts['bottlenecks'] if set(references)&set(facts['states'][channel]['evidence'])]
        return (100 if supported else 0),bool(facts['bottlenecks']),supported
    a,b,c = operation['pulses']
    correct = [a-c,b-c] == facts['target'] and all(value <= facts['states'][channel]['amplitude'] for channel,value in zip('ABC',(a,b,c),strict=True))
    active = [channel for channel,value in zip('ABC',(a,b,c),strict=True) if value]
    supported = [channel for channel in active if set(references)&set(facts['states'][channel]['evidence'])]
    return (100*len(supported)/len(active) if correct and active else 0),correct,supported


class Runtime(TaskRuntime):
    action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':True,
        'items':{'type':'string','enum':list(CATALOG)},'description':'E01—E12编号字符串数组，可空；先去重后最多3个不同ID。'}}})

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
            a,b,c = operation['pulses']
            self.state.update(issued_program=[a,b,c],requested_net=[a-c,b-c],correction_completed=correct)
        self.facts = {'executed_operation':operation,'operation_correct':correct,'supported':supported,'references':references}
        self.feedback = '姿态指令与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2,3):
            for references in combinations(CATALOG,count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('A valid exact correction or bottleneck must be supported by at most three records')


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Channel amplitudes and reachability must follow public installation and acceptance records')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(4):
            for references in combinations(CATALOG,count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
