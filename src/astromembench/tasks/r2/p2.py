"""FM-R2-P2: retained static sampling decisions with nonlinear energy reserves."""
import re

from ...environment import SingleChoiceRuntime
from ..common import ArchiveHistory, clock, fixed_options, task_shell
from ..decisions import decision_cases, decision_command
from ..prose import paragraphs

COSTS = (0,5,11,18,26,35,45,54,66,80)
NAMES = {'C':'接收冷舱预冷','F':'样品封装','G':'样品入柜','T':'接收架消毒','V':'密封复验','X':'低优摄影'}
RETAINED_MENUS = {
    0:(8,0,1,6,9,5,7,2,3,4),1:(1,5,6,8,7,0,2,3,4,9),2:(5,3,1,2,6,4,7,0,9,8),
    6:(8,6,5,4,2,7,9,1,0,3),7:(9,2,8,0,4,1,6,5,7,3),8:(9,6,2,4,0,8,5,1,7,3),
    12:(5,9,3,1,8,2,6,7,4,0),13:(0,8,7,6,4,9,2,3,1,5),
}
NEW_MENU = (4,0,7,2,9,5,1,8,3,6)
# Explicit native rounds. Each tuple is (round, event, procedure, registration cost).
CONFIGS = (
    (42,((4,'register','C',16),(16,'register','F',12),(25,'register','X',10))),
    (95,((4,'register','C',24),(16,'register','F',16),(25,'register','X',10))),
    (45,((5,'register','C',14),(15,'complete','C',None),(24,'register','F',16))),
    (108,((5,'register','F',10),(18,'register','C',18),(27,'register','X',35))),
    (95,((7,'register','C',13),(20,'register','F',15),(29,'register','X',22))),
    (20,((4,'register','C',10),(14,'complete','C',None),(25,'register','F',17))),
    (44,((3,'register','C',18),(3,'register','F',12),(11,'register','G',6),(19,'register','X',16),(27,'pending_notice',None,None))),
    (72,((4,'register','C',20),(4,'register','F',14),(12,'complete','C',None),(20,'register','G',10),(27,'register','X',18))),
    (51,((3,'register','C',18),(3,'register','F',12),(12,'register','V',8),(20,'cancel','V',None),(27,'register','X',9))),
    (80,((3,'register','C',16),(7,'register','F',13),(12,'register','G',7),(16,'complete','C',None),(21,'register','V',6),(28,'draft','F',None))),
    (87,((4,'register','C',17),(9,'register','F',16),(13,'register','V',8),(18,'complete','C',None),(23,'register','G',5),(27,'cancel','V',None))),
    (35,((3,'register','C',14),(8,'register','G',6),(13,'register','F',19),(17,'complete','C',None),(22,'register','V',5),(29,'register','X',8))),
    (77,((3,'register','C',22),(3,'register','F',16),(9,'register','T',12),(15,'complete','T',None),(20,'register','V',10),(24,'cancel','V',None),(28,'register','X',24))),
    (34,((3,'register','C',18),(3,'register','F',12),(3,'register','G',6),(10,'complete','C',None),(17,'register','X',20),(24,'cancel','X',None),(28,'draft','F',None))),
    (90,((3,'register','C',18),(6,'register','T',7),(9,'register','F',17),(12,'register','G',6),(15,'register','V',11),(19,'complete','C',None),(22,'complete','T',None),(26,'cancel','V',None),(29,'draft','F',None))),
    (51,((3,'register','G',8),(6,'register','T',9),(9,'register','V',12),(12,'register','C',11),(16,'register','F',14),(20,'complete','T',None),(24,'cancel','V',None),(28,'plan','C',None))),
)


def required_energy(requirements,stage):
    return sum(r['energy'] for r in requirements.values() if r['stage'] == stage and r['required'] and r['status'] == 'pending')


def build(index):
    current_battery,events = CONFIGS[index]
    prices = {code:cost for _,kind,code,cost in events if kind == 'register'}
    battery = current_battery+sum(prices[code] for _,kind,code,_ in events if kind == 'complete')
    history = ArchiveHistory(clock('10:00'),spacing_s=120)
    history.add(1,'阶段Q7定点采样，档位0—9产出同数等价值样品组，费用为公开表列的非线性费用，暂存盒容量9组。'
        '保证所有尚未完成且未取消的必需保全供电后，尽量增加本次有效产出；挤占必需供电使成果无法验收。'
        '当前设备、质量和费用已确定，单位仅为题内简化电量，不是工程定额；无补能，移动、基础温控和平台消耗另行保障。'
        '样品先采入独立隔热暂存盒，保全结束前均稳定；档位不改变每项保全的固定费用。'
        'C接收冷舱预冷可提前完成并由基础温控维持，或采样后入柜前完成；T是接收架消毒，亦可提前完成并保持有效，'
        '不是当前直接接触样品的取样工具。F封装、G入柜属于采样后工序，不能在本批采样前宣称完成。'
        'V为独立密封复验或重复复查，各必需工序费用独立；同一工序的重复说明不形成第二项需求。X可选低优摄影可顺延。'
        '实际完成扣原登记费用且不再预留；正式取消只解除该项需求，不扣电；完成草稿、预填或计划均不执行也不解除需求。'
        '后续必需工序10:20—11:00由既定流程完成，无时间冲突；所有采样档位10:10前结束，不需主体追加执行保全。'
        '只选择一个档位，精确提交select与字符串option或end；合法、非法和end合计最多3次，格式错误不作预算分配，'
        '首个有效选择即不可撤销并结束，不能试选后改答。0档是明确提交零规模配置，end是退出。',
        event='sample_reserve_protocol',stage='Q7',costs=list(COSTS),yields=list(range(10)),capacity_groups=9,
        sampling_complete_before_s=clock('10:10'),preservation_window_s=[clock('10:20'),clock('11:00')])
    history.add(2,f'阶段Q7初始电量读数{battery}，后续实际完成的保全准备从此余额逐项扣除。',
        event='sample_reserve_initial',stage='Q7',battery=battery)
    requirements = {}
    for at,kind,code,cost in events:
        if kind == 'register':
            requirement = {'id':code,'title':NAMES[code],'stage':'Q7','energy':cost,'required':code != 'X'}
            requirements[code] = {**requirement,'status':'pending'}
            history.add(at,f'Q7工序{code}「{NAMES[code]}」登记为'+('必需，高于当前采样' if code != 'X' else '可选低优，可顺延')+f'，确定耗电{cost}。',
                event='sample_preservation_registered',**requirement)
        elif kind == 'complete':
            before = battery
            battery -= requirements[code]['energy']
            requirements[code]['status'] = 'completed'
            history.add(at,f'Q7工序{code}「{NAMES[code]}」已实际完成，准备持续有效；实际耗电{prices[code]}，余额由{before}变为{battery}。',
                event='sample_preservation_completed',stage='Q7',id=code,energy=prices[code],battery_before=before,battery_after=battery)
        elif kind == 'cancel':
            requirements[code]['status'] = 'cancelled'
            history.add(at,f'Q7工序{code}「{NAMES[code]}」正式取消，此前未执行，不再需要该项；未扣电。',
                event='sample_preservation_cancelled',stage='Q7',id=code)
        elif kind in ('draft','plan'):
            note = '工单完成栏只是预填草稿' if kind == 'draft' else '拟完成此工序，仅为计划'
            history.add(at,f'Q7工序{code}「{NAMES[code]}」{note}，实际尚未执行、未扣电。',
                event='sample_preservation_draft' if kind == 'draft' else 'sample_preservation_plan',stage='Q7',id=code,executed=False)
        else:
            history.add(at,'当前取样尚未开始，Q7的C预冷、F封装、G入柜三项必需工序均未执行。',
                event='sample_preservation_pending_notice',stage='Q7',ids=['C','F','G'],executed=False)
    order = RETAINED_MENUS.get(index,NEW_MENU)
    entries = [{'description':f'档位{j}：产出{j}组样品，耗电{COSTS[j]}','operation':{'level':j,'cost':COSTS[j],'yield':j}} for j in order]
    task = task_shell('FM-R2-P2',index,current_input_group=f'FM-R2-P2-{current_battery}-'+','.join(map(str,order)))
    task.public = {'instruction':'选择当前作业档位。','time_s':clock('10:00'),'stage':'Q7','battery':current_battery,
        'max_steps':3,'state_fields':[],'actions':fixed_options(entries)}
    task.initial = {}
    task.world = {'requirements':requirements,'battery':battery}
    task.rubric = {'score':'0 if chosen cost invades pending required preservation; otherwise 100*yield/maximum_safe_level; explicit level 0 earns 100 when maximum is 0'}
    return history.finish(task)


class Runtime(SingleChoiceRuntime):
    """Preserve the source Decision's static state, menu and neutral feedback."""
    def grade(self,option):
        operation = option['operation']
        reserve = required_energy(self.task.world['requirements'],self.task.public['stage'])
        available = self.task.world['battery']-reserve
        maximum = max(i for i,cost in enumerate(COSTS) if cost <= available)
        if operation['cost'] > available:
            return 0,False
        score = 100 if maximum == 0 else 100*operation['yield']/maximum
        return score,score == 100


def reconstruct(history,current):
    requirements,battery = {},None
    for text in paragraphs(history):
        initial = re.fullmatch(r'阶段(Q\d+)初始电量读数(\d+)，后续实际完成的保全准备从此余额逐项扣除。',text)
        if initial and initial[1] == current['stage']:
            battery = int(initial[2])
        registration = re.fullmatch(r'(Q\d+)工序([A-Z])「([^」]+)」登记为(必需，高于当前采样|可选低优，可顺延)，确定耗电(\d+)。',text)
        if registration:
            stage,identifier,title,kind,energy = registration.groups()
            requirements[identifier] = {'id':identifier,'title':title,'stage':stage,'energy':int(energy),
                'required':kind == '必需，高于当前采样','status':'pending'}
        completed = re.fullmatch(r'(Q\d+)工序([A-Z])「([^」]+)」已实际完成，准备持续有效；实际耗电(\d+)，余额由(\d+)变为(\d+)。',text)
        cancelled = re.fullmatch(r'(Q\d+)工序([A-Z])「([^」]+)」正式取消，此前未执行，不再需要该项；未扣电。',text)
        status = completed or cancelled
        if status:
            stage,identifier,title = status.groups()[:3]
            requirement = requirements[identifier]
            if requirement['stage'] != stage or requirement['title'] != title:
                raise ValueError('Preservation records must refer to the registered sampling stage')
            if completed:
                if int(completed[5]) != battery or int(completed[4]) != requirement['energy']:
                    raise ValueError('Actual preparation must debit its own registered cost')
                battery -= requirement['energy']
                if int(completed[6]) != battery:
                    raise ValueError('Preparation receipts must preserve the continuous energy ledger')
                requirement['status'] = 'completed'
            else:
                requirement['status'] = 'cancelled'
    if battery != current['battery']:
        raise ValueError('Current sampling battery must reflect actual completed preparations')
    reserve = required_energy(requirements,current['stage'])
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['cost'] <= battery-reserve]
    return {'requirements':requirements,'battery':battery,'reserve':reserve,'available':battery-reserve,
        'maximum_level':max(op['level'] for op in safe),'safe_operations':safe}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['yield']))


def check_world(task,facts):
    if facts['requirements'] != task.world['requirements'] or facts['battery'] != task.world['battery']:
        raise ValueError('Sampling reserves must exclude completed or cancelled work, but not drafts or plans')


def audit_cases(task,facts,solution):
    def score(operation):
        if operation not in facts['safe_operations']:
            return 0
        return 100 if facts['maximum_level'] == 0 else 100*operation['yield']/facts['maximum_level']
    return decision_cases(task,solution,score)
