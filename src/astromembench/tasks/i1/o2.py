"""FM-I1-O2: transfer actual component support from frame to gripper and cradle."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

CONFIGS = (
    ('M1',3,((8,'G'),(26,'P:V'))),
    ('M2',1,((7,'G'),(16,'Ub'),(25,'P:L'))),
    ('M2',9,((7,'G'),(14,'Ua'),(21,'Ub'),(27,'P:V'))),
    ('M1',5,((6,'G'),(12,'Ua'),(17,'Ub'),(23,'V'))),
    ('M1',8,((6,'G'),(14,'Ua'),(22,'L'),(27,'P:G'))),
    ('M2',6,((8,'G'),(17,'P:Ub'),(26,'P:Ua'))),
    ('M2',2,((4,'G'),(9,'Ub'),(16,'L'),(23,'G'),(28,'P:V'))),
    ('M1',8,((4,'G'),(9,'Ub'),(15,'L'),(21,'G'),(26,'Ua'))),
    ('M1',4,((6,'G'),(14,'L'),(22,'P:Ua'),(28,'P:G'))),
    ('M2',7,((4,'G'),(9,'Ua'),(16,'L'),(25,'G'),(28,'P:Ub'))),
    ('M2',5,((7,'G'),(16,'P:Ua'),(25,'P:Ub'))),
    ('M1',3,((4,'G'),(8,'Ua'),(13,'L'),(18,'G'),(23,'Ub'),(28,'V'))),
    ('M1',7,((4,'G'),(10,'W:Ua'),(18,'F:Ub'),(27,'P:Ua'))),
    ('M1',9,((4,'G'),(9,'Ua'),(15,'L'),(22,'F:G'),(28,'P:Ub'))),
    ('M2',2,((4,'G'),(9,'Ub'),(14,'F:Ua'),(20,'Ua'),(27,'W:V'))),
    ('M1',6,((4,'G'),(9,'F:Ub'),(14,'Ua'),(20,'Ub'),(27,'F:V'))),
)


def operation(component,code):
    result = {'kind':{'G':'grasp','U':'unlock','V':'move','L':'ungrip'}[code[0]],'component':component}
    if code[0] == 'U':
        result['point'] = code[1]
    return result


def advance(state,op):
    """Apply a selected physical program; returns its actual completion category."""
    kind = op['kind']
    if kind == 'grasp':
        if state['gripped']:
            return 'unchanged'
        state['gripped'] = True
    elif kind == 'unlock':
        if state['location'] != 'frame' or not state['gripped'] or op['point'] not in state['locked']:
            return 'unchanged'
        state['locked'].remove(op['point'])
    elif kind == 'move':
        if not state['gripped'] or state['location'] != 'frame':
            return 'unchanged'
        if state['locked']:
            state['damaged'] = True
            return 'damaged'
        state['location'] = 'C'+op['component'][1]
    else:
        if not state['gripped']:
            return 'unchanged'
        state['gripped'] = False
        if state['location'] == 'frame' and not state['locked']:
            state.update(location='fallen',fallen=True,damaged=True)
            return 'fallen'
    return 'completed'


def next_operations(state,component):
    if state['location'] == 'frame':
        if not state['gripped']:
            codes = ['G']
        elif state['locked']:
            codes = ['U'+point for point in state['locked']]
        else:
            codes = ['V']
    else:
        codes = ['L'] if state['gripped'] else []
    return [operation(component,code) for code in codes]


def build(index):
    target,rotation,events = CONFIGS[index]
    other = 'M2' if target == 'M1' else 'M1'
    history = History()
    components = {m:{'location':'frame','locked':['a','b'],'gripped':False,'fallen':False,'damaged':False} for m in ('M1','M2')}
    history.add(1,'独立维修位M1/M2各有机架、固定点a/b、专用夹持器G1/G2及托架C1/C2，编号在本部件内有效，M1只用G1/C1、M2只用G2/C2。'
        '每个锁紧点独立支撑静止部件，夹持器抓稳也能支撑，托架到位后自行承载。无其他重量、温度或时限条件。'
        '拆卸交接下一步：机架上未抓稳先抓持；已抓稳且还有锁紧点则释放任一仍锁紧点；已抓稳且两点均释则移至托架；到托架后仍抓持则松夹。'
        '双点均锁紧时可先释放任一点。拆点程序要求机架上已经抓持，否则拒绝、固定点不变。'
        '移动未抓持对象会被拒绝；已抓持但仍有锁点则结构损伤、原位置和锁紧关系保持；两点均释才移动，重复移动不推进。'
        '松夹有锁紧点或托架支撑时可由其承载；机架上两点均释时松夹将坠落并损伤，不可撤销。重复抓持/拆已释放点/松开空夹具均不推进。'
        '另一件操作也真实发生，但不推进当前指定件流程；每条历史失败按明确无变化回执保留，不臆加损伤，计划未执行不变。'
        '诊断警告按实际成功与否处理。授权、断电、温控、工具与作业区已确认，不考力学、累计力矩或恢复阶段。'
        '全部10菜单可见，select/字符串option或end，总计最多3次含格式错误；首个有效动作执行后立即终局，不能重选。'
        '格式错误不改变支撑关系，额外字段、数值型和范围外编号均无效。',event='support_transfer_protocol')
    history.add(2,'初始M1、M2均在各自机架，a/b均锁紧，G1/G2均未抓持；没有坠落或损伤。',event='support_initial',components=components)
    all_events = [(at,target,code) for at,code in events]+[(5,other,'G'),(11,other,'Ua'),(19,other,'L'),(24,other,'P:Ub')]
    for at,component,code in sorted(all_events):
        status,program = code.split(':',1) if ':' in code else ('success',code)
        op = operation(component,program)
        gripper,cradle = 'G'+component[1],'C'+component[1]
        description = {'G':f'{gripper}抓持{component}','Ua':f'释放{component}固定点a','Ub':f'释放{component}固定点b',
                       'V':f'{gripper}将{component}移至{cradle}','L':f'{gripper}松开{component}'}[program]
        state = components[component]
        if status == 'P':
            history.add(at,description+'只是计划，尚未执行，部件支撑关系没有变化。',event='support_plan',planned_operation=op,executed=False)
        elif status == 'F':
            if program.startswith('U'):
                point = program[1]
                if point not in state['locked']:
                    raise ValueError('Reviewed failed unlock must leave an actually locked point')
                consequence = f'锁紧机构未释放，{component}的{point}仍锁紧，抓持及其他关系未变'
            elif program == 'G':
                if state['gripped']:
                    raise ValueError('Reviewed failed grasp must remain unsupported by the gripper')
                consequence = f'{gripper}未能抓稳{component}，仍未抓持，已有固定点承载和其他关系不变'
            else:
                if state['location'] != 'frame' or not state['gripped'] or state['locked']:
                    raise ValueError('Reviewed failed move must remain gripped at the frame with both points released')
                consequence = f'转移机构没有完成位移，{component}仍由{gripper}悬持在机架原位，两固定点已释放，未到{cradle}'
            history.add(at,description+'失败：'+consequence+'；没有坠落或损伤。',event='support_change',operation=op,success=False,unchanged=True)
        else:
            if advance(state,op) != 'completed' or state['damaged'] or state['fallen']:
                raise ValueError('Every successful historical program must actually advance without damage')
            consequence = (f'{gripper}已抓稳{component}' if program == 'G' else
                f'{component}固定点{program[1]}已释放，{gripper}继续抓稳部件' if program.startswith('U') else
                f'{component}已实际到达{cradle}并由托架承载，{gripper}仍抓持' if program == 'V' else
                f'{gripper}已松开{component}，部件仍由尚锁紧的固定点承载')
            history.add(at,description+('有控制器警告，但实际回执确认已完成：' if status == 'W' else '实际成功：')+consequence+'。',
                        event='support_change',operation=op,success=True,warning=status == 'W')
    history.add(30,'断电、温控和低层工具准备保持满足。',event='support_work_ready')
    entries = []
    for component in ('M1','M2'):
        g,c = 'G'+component[1],'C'+component[1]
        descriptions = (f'{g}抓持{component}。',f'释放{component}-a。',f'释放{component}-b。',f'{g}把{component}移到{c}。',f'{g}松开{component}。')
        entries += [{'description':text,'operation':operation(component,code)} for text,code in zip(descriptions,('G','Ua','Ub','V','L'),strict=True)]
    task = task_shell('FM-I1-O2',index)
    task.public = {'time_s':clock('09:00'),'max_steps':3,'target':target,'state_fields':[],
        'instruction':f'请继续将{target}拆卸至对应托架并松夹，提交下一项操作。',
        'prerequisites':{'authorized':True,'power_isolated':True,'thermal_ready':True,'tools_ready':True,'work_area_ready':True},
        'actions':fixed_options(entries[rotation:]+entries[:rotation])}
    task.initial = {'time_s':clock('09:00'),'components':components}
    task.world = {'components':components}
    task.rubric = {'score':'100 for any equivalent next operation under the public support-transfer sequence; no partial credit'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,op):
        target = self.task.public['target']
        correct = op in next_operations(self.state['components'][target],target)
        outcome = advance(self.state['components'][op['component']],op)
        self.facts['physical_outcome'] = outcome
        self.feedback = {'completed':'所选操作已完成，回执已归档。','unchanged':'所选操作未推进，原物理关系保持。',
                         'damaged':'所选操作造成结构损伤。','fallen':'夹持解除后部件坠落。'}[outcome]
        return 100 if correct else 0


def _described_operation(text):
    match = re.fullmatch(r'G([12])(抓持|松开)M([12])',text)
    if match:
        gripper,verb,component = match.groups()
        if gripper != component:
            raise ValueError('A component must use its own dedicated gripper')
        return operation('M'+component,'G' if verb == '抓持' else 'L')
    match = re.fullmatch(r'释放(M[12])固定点([ab])',text)
    if match:
        return operation(match[1],'U'+match[2])
    match = re.fullmatch(r'G([12])将M([12])移至C([12])',text)
    if match:
        gripper,component,cradle = match.groups()
        if gripper != component or cradle != component:
            raise ValueError('A component must use its own dedicated gripper and cradle')
        return operation('M'+component,'V')
    return None


def reconstruct(history,current):
    components = {}
    for text in paragraphs(history):
        if text == '初始M1、M2均在各自机架，a/b均锁紧，G1/G2均未抓持；没有坠落或损伤。':
            components = {m:{'location':'frame','locked':['a','b'],'gripped':False,'fallen':False,'damaged':False}
                          for m in ('M1','M2')}
            continue
        match = re.fullmatch(r'(.+?)(?:有控制器警告，但实际回执确认已完成：|实际成功：)(.+)。',text)
        if match:
            op = _described_operation(match[1])
            if op is None:
                continue
            component,kind = op['component'],op['kind']
            gripper,cradle = 'G'+component[1],'C'+component[1]
            state = components[component]
            if advance(state,op) != 'completed':
                raise ValueError('Successful historical support operation must physically advance')
            if kind == 'grasp':
                expected = f'{gripper}已抓稳{component}'
            elif kind == 'unlock':
                expected = f'{component}固定点{op["point"]}已释放，{gripper}继续抓稳部件'
            elif kind == 'move':
                expected = f'{component}已实际到达{cradle}并由托架承载，{gripper}仍抓持'
            else:
                if state['location'] != 'frame' or not state['locked']:
                    raise ValueError('The reported remaining locked points must still support the component')
                expected = f'{gripper}已松开{component}，部件仍由尚锁紧的固定点承载'
            if match[2] != expected:
                raise ValueError('Successful support receipt must report the actual component and holder')
            continue
        match = re.fullmatch(r'(.+?)失败：(.+)；没有坠落或损伤。',text)
        if match:
            op = _described_operation(match[1])
            if op is None:
                continue
            component,kind = op['component'],op['kind']
            gripper,cradle = 'G'+component[1],'C'+component[1]
            state = components[component]
            if kind == 'unlock':
                expected = f'锁紧机构未释放，{component}的{op["point"]}仍锁紧，抓持及其他关系未变'
                unchanged = op['point'] in state['locked']
            elif kind == 'grasp':
                expected = f'{gripper}未能抓稳{component}，仍未抓持，已有固定点承载和其他关系不变'
                unchanged = not state['gripped'] and state['location'] == 'frame' and bool(state['locked'])
            elif kind == 'move':
                expected = f'转移机构没有完成位移，{component}仍由{gripper}悬持在机架原位，两固定点已释放，未到{cradle}'
                unchanged = state['location'] == 'frame' and state['gripped'] and not state['locked']
            else:
                raise ValueError('A failed historical receipt must describe its unchanged support')
            if not unchanged or match[2] != expected:
                raise ValueError('A failed historical receipt must preserve its prior support')
    if set(components) != {'M1','M2'} or any(s['fallen'] or s['damaged'] for s in components.values()):
        raise ValueError('Both components must reach the current handoff without historical damage')
    return {'components':components}


def next_action(facts,current):
    target = current['target']
    return decision_command(current,next_operations(facts['components'][target],target)[0])


def check_world(task,facts):
    if facts != task.world or facts['components'] != task.initial['components']:
        raise ValueError('Private support relations must match the received physical transfer history')


def audit_cases(task,facts,solution):
    target = task.public['target']
    correct = next_operations(facts['components'][target],target)
    return decision_cases(task,solution,lambda op:100 if op in correct else 0)
