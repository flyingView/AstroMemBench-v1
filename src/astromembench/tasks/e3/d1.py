"""FM-E3-D1: identify a cruise segment from a simultaneous common-clock snapshot."""
import re

from ..common import History, clock, task_shell
from ..decisions import DecisionRuntime, decision_cases
from ..prose import STORY_STAMP, paragraphs, seconds
from .locations import location, report_command, report_options
from ...schema import story_timestamp

FEATURES = ((-4,-3),(-4,0),(-4,3),(0,-3),(0,0),(0,3),(4,-3),(4,0),(4,3))
NAMES = {'A':(7,1,5,3,9,2,8,6,4),'B':(2,8,4,6,1,7,5,9,3),
         'C':(5,3,9,1,6,8,4,2,7),'D':(9,4,2,8,5,3,7,1,6)}
ORDERS = {'A':(6,1,8,4,9,2,5,7,3),'B':(3,7,2,9,5,8,1,4,6),
          'C':(8,4,6,1,7,3,9,5,2),'D':(2,9,5,7,3,6,4,8,1)}
VISITS = ('V51','V06','V38','V74','V23','V89','V17','V62','V45')
SNAPSHOTS = ('S37','S82','S16','S59','S24','S73','S48','S91','S65')
CONFIGS = (('A',1,50),('B',5,73),('D',3,96),('C',6,81),('A',4,34),('B',9,107),
           ('A',8,126),('B',3,39),('C',5,118),('A',2,83),('B',7,102),('D',1,137),
           ('A',5,208),('C',4,276),('B',1,237),('D',7,315))


def snapshot(feature,reference):
    db,dc = feature
    return {'A':reference,'B':reference+db,'C':reference+dc}


def differences(values):
    return [values['B']-values['A'],values['C']-values['A']]


def build(index):
    naming,q,reference = CONFIGS[index]
    names,history = NAMES[naming],History()
    history.add(1,'当前航路K有九个已经实际穿越并标定的离散空间区段N01—N09，N为任意名称，不是源ID或时钟故障代码。'
        '外部导航源A/B/C共用同一接收时钟，每次同步快照的残差tA/tB/tC单位ms，共同钟偏b同时加到三个值。'
        '空间特征为tB−tA、tC−tA，必须取同一快照，不能混合不同快照。各次残差快照都在前端完成周期/星历补偿与整周期消歧后交付，'
        '数值精确、无取模折返、无噪声，不是光行时距离。九种空间差分稳定，每分量各重复三次，需联合两者与历史名称登记。'
        '当前仅处于其中一个区段，所有设备和巡航控制正常；不要求连续轨道、速度、姿态或未来区段预测。'
        'A—I报告N01—N09，J报告无法确定，end放弃；有效、无效及end合计最多3次，第三次仍可有效报告。'
        '须报告完整位置，首个合法报告立即结束，不要求钟偏或解释；格式反馈不含差分或候选信息。'
        '没有测钟偏、查询位置或继续飞行工具；报告绑定09:00同步快照，不推进待判定时刻，原生检索不计动作。',
        event='cruise_localization_protocol')
    mapping,visits = {},[]
    for j,(slot,visit,identifier) in enumerate(zip(ORDERS[naming],VISITS,SNAPSHOTS,strict=True)):
        name = location(names[slot-1])
        values,actual = snapshot(FEATURES[slot-1],100),clock('12:00',110+j)
        mapping[name] = list(FEATURES[slot-1])
        visits.append({'visit':visit,'location':name,'crossed_s':actual,'snapshot_id':identifier,'snapshot_ms':values})
        at = 2+2*j
        if index < 6:
            history.add(at,f'{visit}：{story_timestamp(actual)}实际穿越K-{name}，同步快照{identifier}的A/B/C残差'
                f'{values["A"]}/{values["B"]}/{values["C"]} ms。',occurred=actual,event='cruise_survey',route='K',visit=visit,
                location=name,crossed_s=actual,snapshot_s=actual,snapshot_id=identifier,snapshot_ms=values)
            history.add(at+1,'该次实际穿越记录已归档。',event='closed_cruise_archive')
        else:
            history.add(at,f'{visit}：{story_timestamp(actual)}已实际穿越航路K的{name}。',occurred=actual,
                event='cruise_crossing',route='K',visit=visit,location=name,crossed_s=actual)
            history.add(at+1,f'{visit}：{story_timestamp(actual)}航路K同一同步快照{identifier}，A/B/C残差'
                f'{values["A"]}/{values["B"]}/{values["C"]} ms。',occurred=actual,event='cruise_snapshot',route='K',visit=visit,
                snapshot_s=actual,snapshot_id=identifier,snapshot_ms=values)
    history.add(20,'三源相位前端正常，全部已标定空间差分继续有效。',event='cruise_calibration_verified')
    if index >= 12:
        for j,n in enumerate(names[::-1]):
            values = snapshot(FEATURES[j],100)
            actual = clock('12:00',100+j)
            history.add(22,f'独立航路J：{story_timestamp(actual)}实际标定{location(n)}，同一同步快照的A/B/C残差'
                f'{values["A"]}/{values["B"]}/{values["C"]} ms；J与K不共享区段。',occurred=actual,event='cruise_survey',
                route='J',location=location(n),snapshot_id=f'J-{SNAPSHOTS[j]}',snapshot_s=actual,snapshot_ms=values)
    for at,n,time in ((23,9,'12:00'),(24,9,'15:00'),(26,4,'18:00')):
        actual = clock(time,119)
        history.add(at,f'{story_timestamp(actual)}已实际穿越K-{location(n)}，未附相位快照，登记不变。',occurred=actual,
            event='recent_cruise_crossing',route='K',location=location(n),crossed_s=actual)
    history.add(27,'此后自主巡航，连续轨迹、区段进入计数及终点登记均未保留。',event='cruise_log_incomplete')
    history.add(28,'相位接收机正常，共同钟偏未知，三源仍共用同一个接收时钟。',event='cruise_clock_verified')
    history.add(29,'相位前端整周期消歧流程检查正常。',event='cruise_unwrapping_verified')
    history.add(30,'巡航控制正常，暂缺所在区段名称，等待定位报告。',event='cruise_ready')
    current = snapshot(FEATURES[q-1],reference)
    task = task_shell('FM-E3-D1',index)
    task.public = {'time_s':clock('09:00'),'route':'K','snapshot_s':clock('09:00'),'snapshot_id':'C01','snapshot_ms':current,
        'phase_unwrapped':True,'max_steps':3,'state_fields':[],
        'instruction':'当前位于航路K，区段定位暂不可用。09:00这份同步快照已完成整周期消歧；相位残差如下，请报告所在区段。',
        'actions':report_options()}
    task.initial = {'time_s':clock('09:00'),'reported_location':None}
    task.world = {'differentials_ms':mapping,'visits':visits,'current_location':location(names[q-1]),'current_snapshot_ms':current}
    task.rubric = {'score':'100 for the registered segment of the 09:00 simultaneous snapshot; common clock offset is not graded'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['reported_location'] = operation['location']
        self.feedback = '巡航位置报告已记录。'
        return 100 if operation['location'] == self.task.world['current_location'] else 0


def reconstruct(history,current):
    crossings,snapshots = {},{}
    route = re.escape(current['route'])
    values = r'(-?\d+)/(-?\d+)/(-?\d+) ms。'
    for text in paragraphs(history):
        if match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际穿越{route}-(N\d{{2}})，同步快照(S\d+)的A/B/C残差{values}',text):
            visit,stamp,name,identifier,a,b,c = match.groups()
            crossings[visit] = {'location':name,'crossed_s':seconds(stamp)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})已实际穿越航路{route}的(N\d{{2}})。',text):
            visit,stamp,name = match.groups()
            crossings[visit] = {'location':name,'crossed_s':seconds(stamp)}
            continue
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})航路{route}同一同步快照(S\d+)，A/B/C残差{values}',text):
            visit,stamp,identifier,a,b,c = match.groups()
        else:
            continue
        snapshots[visit] = {'snapshot_s':seconds(stamp),'snapshot_id':identifier,
                            'snapshot_ms':dict(zip('ABC',map(int,(a,b,c)),strict=True))}
    if len(crossings) != 9 or crossings.keys() != snapshots.keys() or len({s['snapshot_id'] for s in snapshots.values()}) != 9:
        raise ValueError('Every registered crossing requires its own complete simultaneous snapshot')
    mapping = {}
    for visit,crossing in crossings.items():
        data = snapshots[visit]
        if crossing['crossed_s'] != data['snapshot_s']:
            raise ValueError('Phase snapshot must belong to the actual registered crossing')
        mapping[crossing['location']] = differences(data['snapshot_ms'])
    if len(mapping) != 9 or len({tuple(v) for v in mapping.values()}) != 9:
        raise ValueError('The combined two differences must uniquely identify nine segments')
    feature = differences(current['snapshot_ms'])
    matches = [n for n,v in mapping.items() if v == feature]
    if len(matches) != 1:
        raise ValueError('Current simultaneous snapshot has no unique registered segment')
    return {'differentials_ms':mapping,'current_location':matches[0]}


def next_action(facts,current):
    return report_command(facts['current_location'])


def check_world(task,facts):
    if any(facts[key] != task.world[key] for key in facts):
        raise ValueError('Cruise phase registration differs from the physical segment')
    if differences(task.world['current_snapshot_ms']) != facts['differentials_ms'][facts['current_location']]:
        raise ValueError('Current three-source snapshot must share one common clock offset')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op['location'] == facts['current_location'] else 0)
