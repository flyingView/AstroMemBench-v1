"""FM-E2-O3: externally revised receiver pressures and independent split cutoffs."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Initial absolute PA/PB, old Q, local U/V changes, final PA/PB.
CONFIGS = (
    ((2,8),8,(('B',3),),(('A',7),),(7,3)),
    ((9,1),1,(('A',8),),(('B',2),),(8,2)),
    ((4,6),6,(('A',1),),(('A',4),),(4,6)),
    ((10,0),0,(('A',2),),(('B',8),),(2,8)),
    ((6,4),4,(('B',10),),(('A',0),),(0,10)),
    ((8,2),2,(('A',10),),(('B',0),),(10,0)),
    ((3,7),7,(('A',9),('B',2)),(('B',1),),(9,1)),
    ((1,9),9,(('A',5),('B',6)),(('A',1),('B',9)),(1,9)),
    ((4,6),6,(('A',0),('B',8)),(('B',10),),(0,10)),
    ((2,8),8,(('A',10),('B',2)),(('B',0),),(10,0)),
    ((5,5),5,(('A',7),('B',3)),(('A',5),('B',5)),(5,5)),
    ((10,0),0,(('A',8),('B',1)),(('B',2),),(8,2)),
    ((2,8),8,(('A',7),('B',5)),(('A',2),('B',8)),(2,8)),
    ((10,0),0,(('A',3),('B',6)),(('A',0),('B',10)),(0,10)),
    ((0,10),10,(('A',6),('B',5)),(('A',10),('B',0)),(10,0)),
    ((3,7),7,(('A',8),('B',5)),(('A',6),('B',4)),(6,4)),
)
MODEL = {'pressure_limit_kpa':10,'pressure_increase_kpa_per_l':1,'supply_l':10,'program_duration_s':20,
         'flow_l_per_s':'requested_l / 20','actual_received_l':'min(requested_l, 10 - initial_pressure_kpa)',
         'independent_cutoffs':True,'redirect_unaccepted':False}


def build(index):
    initial,old,updates,final_updates,final = CONFIGS[index]
    history,pressures = History(),{}

    def add(at,text,**facts):
        history.add(at,text,record_id=f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}',**facts)

    add(1,'目标K的A/B为独立接收容腔，J-A/J-B属于另一目标。服务方供泵、两管路、计量器和止回阀始终正常且已连接。'
        '接收侧外部加热、遮蔽或自身放散可改变绝对压力，实测只更新该目标相应容腔，没有未报告变化，计划不生效。'
        '题内恒定响应：每接收1L初压升1kPa，允许终压10kPa，余量10-P L；各腔独立、不互通。'
        '本轮10L惰性工艺液，Q0—Q10中Qx请求A=x L、B=10-x L，两路同时按各自请求量/20秒供给，'
        '设备支持每路0—0.5L/s；达到10kPa自动截止，实际收min(请求,余量)，未达到限的支路继续至20秒。'
        '请求0的支路全程关闭；未送留供方，不泄漏、不自动改道。一次合法Q占用唯一20秒机会，不能试送或补送。'
        '目标尽量增加两端实际交付量，合计交付10L即可完成全部需求；留在罐内的余液不算已交付。'
        '十一Q加保持始终可选，有效/无效/end合计最多3次；首个合法操作终局，推理和检索不推进故事时间。',
        event='split_supply_protocol',model=MODEL)
    add(2,'本轮工艺液10L尚未交付，两管路正常。旧周期各自另备10L，随后由目标自身消费/放散并实测恢复，均不占本轮供给。',
        event='supply_assignment',target='K',current_supply_l=10,current_delivery_l=0,equipment_ready=True)

    def measure(at,target,chamber,value):
        key = (target,chamber)
        previous = pressures.get(key)
        if previous is None:
            cause = '绝对初压实测'
        elif value > previous:
            cause = '接收侧外部加热后稳态复测'
        elif value < previous:
            cause = '接收侧遮蔽冷却/自身放散已发生后稳态复测'
        else:
            cause = '再次稳态实测确认仍为原值'
        add(at,f'{target}-{chamber}：{cause}，绝对压力{value}kPa。',event='pressure_measured',
            target=target,chamber=chamber,previous_kpa=previous,pressure_kpa=value)
        pressures[key] = value

    def old_cycle(at,cycle):
        finish = clock(f'08:{at:02d}')
        before = {c:pressures['K',c] for c in ('A','B')}
        delivered = {'A':min(old,10-before['A']),'B':min(10-old,10-before['B'])}
        after = {c:before[c]+delivered[c] for c in ('A','B')}
        consumed = dict(zip(('A','B'),(10-initial[0],10-initial[1]),strict=True))
        add(at,f'目标K旧补给周期{cycle}独立供液10L，{story_timestamp(finish-60)}开始Q{old}，'
            f'{story_timestamp(finish-40)}结束20秒交付：A收{delivered["A"]}L、B收{delivered["B"]}L，'
            f'绝对终压{after["A"]}/{after["B"]}kPa，旧供方剩{10-sum(delivered.values())}L。',
            occurred=finish-40,event='old_supply_completed',target='K',cycle=cycle,program=f'Q{old}',request_a_l=old,
            started_s=finish-60,finished_s=finish-40,supply_initial_l=10,pressure_before_kpa=before,
            received_l=delivered,pressure_after_kpa=after,supply_remaining_l=10-sum(delivered.values()))
        add(at,f'目标K旧周期{cycle}接收侧自身消费/放散于{story_timestamp(finish-40)}开始、{story_timestamp(finish-20)}完成：'
            f'A实际消耗{consumed["A"]}L、B实际消耗{consumed["B"]}L，随后稳定20秒。',
            occurred=finish-20,event='old_receiver_consumption_completed',target='K',cycle=cycle,
            started_s=finish-40,finished_s=finish-20,consumed_l=consumed)
        restored = dict(zip(('A','B'),initial,strict=True))
        add(at,f'旧周期{cycle}稳定后于{story_timestamp(finish)}实际复测K-A/B绝对压力为{initial[0]}/{initial[1]}kPa。旧周期结束。',
            occurred=finish,event='old_pressure_restored',target='K',cycle=cycle,
            stabilization_started_s=finish-20,finished_s=finish,pressure_kpa=restored)
        for chamber,value in restored.items():
            pressures['K',chamber] = value

    measure(3,'K','A',initial[0])
    measure(3 if index < 6 else 7,'K','B',initial[1])
    if index < 6:
        old_cycle(6,1)
        old_cycle(9,2)
        update_round,plan_round = 14,20
    elif index < 12:
        old_cycle(10,1)
        old_cycle(13,2)
        update_round,plan_round = 16,21
    else:
        old_cycle(9,1)
        measure(11,'K','A',10)
        measure(13,'K','A',initial[0])
        old_cycle(15,2)
        update_round,plan_round = 18,22
    for chamber,value in updates:
        measure(update_round,'K',chamber,value)
    add(plan_round,f'拟通过接收侧放散/热控恢复K-A/B绝对压力至{initial[0]}/{initial[1]}kPa，尚未执行。',
        event='pressure_plan',target='K',planned_pressure_kpa=dict(zip(('A','B'),initial,strict=True)),implemented=False)
    for chamber,value in final_updates:
        measure(24,'K',chamber,value)
    for chamber,value in zip(('A','B'),initial,strict=True):
        measure(28,'J',chamber,value)
    add(30,'目标K已对接保持，两支路计量准备完成，等待本轮10L分流。',event='split_supply_ready',target='K',supply_l=10)
    task = task_shell('FM-E2-O3',index)
    task.public = {'time_s':clock('09:00'),'target':'K','supply_l':10,'split_model':MODEL,'max_steps':3,'state_fields':[],
        'instruction':'任务第120日09:00；已对接目标K；本轮工艺液10L。请执行本轮补给分流。',
        'actions':fixed_options([{'operation':{'kind':'split','request_a_l':x},'description':f'Q{x}：A请求{x}L、B请求{10-x}L。'} for x in range(11)]+
                                 [{'operation':{'kind':'hold'},'description':'保持，不补给。'}])}
    task.initial = {'time_s':clock('09:00'),'supply_remaining_l':10,'received_l':{'A':0,'B':0},
                    'pressure_kpa':dict(zip(('A','B'),final,strict=True)),'branches':{},'opportunity_used':False,'leaked_l':0}
    task.world = {'pressure_kpa':dict(zip(('A','B'),final,strict=True))}
    task.rubric = {'score':'10 per litre actually accepted by either independent receiver; undelivered fluid remains in supply'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，不补给，操作结束。'
            return 0
        x,start = operation['request_a_l'],self.state['time_s']
        for chamber,request in (('A',x),('B',10-x)):
            initial = self.state['pressure_kpa'][chamber]
            delivered = min(request,10-initial)
            duration = 20*delivered/request if request else 0
            self.state['branches'][chamber] = {'requested_l':request,'flow_l_per_s':request/20,
                'received_l':delivered,'active_duration_s':duration,'started_s':start,'stopped_s':start+duration,
                'stop_reason':'closed' if request == 0 else 'pressure_limit' if delivered < request else 'request_completed'}
            self.state['received_l'][chamber] = delivered
            self.state['pressure_kpa'][chamber] = initial+delivered
            self.state['supply_remaining_l'] -= delivered
        self.state.update(time_s=start+20,opportunity_used=True)
        self.feedback = f'已完成Q{x}的本轮分流，交付记录已归档。'
        return 10*sum(self.state['received_l'].values())


def reconstruct(history,current):
    pressures = {}
    for text in paragraphs(history):
        measurement = re.fullmatch(r'([KJ])-([AB])：(绝对初压实测|接收侧外部加热后稳态复测|接收侧遮蔽冷却/自身放散已发生后稳态复测|再次稳态实测确认仍为原值)，'
                                   r'绝对压力(\d+)kPa。',text)
        if measurement and measurement[1] == current['target']:
            _,chamber,cause,printed = measurement.groups()
            value,previous = int(printed),pressures.get(chamber)
            if ((cause == '绝对初压实测' and previous is not None)
                    or (cause == '再次稳态实测确认仍为原值' and previous != value)
                    or (cause == '接收侧外部加热后稳态复测' and (previous is None or value <= previous))
                    or (cause == '接收侧遮蔽冷却/自身放散已发生后稳态复测' and (previous is None or value >= previous))):
                raise ValueError('Absolute pressure revision must preserve the previous local pressure')
            pressures[chamber] = value
        supply = re.fullmatch(rf'目标([KJ])旧补给周期\d+独立供液10L，{STORY_STAMP}开始Q(\d+)，'
                              rf'{STORY_STAMP}结束20秒交付：A收(\d+)L、B收(\d+)L，'
                              r'绝对终压(\d+)/(\d+)kPa，旧供方剩(\d+)L。',text)
        if supply and supply[1] == current['target']:
            x = int(supply[2])
            expected = {c:min(request,10-pressures[c]) for c,request in (('A',x),('B',10-x))}
            if expected != {'A':int(supply[3]),'B':int(supply[4])} or sum(expected.values()) != 10 or int(supply[7]) != 0:
                raise ValueError('Old cycle must actually deliver its own ten litres under then-current pressures')
            pressures = {c:pressures[c]+expected[c] for c in ('A','B')}
            if pressures != {'A':int(supply[5]),'B':int(supply[6])}:
                raise ValueError('Old cycle final pressures must follow actual received volume')
        consumption = re.fullmatch(rf'目标([KJ])旧周期\d+接收侧自身消费/放散于{STORY_STAMP}开始、{STORY_STAMP}完成：'
                                   r'A实际消耗(\d+)L、B实际消耗(\d+)L，随后稳定20秒。',text)
        if consumption and consumption[1] == current['target']:
            pressures = {c:pressures[c]-int(consumption[i]) for c,i in (('A',2),('B',3))}
        restored = re.fullmatch(rf'旧周期\d+稳定后于{STORY_STAMP}实际复测([KJ])-A/B绝对压力为(\d+)/(\d+)kPa。旧周期结束。',text)
        if restored and restored[1] == current['target'] and pressures != {'A':int(restored[2]),'B':int(restored[3])}:
            raise ValueError('The restored absolute reading must follow explicit old-cycle receiver consumption')
    return {'pressure_kpa':pressures}


def next_action(facts,current):
    return decision_command(current,{'kind':'split','request_a_l':10-facts['pressure_kpa']['A']})


def check_world(task,facts):
    if facts != task.world or facts['pressure_kpa'] != task.initial['pressure_kpa']:
        raise ValueError('Current receiver pressure must follow actual environmental revisions')


def audit_cases(task,facts,solution):
    capacities = {c:10-p for c,p in facts['pressure_kpa'].items()}
    def score(operation):
        if operation['kind'] == 'hold':
            return 0
        x = operation['request_a_l']
        return 10*(min(x,capacities['A'])+min(10-x,capacities['B']))
    return decision_cases(task,solution,score)
