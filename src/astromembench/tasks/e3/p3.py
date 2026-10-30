"""FM-E3-P3: identify a cyclic transport stop from three actual geometric scans."""
import re

from ..common import History, clock, task_shell
from ..decisions import DecisionRuntime, decision_cases
from ..prose import STORY_STAMP, paragraphs, seconds
from .locations import location, report_command, report_options
from ...schema import story_timestamp

GEOMETRY = {'a':(20,80),'b':(35,50),'c':(50,110)}
ENVIRONMENTS = {'A':'aabacbbcc','B':'aabbacbcc','C':'aabbcaccb','D':'abcabaccb'}
NAMES = {'A':(4,8,1,6,2,9,5,3,7),'B':(7,2,6,9,5,1,8,4,3),
         'C':(3,6,8,1,7,4,9,2,5),'D':(8,5,2,7,4,3,1,9,6)}
ORDERS = {'A':(6,2,8,4,1,7,3,9,5),'B':(3,8,1,6,9,2,5,7,4),
          'C':(7,4,9,2,5,1,8,3,6),'D':(5,9,3,7,2,6,1,4,8)}
VISITS = ('V31','V08','V54','V19','V72','V43','V16','V65','V27')
# Environment, naming registration, actual current stop (one-based).
CONFIGS = (('A','A',3),('B','B',3),('C','C',2),('D','A',2),('A','C',5),('D','B',4),
           ('B','A',6),('C','B',2),('D','C',9),('A','A',1),('D','D',8),('C','D',6),
           ('A','C',8),('C','A',9),('B','A',2),('D','C',3))


def scan(code):
    height,width = GEOMETRY[code]
    return {'left_ridge_height_cm':height,'trench_width_cm':width}


def build(index):
    geometry,naming,q = CONFIGS[index]
    codes,names,order = ENVIRONMENTS[geometry],NAMES[naming],ORDERS[naming]
    history = History()
    history.add(1,'K区九处运输停靠点N01—N09组成无支路单向闭环，名称无几何顺序；各处地貌及下游连接固定。'
        '每次相邻停靠只向下游走一次，不跳点、不掉头。激光固定前端给左侧土脊高/沟槽宽，单位cm，无误差，数值不编码N。'
        '最后三个相邻停靠的实际扫描按时间排序，第三次为当前位置；它们不是计划或运动命令。'
        '低层驾驶、载荷、能源及通行条件正常，报告不移动，不要求装卸，没有定位查询或移动试探。'
        'A—I报告N01—N09，J报告无法确定，end放弃；须提交完整位置，首个合法报告立即终局，无需解释。'
        '有效、无效、end合计最多3次，第三次格式错误结束；前两次格式错误后仍可提交报告。推理及原生检索不计调用。',
        event='transport_localization_protocol')
    map_rows,visits = {},[]
    for j,(i,visit) in enumerate(zip(order,VISITS,strict=True)):
        name,downstream = location(names[i-1]),location(names[i%9])
        measured = scan(codes[i-1])
        arrived = clock('10:00',119)+(i-1)*300
        moved = arrived+60
        at = 2+2*j
        map_rows[name] = {'scan':measured,'downstream':downstream}
        visits.append({'visit':visit,'location':name,'arrived_s':arrived,'scan':measured,
                       'downstream':downstream,'downstream_arrival_s':moved})
        if index < 6:
            history.add(at,f'{visit}：{story_timestamp(arrived)}实际抵达K-{name}并扫描，土脊高{measured["left_ridge_height_cm"]}cm、'
                f'沟槽宽{measured["trench_width_cm"]}cm；{story_timestamp(moved)}实际从该点走到下游K-{downstream}。',
                occurred=moved,event='transport_stop_survey',region='K',visit=visit,location=name,scan=measured,
                arrived_s=arrived,scanned_s=arrived,downstream=downstream,downstream_arrival_s=moved)
            history.add(at+1,'已完成的卸货凭据已整理入档。',event='closed_transport_archive')
        else:
            history.add(at,f'{visit}：{story_timestamp(arrived)}实际抵达K-{name}，到达登记已归档。',
                occurred=arrived,event='transport_stop_arrival',region='K',visit=visit,location=name,arrived_s=arrived)
            history.add(at+1,f'{visit}：{story_timestamp(arrived)}实际扫描土脊高{measured["left_ridge_height_cm"]}cm、'
                f'沟槽宽{measured["trench_width_cm"]}cm；{story_timestamp(moved)}已实际走到下游K-{downstream}。',
                occurred=moved,event='transport_stop_scan',region='K',visit=visit,scan=measured,scanned_s=arrived,
                downstream=downstream,downstream_arrival_s=moved)
    if index >= 12:
        other_names,other_codes = names[::-1],codes[::-1]
        for j,(n,code) in enumerate(zip(other_names,other_codes,strict=True)):
            measured = scan(code)
            history.add(20,f'独立运输区J：{location(n)}现场扫描土脊高{measured["left_ridge_height_cm"]}cm、'
                f'沟槽宽{measured["trench_width_cm"]}cm，真实下游为{location(other_names[(j+1)%9])}；J与K没有道路相连。',
                occurred=clock('11:00',119)+j*300+60,event='transport_stop_survey',region='J',location=location(n),
                scan=measured,downstream=location(other_names[(j+1)%9]))
    history.add(20,'K区激光传感器校验正常，全部横断面数值保持稳定。',event='scanner_verified',region='K')
    history.add(21,'K区全部九条实际连接已完成测绘并构成闭环，登记及连接没有变化。',event='ring_verified',region='K')
    history.add(22,'已结束运输批次清单归档完毕。',event='closed_transport_archive')
    history.add(23,'存储及能源状态正常，通行条件稳定。',event='transport_health')
    for at,n in ((24,9),(26,9),(27,4)):
        history.add(at,f'实际确认停靠K-{location(n)}，载荷系固复查正常；没有新扫描。'+('随后准备继续运输。' if at == 27 else ''),
            event='recent_stop',region='K',location=location(n),scanned=False)
    history.add(28,'此后已完成若干环线运输，最后有标签的出发点、完整停靠次数及终点日志未留存。',event='transport_log_incomplete')
    history.add(29,'激光传感器与时序缓冲正常，缓存可提供最后三个相邻停靠的扫描。',event='buffer_verified')
    history.add(30,'载具已停稳，没有当前N定位，载荷完整，报告前无需装卸。',occurred=clock('08:30'),event='transport_parked')
    cache = [{'time_s':clock(f'08:{57+j}'),**scan(codes[(q-3+j)%9])} for j in range(3)]
    task = task_shell('FM-E3-P3',index)
    task.public = {'time_s':clock('09:00'),'region':'K','scans':cache,'max_steps':3,'state_fields':[],
        'instruction':'运输载具在08:30的停车后，于08:56恢复自动运输，08:59再次停稳；定位流一直暂不可用。'
            '下列是08:57、08:58、08:59三个相邻停靠的实际扫描，后一行晚于前一行。请报告当前停靠点。',
        'transport_resumed_s':clock('08:56'),'parked_s':clock('08:59'),'actions':report_options()}
    if index < 6:
        task.public['scanner_value_examples_cm'] = [scan(c) for c in 'abc']
    task.initial = {'time_s':clock('09:00'),'reported_location':None}
    task.world = {'map':map_rows,'visits':visits,'current_location':location(names[q-1]),
                  'recent_stops':[location(names[(q-3+j)%9]) for j in range(3)]}
    task.rubric = {'score':'100 only for the exact current stop; reporting does not move the vehicle'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['reported_location'] = operation['location']
        self.feedback = '停靠位置报告已记录。'
        return 100 if operation['location'] == self.task.world['current_location'] else 0


def reconstruct(history,current):
    arrivals,observations = {},{}
    region = re.escape(current['region'])
    for text in paragraphs(history):
        if match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际抵达{region}-(N\d{{2}})并扫描，土脊高(\d+)cm、沟槽宽(\d+)cm；({STORY_STAMP})实际从该点走到下游{region}-(N\d{{2}})。',text):
            visit,arrived,name,height,width,moved,downstream = match.groups()
            arrivals[visit] = {'location':name,'arrived_s':seconds(arrived)}
            observations[visit] = {'scan':{'left_ridge_height_cm':int(height),'trench_width_cm':int(width)},
                'scanned_s':seconds(arrived),'downstream':downstream,'downstream_arrival_s':seconds(moved)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际抵达{region}-(N\d{{2}})，到达登记已归档。',text):
            visit,arrived,name = match.groups()
            arrivals[visit] = {'location':name,'arrived_s':seconds(arrived)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际扫描土脊高(\d+)cm、沟槽宽(\d+)cm；({STORY_STAMP})已实际走到下游{region}-(N\d{{2}})。',text):
            visit,scanned,height,width,moved,downstream = match.groups()
            observations[visit] = {'scan':{'left_ridge_height_cm':int(height),'trench_width_cm':int(width)},
                'scanned_s':seconds(scanned),'downstream':downstream,'downstream_arrival_s':seconds(moved)}
    if len(arrivals) != 9 or arrivals.keys() != observations.keys():
        raise ValueError('Nine complete visited stops are required')
    mapped = {}
    for visit,arrival in arrivals.items():
        obs = observations[visit]
        if not arrival['arrived_s'] == obs['scanned_s'] < obs['downstream_arrival_s']:
            raise ValueError('Stop survey must scan at arrival before actual downstream travel')
        mapped[arrival['location']] = {k:obs[k] for k in ('scan','downstream')}
    cursor = next(iter(mapped))
    seen = set()
    for _ in range(9):
        if cursor in seen:
            raise ValueError('Registered stops must form one nine-stop cycle')
        seen.add(cursor)
        cursor = mapped[cursor]['downstream']
    if len(mapped) != 9 or cursor != next(iter(mapped)):
        raise ValueError('Transport map is not a complete closed cycle')
    measured = [{k:r[k] for k in ('left_ridge_height_cm','trench_width_cm')} for r in current['scans']]
    matches = []
    for start in mapped:
        second = mapped[start]['downstream']
        third = mapped[second]['downstream']
        if [mapped[n]['scan'] for n in (start,second,third)] == measured:
            matches.append([start,second,third])
    if len(matches) != 1:
        raise ValueError('Actual ordered scan cache must identify one cyclic three-stop path')
    return {'map':mapped,'recent_stops':matches[0],'current_location':matches[0][-1]}


def next_action(facts,current):
    return report_command(facts['current_location'])


def check_world(task,facts):
    if any(facts[key] != task.world[key] for key in facts):
        raise ValueError('Public transport geometry and connections disagree with physical locations')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op['location'] == facts['current_location'] else 0)
