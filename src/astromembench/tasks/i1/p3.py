"""FM-I1-P3: release the target carriage's actual incident drawbars."""
from copy import deepcopy
from itertools import combinations
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

INITIAL = {'1':['A','B'],'2':['B','C'],'3':['C','D'],'4':['D','E']}
CONFIGS = (
    ('C',4,((8,'D2'),(25,'P:C2BC'))),
    ('C',1,((8,'D2'),(17,'D3'),(26,'P:C3CD'))),
    ('A',10,((8,'D2'),(17,'C2AC'),(26,'P:D1'))),
    ('E',0,((8,'D1'),(17,'C1AE'),(26,'P:D4'))),
    ('A',6,((8,'D3'),(17,'C3AD'),(26,'P:C3CD'))),
    ('D',2,((8,'D3'),(17,'C3AD'),(26,'P:D3'))),
    ('E',2,((5,'D2'),(10,'D4'),(17,'C2BE'),(24,'C4EC'))),
    ('C',8,((5,'D2'),(10,'D4'),(17,'C2BE'),(24,'C4EC'))),
    ('A',6,((5,'D1'),(10,'D3'),(17,'C1AC'),(24,'C3BE'))),
    ('D',1,((5,'D2'),(10,'D3'),(17,'C2BD'),(24,'C3CE'))),
    ('B',9,((5,'D1'),(11,'C1AE'),(18,'D2'),(25,'P:C2BC'))),
    ('A',5,((5,'D2'),(11,'C2AC'),(18,'D1'),(25,'P:C1AB'))),
    ('B',1,((5,'F:D2'),(14,'P:C2AE'),(25,'P:D1'))),
    ('D',4,((4,'D3'),(9,'F:C3AD'),(16,'C3AD'),(24,'F:D4'))),
    ('C',0,((4,'D2'),(9,'D3'),(16,'F:C2AC'),(24,'P:C3CE'))),
    ('D',2,((4,'D2'),(9,'D3'),(15,'C2BD'),(21,'F:C3CE'),(27,'C3CE'))),
)


def validate_chains(drawbars):
    adjacency = {carriage:set() for carriage in 'ABCDE'}
    components = {carriage:carriage for carriage in 'ABCDE'}
    for endpoints in drawbars.values():
        if endpoints is None:
            continue
        a,b = endpoints
        if a not in adjacency or b not in adjacency or a == b or components[a] == components[b]:
            raise ValueError('Installed drawbars must connect different carriages without forming a cycle')
        adjacency[a].add(b)
        adjacency[b].add(a)
        if len(adjacency[a]) > 2 or len(adjacency[b]) > 2:
            raise ValueError('Each carriage has only two drawbar interfaces')
        old,new = components[b],components[a]
        components = {node:new if group == old else group for node,group in components.items()}


def incident(drawbars,target):
    return {rod for rod,endpoints in drawbars.items() if endpoints is not None and target in endpoints}


def release_score(drawbars,target,operation):
    before = incident(drawbars,target)
    if operation['kind'] == 'park':
        return 0 if before else 100
    released = {rod for rod in operation['rods'] if drawbars[rod] is not None}
    return 100*len(released)/len(before) if before and released <= before else 0


def build(index):
    target,rotation,events = CONFIGS[index]
    history = History()
    drawbars = deepcopy(INITIAL)
    history.add(1,'车厢A/B/C/D/E各有两个等价牵引接口，每口接一根杆；杆1/2/3/4各连两个不同车厢或完全卸下停在工具架。'
        '挂接图始终是无环的若干链，每车不超过两杆。成功卸杆解除其两个端点；成功安装回执确认杆空闲、两端接口空闲且不闭环。'
        '失败按回执保留原连接或仍在工具架；未执行计划不拆装。当前分离并留置指定车，须释放其全部相邻杆、保留其他杆；'
        '若该车本来无杆，只施加它的驻车制动。解除后由公共固定承托保持静止，本阶段无须再驻车，操作前各车均未制动。'
        '单杆/双杆释放由预置夹具独立执行，双杆同步解除；请求中实际已装杆均被卸至工具架，本已卸杆保持不动。'
        '误释放无关车的杆也会实际改变挂接，不能撤销；驻车只制动指定车，不拆杆。'
        '车辆停稳、动力隔离、载荷稳定，工具与操作区已准备，不考路线、能源或累计运量。'
        '全部11项每题可选；按select和字符串option提交，或end放弃。有效/无效/end总计最多3次，首个有效选择立即执行并终止，不能补选。'
        '格式错误不动杆，只占同一额度；不接受额外字段、数值型或范围外编号。',event='drawbar_protocol')
    history.add(2,'初始挂接：杆1连接A—B，杆2连接B—C，杆3连接C—D，杆4连接D—E。',event='drawbar_initial',drawbars=drawbars)
    for at,code in events:
        status,operation = code.split(':',1) if ':' in code else ('success',code)
        rod,install = operation[1],operation[0] == 'C'
        endpoints = list(operation[2:]) if install else deepcopy(drawbars[rod])
        if status == 'P':
            plan = {'kind':'install' if install else 'release','rod':rod}
            if install:
                plan['endpoints'] = endpoints
            text = f'把杆{rod}安装至{endpoints[0]}—{endpoints[1]}' if install else f'卸下杆{rod}'
            history.add(at,text+'的方案只是计划，尚未执行，所有挂接均未改变。',event='drawbar_plan',planned_operation=plan,executed=False)
            continue
        if install and drawbars[rod] is not None or not install and drawbars[rod] is None:
            raise ValueError('Install requires a racked rod; release requires an installed rod')
        if status == 'F':
            if install:
                history.add(at,f'尝试把杆{rod}安装到{endpoints[0]}—{endpoints[1]}失败，锁扣未锁合。杆{rod}仍在工具架，双方没有建立这根杆的连接，其他连接均不变。',
                    event='drawbar_install',rod=rod,endpoints=endpoints,success=False,actual_endpoints=None,reason='latch_not_engaged')
            else:
                history.add(at,f'杆{rod}卸下尝试失败，锁扣未松开，杆仍连接{endpoints[0]}—{endpoints[1]}，没有解除任何一端，其他连接均不变。',
                    event='drawbar_release',rod=rod,success=False,actual_endpoints=endpoints,reason='latch_not_released')
        elif install:
            drawbars[rod] = endpoints
            validate_chains(drawbars)
            history.add(at,f'杆{rod}实际安装成功，连接{endpoints[0]}—{endpoints[1]}；回执确认安装前两个接口空闲且本次未闭合成环，现两端已锁紧。',
                event='drawbar_install',rod=rod,endpoints=endpoints,success=True,interfaces_free_before=True,acyclic=True)
        else:
            drawbars[rod] = None
            history.add(at,f'杆{rod}实际卸下成功，已解除{endpoints[0]}—{endpoints[1]}两个端点，杆移至工具架，两端接口已释放。',
                event='drawbar_release',rod=rod,previous_endpoints=endpoints,success=True,actual_endpoints=None)
    history.add(30,'车辆保持静止、牵引动力已隔离，公共固定承托、操作区及工具均已就绪。',event='drawbar_work_ready')
    releases = [(rod,) for rod in '1234']+list(combinations('1234',2))
    entries = [{'operation':{'kind':'release','rods':list(rods)},'description':'释放牵引杆'+'+'.join(rods)+'。'} for rods in releases]
    entries.append({'operation':{'kind':'park'},'description':'给当前指定车厢施加驻车制动。'})
    task = task_shell('FM-I1-P3',index)
    task.public = {'time_s':clock('09:00'),'max_steps':3,'target':target,'state_fields':[],
        'instruction':f'请执行分离并留置车厢{target}的本阶段操作，保留其他车厢的挂接。',
        'actions':fixed_options(entries[rotation:]+entries[:rotation])}
    task.initial = {'time_s':clock('09:00'),'drawbars':drawbars,'parked':{carriage:False for carriage in 'ABCDE'}}
    task.world = {'drawbars':drawbars}
    task.rubric = {'score':'100 times the fraction of incident rods actually released; releasing an unrelated installed rod makes zero; already racked rods remain unchanged; an initially isolated target requires parking'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        drawbars,target = self.state['drawbars'],self.task.public['target']
        score = release_score(drawbars,target,operation)
        if operation['kind'] == 'park':
            self.state['parked'][target] = True
            self.feedback = '指定车厢驻车制动已执行。'
        else:
            self.facts['released_rods'] = [rod for rod in operation['rods'] if drawbars[rod] is not None]
            for rod in operation['rods']:
                drawbars[rod] = None
            self.feedback = '所选牵引杆释放请求已执行，回执已归档。'
        return score


def reconstruct(history,current):
    drawbars = {}
    for text in paragraphs(history):
        match = re.fullmatch(r'初始挂接：(.*)。',text)
        if match:
            drawbars = {}
            for entry in match[1].split('，'):
                endpoints = re.fullmatch(r'杆([1-4])连接([A-E])—([A-E])',entry)
                if endpoints is None or endpoints[1] in drawbars:
                    raise ValueError('Initial drawbars must each identify their own endpoints')
                drawbars[endpoints[1]] = [endpoints[2],endpoints[3]]
            validate_chains(drawbars)
            continue
        match = re.fullmatch(r'杆([1-4])实际安装成功，连接([A-E])—([A-E])；'
            r'回执确认安装前两个接口空闲且本次未闭合成环，现两端已锁紧。',text)
        if match:
            rod,a,b = match.groups()
            if drawbars[rod] is not None:
                raise ValueError('Successful installation requires a racked rod and free chain ends')
            drawbars[rod] = [a,b]
            validate_chains(drawbars)
            continue
        match = re.fullmatch(r'杆([1-4])实际卸下成功，已解除([A-E])—([A-E])两个端点，杆移至工具架，两端接口已释放。',text)
        if match:
            rod,a,b = match.groups()
            if drawbars[rod] != [a,b]:
                raise ValueError('Successful release must detach both previous endpoints')
            drawbars[rod] = None
            validate_chains(drawbars)
            continue
        match = re.fullmatch(r'尝试把杆([1-4])安装到[A-E]—[A-E]失败，锁扣未锁合。'
            r'杆([1-4])仍在工具架，双方没有建立这根杆的连接，其他连接均不变。',text)
        if match:
            if match[1] != match[2] or drawbars[match[1]] is not None:
                raise ValueError('Failed drawbar operation cannot change its physical endpoints')
            continue
        match = re.fullmatch(r'杆([1-4])卸下尝试失败，锁扣未松开，杆仍连接([A-E])—([A-E])，'
            r'没有解除任何一端，其他连接均不变。',text)
        if match and drawbars[match[1]] != [match[2],match[3]]:
            raise ValueError('Failed drawbar operation cannot change its physical endpoints')
    if set(drawbars) != set('1234'):
        raise ValueError('The received history must identify all four drawbars')
    return {'drawbars':drawbars}


def next_action(facts,current):
    rods = sorted(incident(facts['drawbars'],current['target']))
    return decision_command(current,{'kind':'release','rods':rods} if rods else {'kind':'park'})


def check_world(task,facts):
    if facts != task.world or facts['drawbars'] != task.initial['drawbars']:
        raise ValueError('Private drawbar graph differs from actual public installation and release receipts')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:release_score(facts['drawbars'],task.public['target'],op))
