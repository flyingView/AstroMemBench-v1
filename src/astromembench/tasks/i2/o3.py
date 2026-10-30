"""FM-I2-O3: retained supply receipts, net recovery, and closed material balance."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import decision_cases, decision_command
from ...environment import SingleChoiceRuntime
from ...schema import story_timestamp
from ..prose import paragraphs

CONFIGS = (
    ('B',42,48,None),('B',42,48,None),('C',36,42,None),
    ('A',39,45,(12,9)),('A',48,54,(9,12)),('B',30,36,(12,15)),
    ('A',54,60,None),('A',42,48,(18,12,-6,9)),('A',48,54,(18,-9,9,6)),
    ('C',36,42,(12,12,-6,18)),('A',45,51,(18,-6,15,15)),('C',30,36,(12,9,-6,3)),
    ('C',63,69,None),('B',57,63,(18,-9,12,0,9,3)),
    ('A',45,51,(15,-6,9,0,12,15)),('C',51,57,(15,-6,12,0,9,9)),
)
PRESERVED_MENUS = {
    0:(0,9,27,21,24,6,15,12,3,18),1:(3,21,24,6,18,9,12,27,0,15),
    2:(6,27,3,0,18,12,21,15,24,9),6:(9,6,21,18,24,27,15,12,0,3),
    12:(6,9,12,21,24,3,27,15,18,0),
}
NEW_MENU = (15,3,24,0,18,9,27,6,21,12)
# These are direct native round numbers from the FM, not a history conversion.
PRESERVED_RECEIPTS = {
    0:((5,'T',18,15,'提前停止，只注入所报实际量。'),(15,'A',12,12,''),(24,'T',12,12,'泵已停，未排出液体。')),
    1:((5,'T',18,18,''),(15,'A',12,12,''),(24,'T',18,18,'注入完成。')),
    2:((4,'T',15,15,''),(14,'T',12,12,''),(24,'T',9,9,'暂停泵送等待下一操作，未排出液体。')),
    6:((3,'T',18,15,'提前停止，只完成所报实际量。'),(10,'C',9,9,''),(22,'T',9,9,''),
       (27,'T',9,9,'暂停后再启动并完成本次注入，暂停没有排出液体。')),
    12:((3,'T',18,15,'提前停止，只完成所报实际量。'),(8,'A',12,12,''),(13,'T',6,0,'联锁拒绝，未注入。'),
        (18,'T',18,15,'只完成所报实际量。'),(27,'T',9,9,'这是单独下发的新操作；此前候选计划未执行，不额外贡献液量。')),
}


def transfer(volumes,capacities,part,direction,requested,actual):
    if not 0 <= actual <= requested:
        raise ValueError('Actual transferred amount cannot exceed its request')
    if direction == 'inject':
        if volumes[part]+requested > capacities[part]:
            raise ValueError('Historical injection requests must fit the receiving tank')
        volumes[part] += actual
    elif direction == 'recover':
        if requested > volumes[part]:
            raise ValueError('Historical withdrawal requires sufficient retained liquid')
        volumes[part] -= actual
    else:
        raise ValueError('Transfer direction must be an explicit injection or recovery')


def supply_score(total,goal,capacity,increment):
    remaining = goal-total
    if total+increment > capacity:
        return 0.0
    if remaining == 0:
        return 100.0 if increment == 0 else 0.0
    return 100*remaining/increment if increment > remaining else 100*increment/remaining


def build(index):
    target,goal,capacity,sequence = CONFIGS[index]
    preserved = sequence is None
    goals = {part:goal if part == target else 60 for part in 'ABC'}
    capacities = {part:capacity if part == target else 66 for part in 'ABC'}
    volumes = dict.fromkeys('ABC',0)
    source_remaining,recovery = 200,0
    history = History(times=[clock('09:00:59')+120*i for i in range(30)])
    timing = '' if preserved else '当前正档准确按1单位/秒转移，零档关闭用1秒；操作完成后关阀。'
    history.add(1,'A/B/C接收罐相互独立，初始均空，阀路正确连接且设备正常，各罐目标量和容量固定。'
        '只累计本罐实际注入，减去明确回执的实际回抽。请求、候选计划、停泵和重新就位均不改变液量；'
        '静止期间无蒸发或泄漏，恢复泵送不表示曾回抽。回抽流入ABC以外的独立密闭回收罐，不并入其他罐或当前产出，不再复用。'
        '目标是在容量内达到目标量，超过目标没有额外成果且浪费；已到目标应关闭。'
        '当前仅一次准确注入，十档0/3/6/9/12/15/18/21/24/27单位，0为关闭不再注入。'
        '历史供给源可用200单位，当前另行配给27单位；回收罐和不可回用溢流收集器容量各100单位。'
        '供给源实际输出完整所选量，超容时接收罐仅留至容量，多余全部进入溢流收集器，整次补给不合格且不能撤销。'
        '无免费液位读数、当前累计查询、准备调用或当前回抽接口。'+timing+
        '按菜单提交select与字符串option，或end。总调用最多3次含格式错误和最终合法选择；额外字段、数值型或范围外编号无效。'
        '首次合法选择后结束，超容量与浪费也是合法终局，不能重选。',event='supply_protocol',
        history_source_units=200,current_source_units=27,recovery_capacity=100,overflow_capacity=100)
    history.add(2,'三接收罐初始均空；'+ '；'.join(f'{part}目标{goals[part]}、容量{capacities[part]}' for part in 'ABC')+'，均使用本题标定单位。',
                event='supply_initial',goals=goals,capacities=capacities,volumes=volumes)
    plans = []
    if preserved:
        receipts = [(at,target if part == 'T' else part,'inject',q,a,note) for at,part,q,a,note in PRESERVED_RECEIPTS[index]]
        if index in (6,12):
            plans = [(16,12)] if index == 6 else [(22,9)]
    else:
        u,v = ['ABC'[('ABC'.index(target)+n)%3] for n in (1,2)]
        rounds = (4,20) if index < 6 else (4,10,18,25) if index < 12 else (3,8,13,17,23,27)
        receipts = [(7,u,'inject',6,6,''),(22,v,'inject',9,9,'')]
        for ordinal,(at,amount) in enumerate(zip(rounds,sequence,strict=True)):
            actual = abs(amount)
            requested = actual+3 if index >= 6 and ordinal == 0 else 3 if amount == 0 else actual
            note = '未开阀，实际0。' if amount == 0 else '提前结束，只有实际量完成转移。' if requested > actual else ''
            receipts.append((at,target,'recover' if amount < 0 else 'inject',requested,actual,note))
        plans = [(15,3)]
        history.add(26,f'{target}单元停泵并重新就位，无液体排出或新增注入。',event='supply_pause',part=target,liquid_moved=False)
        history.add(30,f'设备已在{target}就位，状态正常。',event='supply_ready',part=target)
    for at,part,direction,requested,actual,note in sorted(receipts):
        transfer(volumes,capacities,part,direction,requested,actual)
        if direction == 'inject':
            if requested > source_remaining:
                raise ValueError('Historical supply requests cannot reuse recovered liquid')
            source_remaining -= actual
            text = f'向{part}请求注入{requested}单位，实际注入{actual}单位。'
        else:
            recovery += actual
            if recovery > 100:
                raise ValueError('Recovery tank capacity cannot be exceeded')
            text = f'从{part}请求回抽{requested}单位，实际回抽{actual}单位，流入独立密闭回收罐。'
        history.add(at,text+note,event='supply_receipt',part=part,direction=direction,requested_units=requested,actual_units=actual)
    for at,amount in plans:
        history.add(at,f'候选计划：向{target}注入{amount}单位，尚未执行，没有转移液体。',
                    event='supply_plan',part=target,planned_units=amount,executed=False)
    entries = [{'description':f'本次注入{a}单位' if a else '关闭该单元，不再注入','operation':{'increment':a}}
               for a in PRESERVED_MENUS.get(index,NEW_MENU)]
    task = task_shell('FM-I2-O3',index)
    task.public = {'time_s':clock('10:00'),'max_steps':3,
                   'instruction':f'设备在{target}就位。请提交当前一次追加档位，0表示结束该单元。',
                   'target':target,'actions':fixed_options(entries)}
    task.initial = {} if preserved else {'time_s':clock('10:00'),'stored':volumes,'history_source_remaining':source_remaining,
        'recovery_units':recovery,'source_remaining':27,'overflow_units':0,'valve_closed':True,'transfer_completed':False,'transferred_units':0}
    task.world = {'target':target,'goal':goal,'capacity':capacity,'total':volumes[target],
                  'remaining':goal-volumes[target],'waste_penalty':True}
    task.rubric = ({'description':'修复按未超上限的有效追加比例；补给还区分目标/容量并扣除无用超注效率；已达目标时唯有零追加100。'} if preserved
                   else {'score':'0 for overflow; if already at goal only zero earns 100; otherwise 100*min(a/r,r/a), with zero addition scoring zero'})
    return history.finish(task)


class Runtime(SingleChoiceRuntime):
    def observation(self):
        result = super().observation()
        if 'time_s' in self.state:
            result.update(time_s=self.state['time_s'],current_time=story_timestamp(self.state['time_s']))
        return result

    def grade(self,option):
        increment = option['operation']['increment']
        world = self.task.world
        total = self.state['stored'][world['target']] if self.state else world['total']
        score = supply_score(total,world['goal'],world['capacity'],increment)
        if self.state:
            self.state['source_remaining'] -= increment
            self.state['stored'][world['target']] = min(world['capacity'],total+increment)
            self.state['overflow_units'] += max(0,total+increment-world['capacity'])
            self.state.update(time_s=self.state['time_s']+(increment or 1),valve_closed=True,
                              transfer_completed=True,transferred_units=increment)
        return score, score == 100


def reconstruct(history,current):
    goals,capacities,volumes = {},{},{}
    source_remaining,recovery = 200,0
    for text in paragraphs(history):
        initial = re.fullmatch(r'三接收罐初始均空；(.*?)，均使用本题标定单位。',text)
        injection = re.match(r'向([ABC])请求注入(\d+)单位，实际注入(\d+)单位。',text)
        withdrawal = re.match(r'从([ABC])请求回抽(\d+)单位，实际回抽(\d+)单位，流入独立密闭回收罐。',text)
        plan = re.fullmatch(r'候选计划：向([ABC])注入(\d+)单位，尚未执行，没有转移液体。',text)
        if initial:
            for part,goal,capacity in re.findall(r'([ABC])目标(\d+)、容量(\d+)',initial[1]):
                goals[part],capacities[part],volumes[part] = int(goal),int(capacity),0
        elif injection or withdrawal:
            receipt = injection or withdrawal
            part,requested,actual = receipt[1],int(receipt[2]),int(receipt[3])
            transfer(volumes,capacities,part,'inject' if injection else 'recover',requested,actual)
            if injection:
                if requested > source_remaining:
                    raise ValueError('Historical supply source lacks the requested amount')
                source_remaining -= actual
            else:
                recovery += actual
        elif plan and volumes[plan[1]]+int(plan[2]) > capacities[plan[1]]:
            raise ValueError('The unexecuted injection candidate must fit when proposed')
    if set(volumes) != set('ABC') or source_remaining+sum(volumes.values())+recovery != 200 or recovery > 100:
        raise ValueError('All three receiving tanks and recovered liquid must conserve the historical source')
    target = current['target']
    return {'target':target,'goal':goals[target],'capacity':capacities[target],'total':volumes[target],
            'remaining':goals[target]-volumes[target],'waste_penalty':True,'volumes':volumes,
            'history_source_remaining':source_remaining,'recovery_units':recovery}


def next_action(facts,current):
    return decision_command(current,{'increment':facts['remaining']})


def check_world(task,facts):
    if task.world != {key:facts[key] for key in task.world}:
        raise ValueError('Supply target must follow actual net retention, separately from capacity')
    if task.initial and (task.initial['stored'] != facts['volumes'] or any(
            task.initial[key] != facts[key] for key in ('history_source_remaining','recovery_units'))):
        raise ValueError('Receiving, supply and recovery tanks must preserve the public history balance')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:supply_score(facts['total'],facts['goal'],facts['capacity'],op['increment']))
