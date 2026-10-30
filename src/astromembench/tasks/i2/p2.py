"""FM-I2-P2: cumulative fixed-bore depth, with the original request-scoring contract."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import decision_cases, decision_command
from ...environment import SingleChoiceRuntime
from ..prose import paragraphs

PAIRS = (('A',9),('C',11),('B',8),('A',13),('B',12),('C',12),('A',15),('B',12))
ACTUAL = ((3,3,3),(1,1,1),(4,3,4),(1,1,1),(3,3),(2,2),
          (3,4,2,4),(2,1,2,1),(2,3,2,3),(2,1,2,3),(3,2,3,3),(1,2,1,3),
          (3,3,3,0,3,3),(1,2,1,0,1,1),(2,2,3,0,2,2),(2,1,3,0,2,1))
MENUS = ((5,4,7,3,0,8,2,6,1,9),(8,4,6,2,0,9,1,7,5,3),
         (8,9,0,3,1,4,6,7,2,5),(1,9,0,7,2,4,8,5,6,3),
         (2,1,3,4,8,5,6,0,9,7),(8,9,3,4,0,7,2,1,6,5),
         (3,8,7,5,4,1,6,0,9,2),(9,6,2,8,0,3,1,7,4,5))


def build(index):
    target,limit = PAIRS[index//2]
    u,v = ['ABC'[('ABC'.index(target)+offset)%3] for offset in (1,2)]
    limits = {point:{target:limit,u:10,v:14}[point] for point in 'ABC'}
    cumulative = dict.fromkeys('ABC',0)
    history = History()
    history.add(1,'A、B、C各对应一个固定孔位，整段任务不换孔，孔深初始均为0，各自累计上限固定。'
        '真实回执的实际新增孔道深度才累计；每条实际量是该次新增，不是累计读数。'
        '计划不改变孔深，部分执行或失败按明确实际量。钻具回撤或重新就位不消除已形成孔道，也不增加孔深。'
        '目标是在不超本孔上限的条件下尽量完成许可采样深度；本题单位为标定深度单位。'
        '当前设备正常，每档操作保证实际追加对应单位；0档是不新增钻进的有效选择。'
        '所有0—9档始终可选，合法超深操作不会作为格式错误退回。'
        '按菜单提交select和字符串option或end，最多3次总调用，包括格式错误和最终合法选择；首次合法选择后即结束，不能重答。'
        '额外字段、数值型编号或范围外编号无效；无免费查询累计量接口。',event='fixed_bore_protocol')
    history.add(2,'三个固定孔位的累计上限：'+ '；'.join(f'{point}为{limits[point]}单位' for point in 'ABC')+'。各孔初始孔深均0。',
                event='bore_limits',limits=limits,initial_depths=cumulative)
    rounds = {2:(4,16),3:(4,9,21),4:(4,9,16,21),6:(4,9,16,19,21,26)}[len(ACTUAL[index])]
    receipts = [(7,u,3,3),(14,v,4,4),(24,u,2,2)]
    for ordinal,(at,actual) in enumerate(zip(rounds,ACTUAL[index],strict=True)):
        requested = actual+1 if index >= 12 and ordinal == 0 else 1 if index >= 12 and ordinal == 3 else actual
        receipts.append((at,target,requested,actual))
    for at,point,requested,actual in sorted(receipts):
        if not 0 <= actual <= requested <= limits[point]-cumulative[point]:
            raise ValueError('Historical drilling requests must fit the remaining permitted depth')
        cumulative[point] += actual
        detail = '提前结束，未完成的请求量不计入孔深。' if actual and actual < requested else '未产生进给。' if actual == 0 else '已完成。'
        history.add(at,f'采样点{point}请求新增{requested}单位，实际新增孔道深度{actual}单位；{detail}',
                    event='bore_receipt',point=point,requested_increment=requested,actual_increment=actual)
    if index >= 6:
        history.add(12,f'候选计划：以后在{target}孔新增5单位；尚未执行，本条没有形成新孔道。',
                    event='bore_plan',point=target,planned_increment=5,executed=False)
    history.add(30,f'钻具已在采样点{target}就位，设备可正常作业。',event='drill_ready',point=target)
    group = f'FM-I2-P2-pair-{index//2+1:02d}'
    task = task_shell('FM-I2-P2',index,group=group,current_input_group=group,background_group=group)
    entries = [{'description':f'本轮追加{n}个单位' if n else '本轮不新增钻进',
                'operation':{'action':'drill','point':target,'increment':n}} for n in MENUS[index//2]]
    task.public = {'instruction':f'钻具已在采样点{target}就位，设备可正常作业。请继续开展采样，提交本轮追加档位。',
                   'point':target,'time_s':clock('09:00'),'max_steps':3,'actions':fixed_options(entries)}
    task.initial = {}
    task.world = {'remaining':limit-cumulative[target],'limits':limits,'cumulative':cumulative}
    task.rubric = {'score':'0 if a>r else 100*a/r if r>0 else 100','full_credit':'a == r'}
    return history.finish(task)


class Runtime(SingleChoiceRuntime):
    def grade(self,option):
        actual = option['operation']['increment']
        remaining = self.task.world['remaining']
        score = 0 if actual > remaining else 100*actual/remaining if remaining else 100
        self.facts.update(remaining_before=remaining,actual_increment=actual,exceeded_limit=actual > remaining)
        return score, actual == remaining


def reconstruct(history,current):
    limits,cumulative = {},{}
    for text in paragraphs(history):
        initial = re.fullmatch(r'三个固定孔位的累计上限：(.*?)。各孔初始孔深均(\d+)。', text)
        receipt = re.match(r'采样点([ABC])请求新增(\d+)单位，实际新增孔道深度(\d+)单位；', text)
        plan = re.fullmatch(r'候选计划：以后在([ABC])孔新增(\d+)单位；尚未执行，本条没有形成新孔道。', text)
        if initial:
            limits = {point:int(value) for point,value in re.findall(r'([ABC])为(\d+)单位', initial[1])}
            cumulative = dict.fromkeys(limits,int(initial[2]))
        elif receipt:
            point,requested,actual = receipt[1],int(receipt[2]),int(receipt[3])
            if not 0 <= actual <= requested <= limits[point]-cumulative[point]:
                raise ValueError('The fixed bore history must contain feasible requests and actual receipts')
            cumulative[point] += actual
        elif plan and int(plan[2]) > limits[plan[1]]-cumulative[plan[1]]:
            raise ValueError('The unexecuted candidate must fit the permitted depth when proposed')
    if set(limits) != set('ABC') or set(cumulative) != set('ABC'):
        raise ValueError('All fixed bore identities need initial depths and limits')
    return {'remaining':limits[current['point']]-cumulative[current['point']],'limits':limits,'cumulative':cumulative}


def next_action(facts,current):
    return decision_command(current,{'action':'drill','point':current['point'],'increment':facts['remaining']})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Remaining depth must come from all actual receipts of the same fixed bore')


def audit_cases(task,facts,solution):
    def score(operation):
        actual,remaining = operation['increment'],facts['remaining']
        return 0 if actual > remaining else 100*actual/remaining if remaining else 100
    return decision_cases(task,solution,score)
