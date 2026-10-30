"""FM-S2-O1: retained single-call precision inspection and explicit restrictions."""
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

CATALOG = tuple(f'E{i:02d}' for i in range(1,13))
SCORING_VERSION = 'm15/4.1-explicit-unvalidated-receipts'
FAULTS = {'A':'H服务异常退出','B':'作业内存不足，H服务下架','C':'精密处理单元自检异常'}
RECOVERY = {'A':'释放内存并重载H服务','B':'切换内部处理单元','C':'重启H服务'}
PRECISION = {'A':0.04,'B':0.06,'C':0.08}
CONFIGS = (
    (1,'ABC','K1','b0',(12,10,6,8,9,11,1,5,3,7,4,2)),
    (2,'ACB','K1','b0',(6,8,11,1,10,12,4,9,7,3,2,5)),
    (2,'BAC','K1','b2',(9,12,2,7,3,1,10,4,8,11,5,6)),
    (3,'CBA','K1','b0',(10,6,8,1,3,4,5,2,11,12,9,7)),
    (4,'BCA','K1','b0',(3,12,5,10,11,9,7,6,2,1,4,8)),
    (5,'BAC','K1','b4',(5,12,1,9,4,10,3,8,6,7,2,11)),
    (1,'ACB','K1','b3',(1,9,10,3,11,7,6,8,12,5,4,2)),
    (2,'BAC','K1','b0',(1,5,8,2,4,9,10,6,12,11,7,3)),
    (2,'CBA','K1','b2',(7,3,2,6,8,5,1,11,12,9,10,4)),
    (3,'BCA','K1','b3',(9,1,2,11,6,4,10,8,7,3,12,5)),
    (4,'ACB','K1','b2',(3,1,6,12,5,2,10,4,9,8,11,7)),
    (5,'ABC','K1','b4',(9,8,1,2,5,3,7,6,11,4,12,10)),
    (1,'BCA','K2','b0',(4,3,1,9,12,7,10,2,6,8,5,11)),
    (2,'CAB','K1','b1',(1,9,3,6,5,4,2,11,7,10,8,12)),
    (2,'ACB','K2','b0',(12,4,7,10,5,9,3,6,8,2,11,1)),
    (5,'BCA','K2','b4',(1,9,11,8,5,3,7,6,12,10,2,4)),
)


def build(index):
    group,roles,final_configuration,backup_event,ids = CONFIGS[index]
    primary,backup,other = roles
    precision = PRECISION[primary]
    rounds = (3,5,7,9,11,12,16,19,21,22,26,28) if index < 6 else (3,5,7,10,13,16,18,20,22,25,27,29)
    configurations = dict.fromkeys('ABC','K1')
    history = History()
    history.add(1,f'设备{primary}为部位Q的主巡检设备，{backup}为Q备用，{other}只覆盖部位R，本轮不可改覆盖区。'
        'A/B/C各有I图像记录、O普通测量和H精密测量，初始均安装测量头K1；I不提供合格尺寸，O误差0.50 mm，H须有当前配置的有效验证。'
        'Q要求误差≤0.10 mm，等号可用。主设备满足要求且获准时优先主；否则用满足要求且获准的备用，两者均不能执行才保持。'
        'H故障或下架后，只有本设备H模式在当前安装配置实际验证通过才能解除限制。受限表示尚未获准，不推断硬件必坏。'
        '恢复指令、操作完成和排程不是实际通过；O验证不替H，其他设备不替本设备。再次故障或换测量头作废先前状态依据。'
        '未变化状态持续有效，同状态同精度复验均可作为等价依据；故障限制、验证失败和明确无当前H验证的恢复完成回执均可证明同一限制期间仍不可用。'
        '按一次操作附至多两个不同事件编号，可省略或空数组，重复只计一个。只提交action及可选evidence，不提交option或包装字段；单字段action=end提前结束。'
        '只有一次总调用，格式错误也结束，不能试错重答；原生记忆检索不计环境调用，无免费读取能力或重发历史入口。'
        '合法反馈固定“操作已接收，记录已存档。”，不报告状态或对错。用主需证主可用，用备需证主不可用及备可用，保持需证主备均不能用。'
        '错误动作本轮不能形成合规Q巡检，不另设永久损坏。',
        event='inspection_capability_protocol',primary=primary,backup=backup,other=other,
        coverage={primary:'Q',backup:'Q',other:'R'},initial_configuration='K1')

    def emit(slot,device,event,text,*,mode='H',**facts):
        identifier = f'E{ids[slot-1]:02d}'
        configuration = configurations[device]
        history.add(rounds[slot-1],f'{identifier}：设备{device}、测量头配置{configuration}、{mode}模式：{text}',
            record_id=identifier,event=event,device=device,configuration=configuration,mode=mode,**facts)

    def validate(slot,device,*,passed=True,error_mm=precision,mode='H'):
        emit(slot,device,'capability_validated',f'实际验证通过，误差{error_mm:.2f} mm，获准按该精度使用。' if passed else '恢复验证实际未通过，H继续受限。',
            mode=mode,passed=passed,error_mm=error_mm if passed else None)

    def fault(slot,device):
        emit(slot,device,'capability_limited',FAULTS[primary]+'，H功能限制已生效；O/I正常。')

    def request(slot,device):
        emit(slot,device,'recovery_requested',RECOVERY[primary]+'的恢复指令已受理，没有H验证结论。')

    validate(1,primary,error_mm=0.05)
    emit(2,backup,'capability_unvalidated','H尚未验收、尚未获准，限制已生效；O/I正常。')
    if group == 4:
        fault(3,other)
    else:
        validate(3,other,error_mm=0.05)
    fault(4,primary)
    request(5,other if group == 4 and index < 12 else primary)
    if index >= 12 or group == 1:
        validate(6,primary)
    elif group == 2:
        validate(6,primary,mode='O',error_mm=0.50)
    elif group == 4:
        validate(6,other)
    else:
        validate(6,primary,passed=False)
    validate(7,backup,mode='O',error_mm=0.50)
    if index >= 12:
        if final_configuration == 'K2':
            configurations[primary] = 'K2'
            emit(8,primary,'measurement_head_changed','测量头已实际更换为K2，H尚未验证、未获准；旧K1凭据不适用。')
        else:
            fault(8,primary)
    else:
        validate(8,primary,mode='O',error_mm=0.50)
    recovering = backup if group == 5 else other if group == 4 else primary
    if index < 12 and group in (1,4):
        emit(9,recovering,'capability_validation_scheduled','H复验已排程，等待实际执行。')
    else:
        request(9,recovering)
    if group == 2:
        emit(10,primary,'recovery_completed',RECOVERY[primary]+'的恢复操作已完成，但没有当前配置H验证结果，H仍未获准、限制未解除。',authorized=False)
    else:
        validate(10,recovering,passed=group != 3)
    if backup_event == 'b0':
        validate(11,backup,passed=False)
    elif backup_event == 'b1':
        validate(11,backup,error_mm=0.20)
    elif backup_event == 'b2':
        request(11,backup)
    elif backup_event in ('b3','b5'):
        validate(11,backup,mode='O',error_mm=0.50)
    else:
        validate(11,backup)
    emit(12,other,'inspection_image_recorded','在覆盖部位R完成I图像记录，不改变任何设备的H能力。',mode='I',target='R')
    history.add(30,'Q巡检准备完成，等待本轮操作。',event='inspection_prepared')
    task = task_shell('FM-S2-O1',index,current_input_group='FM-S2-O1-current')
    task.public = {'instruction':'请完成部位Q的尺寸巡检，要求测量误差不超过0.10 mm。请提交本轮操作。',
        'target':'Q','maximum_error_mm':0.1,'time_s':clock('09:00'),'max_steps':1,'record_catalog':list(CATALOG),
        'evidence_format':'至多两个不同事件编号的列表，可为空；重复编号只计一条。',
        'actions':[{'action':device+mode,'description':f'调用{device}{label}'} for device in 'ABC'
            for mode,label in (('I','图像记录'),('O','普通测量'),('H','精密测量'))]
            +[{'action':'HOLD','description':'保持待机，本轮不调用测量功能'}]}
    task.initial = {'performed':None}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'correct operation: 100*g/K; wrong or invalid 0'}
    task.design['scoring_version'] = SCORING_VERSION
    return history.finish(task)


def reconstruct(history,current):
    states,primary,backup,coverage = {},None,None,{}

    def restrict(device,configuration,identifier,*,new_period):
        state = states[device]
        if new_period or state['authorized'] or state['configuration'] != configuration:
            state.update(configuration=configuration,authorized=False,error_mm=None,evidence=[])
        state['evidence'].append(identifier)

    for text in paragraphs(history):
        if match := re.match(r'设备([ABC])为部位([QR])的主巡检设备，([ABC])为\2备用，([ABC])只覆盖部位([QR])，本轮不可改覆盖区。'
                             r'A/B/C各有I图像记录、O普通测量和H精密测量，初始均安装测量头(K\d+)；',text):
            primary,target,backup,other,outside,configuration = match.groups()
            if len({primary,backup,other}) != 3:
                raise ValueError('Inspection roles must identify three different devices')
            coverage = {primary:target,backup:target,other:outside}
            states = {device:{'configuration':configuration,'authorized':False,'error_mm':None,'evidence':[]} for device in 'ABC'}
            continue
        match = re.fullmatch(r'(E\d{2})：设备([ABC])、测量头配置(K\d+)、([IOH])模式：(.+)',text)
        if match is None:
            continue
        identifier,device,configuration,mode,body = match.groups()
        if mode != 'H':
            continue
        state = states[device]
        if changed := re.fullmatch(r'测量头已实际更换为(K\d+)，H尚未验证、未获准；旧(K\d+)凭据不适用。',body):
            if changed[1] != configuration or changed[2] != state['configuration']:
                raise ValueError('A measurement head replacement must name its previous and new installations')
            restrict(device,configuration,identifier,new_period=True)
        elif re.fullmatch(r'(?:H服务异常退出|作业内存不足，H服务下架|精密处理单元自检异常)，H功能限制已生效；O/I正常。',body):
            if state['configuration'] != configuration:
                raise ValueError('An H fault must refer to the installed measurement head')
            restrict(device,configuration,identifier,new_period=True)
        elif body in ('H尚未验收、尚未获准，限制已生效；O/I正常。','恢复验证实际未通过，H继续受限。'):
            if state['configuration'] != configuration:
                raise ValueError('An H restriction must refer to the installed measurement head')
            restrict(device,configuration,identifier,new_period=False)
        elif passed := re.fullmatch(r'实际验证通过，误差(\d+\.\d+) mm，获准按该精度使用。',body):
            if state['configuration'] != configuration:
                raise ValueError('Actual H validation must refer to the installed measurement head')
            error = float(passed[1])
            if not state['authorized'] or state['error_mm'] != error:
                state.update(authorized=True,error_mm=error,evidence=[])
            state['evidence'].append(identifier)
        elif re.fullmatch(r'(?:释放内存并重载H服务|切换内部处理单元|重启H服务)的恢复操作已完成，'
                          r'但没有当前配置H验证结果，H仍未获准、限制未解除。',body):
            if state['configuration'] != configuration or state['authorized']:
                raise ValueError('Unvalidated recovery receipt must explicitly confirm the current restriction')
            state['evidence'].append(identifier)
    ready = lambda device: coverage[device] == current['target'] and states[device]['authorized'] and states[device]['error_mm'] <= current['maximum_error_mm']
    action = primary+'H' if ready(primary) else backup+'H' if ready(backup) else 'HOLD'
    required = {device:list(states[device]['evidence']) for device in ([primary] if action == primary+'H' else [primary,backup])}
    return {'states':states,'coverage':coverage,'primary':primary,'backup':backup,'correct_action':action,'required_evidence':required}


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action',),{'*':{'evidence':{'required':False,'type':'array',
        'description':'填写至多两个不同的 E01–E12 事件编号，可为空列表；重复编号只计一条。'}}})

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action)-{'action','evidence'} or action.get('action') not in [a['action'] for a in self.actions()]:
            self.invalid()
            return
        evidence = action.get('evidence',[])
        if not isinstance(evidence,list) or any(not isinstance(identifier,str) or identifier not in CATALOG for identifier in evidence) or len(set(evidence)) > 2:
            self.invalid()
            return
        required = self.task.world['required_evidence']
        supported = [device for device,valid in required.items() if set(evidence).intersection(valid)]
        correct = action['action'] == self.task.world['correct_action']
        score = 100*len(supported)/len(required) if correct else 0
        self.state['performed'] = action['action']
        self.facts.update(supported_judgments=supported,necessary_judgments=len(required))
        self.feedback = '操作已接收，记录已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    return {'action':facts['correct_action'],'evidence':[valid[0] for valid in facts['required_evidence'].values()]}


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('Precision inspection must follow current H permissions, configurations and primary-first coverage')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(3):
            for references in combinations(CATALOG,count):
                covered = sum(bool(set(references)&set(valid)) for valid in facts['required_evidence'].values())
                score = 100*covered/len(facts['required_evidence']) if row['action'] == facts['correct_action'] else 0
                cases.append(([{'action':row['action'],'evidence':list(references)}],score))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{'action':command['action']}],0),([{}],0)]
