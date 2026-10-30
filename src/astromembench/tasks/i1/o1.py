"""FM-I1-O1: withdraw the actual free-end guide of an ordered cable path."""
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

INITIAL = {'Q1':['G1','G2'],'Q2':['G3','G4']}
CONFIGS = (
    ('Q1',3,((8,'+3'),(26,'P:+4'))),
    ('Q2',9,((9,'+1'),(25,'P:-1'))),
    ('Q1',5,((7,'-2'),(18,'-1'),(27,'P:+3'))),
    ('Q2',4,((10,'+2'),(27,'P:-2'))),
    ('Q1',9,((8,'+3'),(20,'-3'),(27,'P:+4'))),
    ('Q2',3,((8,'+1'),(20,'-1'),(27,'P:+2'))),
    ('Q1',8,((4,'-2'),(12,'+4'),(22,'+2'),(28,'P:-4'))),
    ('Q2',0,((4,'-4'),(12,'+2'),(22,'+4'),(28,'P:-2'))),
    ('Q1',4,((4,'-2'),(12,'-1'),(22,'+4'),(28,'P:+3'))),
    ('Q2',7,((4,'-4'),(12,'-3'),(22,'+2'),(28,'P:+1'))),
    ('Q1',1,((4,'+3'),(10,'-3'),(18,'-2'),(26,'-1'))),
    ('Q2',9,((4,'-4'),(10,'+1'),(18,'+2'),(26,'-2'))),
    ('Q2',1,((7,'+1'),(15,'F:-1'),(23,'-1'),(28,'P:+2'))),
    ('Q2',4,((7,'-4'),(15,'F:+2'),(23,'+2'),(28,'P:-2'))),
    ('Q1',9,((4,'+4'),(10,'W:-4'),(18,'-2'),(26,'-1'))),
    ('Q1',6,((4,'+3'),(11,'F:-2'),(19,'-3'),(27,'+4'))),
)


def change_route(route,ring,thread):
    if thread:
        if ring in route:
            raise ValueError('A cable may pass through each guide only once')
        route.append(ring)
    else:
        if not route or route[-1] != ring:
            raise ValueError('Successful unthreading must remove the actual free-end guide')
        route.pop()


def build(index):
    target,rotation,events = CONFIGS[index]
    other = 'Q2' if target == 'Q1' else 'Q1'
    history = History()
    routes = deepcopy(INITIAL)
    history.add(1,'巡检探缆Q1/Q2各有固定端和自由端。固定闭合导环G1—G4各有Q1/Q2独立导槽，两缆经过同环不争占。'
        '不能打开环体或剪缆，只能操作自由端；每条缆每环至多穿引一次。路线从固定端到自由端有序排列。'
        '成功穿入未经过的导环将其追加到自由端侧；成功撤出只删除当前末环，不能跳过后面的环撤中间环。'
        '撤回下一步：有环先撤末环，无环才卷收。中间环撤出触发力限位，路线不变；不存在的环撤出不发生。'
        '带环卷收会过载损伤、穿引仍保留；空缆卷入卷盘。另一缆的操作也会实际发生，但不能完成指定缆的撤回。'
        '历史明确失败的回执不改变穿引且未造成损伤，未执行计划不改变路线；有警告时按实际穿入/撤出结果更新。'
        '巡检低层操控、可见性和探头功能正常，不考路径风险、累计距离或时间许可。'
        '全部10项动作始终可选；提交select和字符串option或end，总计最多3次，格式错误也占额度但不改物理关系。'
        '首个有效动作执行后立即终止，不能重选或一次完成全部撤出；额外字段、数值型及范围外编号均无效。',event='cable_guide_protocol')
    history.add(2,'初始穿引按固定端到自由端：Q1依次穿G1、G2；Q2依次穿G3、G4。两缆尚未卷收且无损伤。',
                event='cable_guide_initial',routes=routes)
    other_ring = '3' if other == 'Q1' else '1'
    all_events = [(at,target,code) for at,code in events]
    all_events += [(5,other,'+'+other_ring),(14,other,'-'+other_ring),(24,other,'P:+'+other_ring)]
    for at,cable,code in sorted(all_events):
        status,operation = code.split(':',1) if ':' in code else ('success',code)
        ring,thread = 'G'+operation[1],operation[0] == '+'
        verb = '穿入' if thread else '撤出'
        if status == 'P':
            history.add(at,f'{cable}{verb}{ring}只是未来计划，尚未执行，现有穿引不变。',event='cable_guide_plan',
                        cable=cable,ring=ring,planned_action='thread' if thread else 'unthread',executed=False)
        elif status == 'F':
            if thread:
                if ring in routes[cable]:
                    raise ValueError('Reviewed failed threading must not have passed through the guide')
                text,reason = '导向对准未完成，自由端尚未穿入该环，原穿引全部保留且未损伤','alignment_not_completed'
            elif routes[cable][-1] != ring:
                if ring not in routes[cable]:
                    raise ValueError('Reviewed middle-guide refusal needs that actual guide')
                text,reason = '该环不是自由端末环，后续导环仍约束自由端，力限位触发；原穿引全部保留且未损伤','later_guides_block_release'
            else:
                text,reason = '撤出机构未完成动作，自由端仍穿在该环中，原穿引全部保留且未损伤','withdrawal_not_completed'
            history.add(at,f'{cable}尝试{verb}{ring}失败：{text}。',event='cable_guide_change',
                        cable=cable,ring=ring,thread=thread,success=False,unchanged=True,reason=reason)
        else:
            change_route(routes[cable],ring,thread)
            text = f'{ring}已成为新增的自由端侧末环' if thread else f'自由端已实际从{ring}撤出，解除该环穿引，其余先前穿引保留'
            history.add(at,f'{cable}{verb}{ring}'+('有诊断警告，但回执确认已完成：' if status == 'W' else '实际成功：')+text+'。',
                        event='cable_guide_change',cable=cable,ring=ring,thread=thread,success=True,warning=status == 'W')
    history.add(30,'巡检结束，探头已关闭采集，卷收驱动可用。',event='cable_withdrawal_ready')
    entries = []
    for cable in ('Q1','Q2'):
        entries += [{'description':f'{cable}撤出{ring}。','operation':{'kind':'unthread','cable':cable,'ring':ring}} for ring in ('G1','G2','G3','G4')]
        entries.append({'description':f'卷收{cable}。','operation':{'kind':'coil','cable':cable}})
    task = task_shell('FM-I1-O1',index)
    task.public = {'time_s':clock('09:00'),'max_steps':3,'target':target,'state_fields':[],
                  'instruction':f'请开始撤回探缆{target}，提交下一项操作。',
                  'actions':fixed_options(entries[rotation:]+entries[:rotation])}
    task.initial = {'time_s':clock('09:00'),'routes':routes,'coiled':{'Q1':False,'Q2':False},'overload_damage':{'Q1':False,'Q2':False}}
    task.world = {'routes':routes}
    task.rubric = {'score':'100 only for completing the specified cable next physical unthreading or empty-route coiling operation'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        cable = operation['cable']
        route = self.state['routes'][cable]
        completed = False
        if operation['kind'] == 'coil':
            if route:
                self.state['overload_damage'][cable] = True
                self.feedback = '仍有导环约束，卷收未完成并发生过载损伤。'
            else:
                self.state['coiled'][cable] = True
                completed = True
                self.feedback = '指定探缆已卷收。'
        elif operation['ring'] not in route:
            self.feedback = '指定导环未形成穿引，撤出未发生。'
        elif operation['ring'] != route[-1]:
            self.feedback = '自由端受后续导环约束，撤出未完成。'
        else:
            route.pop()
            completed = True
            self.feedback = '指定导环已撤出。'
        self.facts['operation_completed'] = completed
        return 100 if completed and cable == self.task.public['target'] else 0


def reconstruct(history,current):
    routes = {}
    for text in paragraphs(history):
        match = re.fullmatch(r'初始穿引按固定端到自由端：Q1依次穿(G[1-4](?:、G[1-4])*)；'
            r'Q2依次穿(G[1-4](?:、G[1-4])*)。两缆尚未卷收且无损伤。',text)
        if match:
            routes = {'Q1':match[1].split('、'),'Q2':match[2].split('、')}
            if any(len(set(route)) != len(route) for route in routes.values()):
                raise ValueError('A cable may pass through each guide only once')
            continue
        match = re.fullmatch(r'(Q[12])(穿入|撤出)(G[1-4])(?:有诊断警告，但回执确认已完成：|实际成功：)(.*)。',text)
        if match:
            cable,verb,ring,outcome = match.groups()
            thread = verb == '穿入'
            expected = f'{ring}已成为新增的自由端侧末环' if thread else f'自由端已实际从{ring}撤出，解除该环穿引，其余先前穿引保留'
            if outcome != expected:
                raise ValueError('Cable completion must describe the same actual guide operation')
            change_route(routes[cable],ring,thread)
            continue
        match = re.fullmatch(r'(Q[12])尝试(穿入|撤出)(G[1-4])失败：(.*)[，；]原穿引全部保留且未损伤。',text)
        if match:
            cable,verb,ring,reason = match.groups()
            route = routes[cable]
            valid = (
                verb == '穿入' and ring not in route and reason == '导向对准未完成，自由端尚未穿入该环' or
                verb == '撤出' and ring in route[:-1] and reason == '该环不是自由端末环，后续导环仍约束自由端，力限位触发' or
                verb == '撤出' and route and ring == route[-1] and reason == '撤出机构未完成动作，自由端仍穿在该环中')
            if not valid:
                raise ValueError('Failed cable receipt must preserve the stated physical guide constraint')
    if set(routes) != {'Q1','Q2'}:
        raise ValueError('Both cable paths must be initialized in the received history')
    return {'routes':routes}


def next_action(facts,current):
    cable = current['target']
    route = facts['routes'][cable]
    op = {'kind':'unthread','cable':cable,'ring':route[-1]} if route else {'kind':'coil','cable':cable}
    return decision_command(current,op)


def check_world(task,facts):
    if facts != task.world or facts['routes'] != task.initial['routes']:
        raise ValueError('Private cable paths must follow the received physical receipts in order')


def audit_cases(task,facts,solution):
    cable = task.public['target']
    route = facts['routes'][cable]
    correct = {'kind':'unthread','cable':cable,'ring':route[-1]} if route else {'kind':'coil','cable':cable}
    return decision_cases(task,solution,lambda op:100 if op == correct else 0)
