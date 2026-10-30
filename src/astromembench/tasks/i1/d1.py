"""FM-I1-D1: isolate all parallel flow paths while preserving the other unit."""
from copy import deepcopy
from itertools import combinations
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

INITIAL = {'V1':'A','V2':'A','V3':'B','V4':'B'}
CONFIGS = (
    ('A',3,((8,'2B'),(26,'P:1B'))),
    ('B',7,((8,'3A'),(26,'P:4A'))),
    ('A',5,((7,'1B'),(18,'3A'),(27,'P:2B'))),
    ('B',4,((7,'1B'),(18,'3A'),(27,'P:4A'))),
    ('A',9,((6,'1B'),(13,'2B'),(22,'4A'),(28,'P:3A'))),
    ('B',3,((6,'3A'),(13,'4A'),(22,'2B'),(28,'P:1B'))),
    ('A',6,((4,'1B'),(10,'3A'),(18,'1A'),(26,'2B'))),
    ('B',0,((4,'4A'),(10,'2B'),(18,'4B'),(26,'3A'))),
    ('A',4,((4,'1B'),(9,'3A'),(15,'2B'),(21,'3B'),(28,'4A'))),
    ('B',5,((4,'4A'),(9,'2B'),(15,'3A'),(21,'2A'),(28,'1B'))),
    ('A',0,((4,'2B'),(10,'4A'),(18,'3A'),(26,'4B'))),
    ('B',8,((4,'4A'),(10,'2B'),(18,'1B'),(26,'2A'))),
    ('A',5,((6,'F:2B'),(17,'2B'),(27,'P:1B'))),
    ('A',9,((5,'W:2B'),(14,'4A'),(25,'F:1B'))),
    ('B',2,((5,'W:3A'),(14,'1B'),(25,'F:4A'))),
    ('B',0,((4,'3A'),(9,'4A'),(15,'F:1B'),(21,'1B'),(28,'2B'))),
)


def target_branches(outlets,target):
    return sorted(branch for branch,unit in outlets.items() if unit == target)


def build(index):
    target,rotation,events = CONFIGS[index]
    outlets = deepcopy(INITIAL)
    history = History()
    history.add(1,'巡航换热单元A/B介质兼容。独立支路V1—V4各从共同泵源出发，带开关阀和两位置实体选择器，出口只连A或B之一。'
        '回流已内置隔离，不另考回流模型；阀开才向实际出口单元供流。多路并联时只要仍有一路打开，单元就未隔离。'
        '隔离指定单元须关闭所有仍通向它的支路，同时让另一单元的全部支路保持原样。'
        '历史移位由局部暂闭—选择器移位—恢复开启的低层机构执行，缓冲热控保障切换过程；成功给实际新出口，失败保留旧出口并恢复阀开。'
        '计划不改变出口，警告以实际物理回执为准。当前设备正常、四阀均开，两单元均获供流，不考温度、热力学或累计消耗。'
        '本次仅闭单阀或双阀，不移动选择器。所有10项完整可选，不按真实管路过滤。'
        '按select和字符串option提交，或end放弃；总计最多3次含格式错误，首个有效选择闭阀后立即终止，无重开或重选。'
        '格式错误只占额度、不动阀，额外字段、数值型或范围外编号无效。',event='parallel_cooling_protocol')
    history.add(2,'初始V1/V2出口连A，V3/V4出口连B，四个开关阀均开启。',event='cooling_initial',outlets=outlets,valves_open=True)
    for at,code in events:
        status,move = code.split(':',1) if ':' in code else ('success',code)
        branch,destination = 'V'+move[0],move[1]
        if status == 'P':
            history.add(at,f'拟将{branch}的实体选择器出口移至{destination}，仅为计划，尚未执行，出口和开关阀不变。',
                event='cooling_plan',branch=branch,requested_outlet=destination,executed=False)
            continue
        origin = outlets[branch]
        success = status != 'F'
        if success:
            outlets[branch] = destination
        text = (f'警告但实际已由{origin}移至{destination}' if status == 'W' else
                f'成功由{origin}移至{destination}' if success else f'移向{destination}未到位，实际仍保持原出口{origin}')
        history.add(at,f'{branch}实体选择器{text}；局部切换程序结束，本阀恢复开启。',event='cooling_selector',
            branch=branch,previous_outlet=origin,requested_outlet=destination,actual_outlet=outlets[branch],
            success=success,warning=status == 'W',valve_open=True)
    history.add(30,'巡航热控阀V1—V4均开启，局部切换结束，机构正常。',event='cooling_ready',open_valves=['V1','V2','V3','V4'])
    branches = ('V1','V2','V3','V4')
    programs = [(branch,) for branch in branches]+list(combinations(branches,2))
    entries = [{'description':'闭合'+'+'.join(chosen)+'。','operation':{'kind':'close','valves':list(chosen)}} for chosen in programs]
    if len(target_branches(outlets,target)) not in (1,2) or set(outlets.values()) != {'A','B'}:
        raise ValueError('Reviewed isolation needs one or two target paths and preserves another supplied unit')
    task = task_shell('FM-I1-D1',index)
    task.public = {'time_s':clock('09:00'),'target':target,'max_steps':3,'state_fields':[],
        'instruction':f'请隔离换热单元{target}，保持另一单元的所有供流支路原样。',
        'actions':fixed_options(entries[rotation:]+entries[:rotation])}
    task.initial = {'time_s':clock('09:00'),'outlets':outlets,'valves_open':{branch:True for branch in branches}}
    task.world = {'outlets':outlets}
    task.rubric = {'score':'100 only for full physical isolation of the target with all other-unit branches still open; no partial credit'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        for branch in operation['valves']:
            self.state['valves_open'][branch] = False
        target = self.task.public['target']
        fulfilled = all(self.state['valves_open'][branch] == (unit != target) for branch,unit in self.state['outlets'].items())
        self.feedback = '所选阀已闭合，回执已归档。'
        return 100 if fulfilled else 0


def reconstruct(history,current):
    outlets = {}
    for text in paragraphs(history):
        match = re.fullmatch(r'初始(V[1-4])/(V[1-4])出口连([AB])，(V[1-4])/(V[1-4])出口连([AB])，四个开关阀均开启。',text)
        if match:
            first,second,a,third,fourth,b = match.groups()
            outlets = {first:a,second:a,third:b,fourth:b}
            continue
        match = re.fullmatch(r'(V[1-4])实体选择器(?:警告但实际已由|成功由)([AB])移至([AB])；'
            r'局部切换程序结束，本阀恢复开启。',text)
        if match:
            branch,origin,destination = match.groups()
            if outlets[branch] != origin:
                raise ValueError('Selector receipt must preserve actual before/after outlets and reopen its branch')
            outlets[branch] = destination
            continue
        match = re.fullmatch(r'(V[1-4])实体选择器移向[AB]未到位，实际仍保持原出口([AB])；'
            r'局部切换程序结束，本阀恢复开启。',text)
        if match:
            if outlets[match[1]] != match[2]:
                raise ValueError('Selector receipt must preserve actual before/after outlets and reopen its branch')
            continue
        match = re.fullmatch(r'巡航热控阀([^，]+)均开启，局部切换结束，机构正常。',text)
        if match:
            if match[1] != 'V1—V4':
                raise ValueError('Current isolation starts with all four branches open')
    if set(outlets) != {'V1','V2','V3','V4'}:
        raise ValueError('All four physical branch outlets need initial evidence')
    return {'outlets':outlets}


def next_action(facts,current):
    return decision_command(current,{'kind':'close','valves':target_branches(facts['outlets'],current['target'])})


def check_world(task,facts):
    if facts != task.world or facts['outlets'] != task.initial['outlets'] or not all(task.initial['valves_open'].values()):
        raise ValueError('Current physical flow graph must follow the public selector receipts')


def audit_cases(task,facts,solution):
    needed = target_branches(facts['outlets'],task.public['target'])
    return decision_cases(task,solution,lambda op:100 if op['valves'] == needed else 0)
