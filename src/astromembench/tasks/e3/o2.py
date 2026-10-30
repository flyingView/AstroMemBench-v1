"""FM-E3-O2: localize a three-branch worksite under roll, retaining handedness."""
import re

from ..common import History, clock, task_shell
from ..decisions import DecisionRuntime, decision_cases
from ..prose import STORY_STAMP, paragraphs, seconds
from .locations import location, report_command, report_options
from ...environment import TaskRuntime
from ...schema import story_timestamp

GEOMETRY = ((2,3,5),(2,5,3),(2,3,7),(2,7,3),(2,5,7),(2,7,5),(3,5,7),(3,7,5),(2,3,9))
NAMES = {'A':(8,3,6,1,9,4,2,7,5),'B':(4,9,2,7,5,1,6,3,8),
         'C':(1,7,4,9,2,8,5,6,3),'D':(7,2,5,3,6,9,8,1,4)}
ORDERS = {'A':(5,1,8,3,7,2,9,4,6),'B':(2,7,4,9,1,6,3,8,5),
          'C':(8,4,2,6,9,3,5,1,7),'D':(3,9,5,1,6,8,4,7,2)}
VISITS = ('V48','V13','V76','V25','V61','V09','V34','V87','V52')
# Naming registration, actual worksite geometry, left cyclic shift of the current scan.
CONFIGS = (('A',1,0),('D',2,0),('A',5,0),('C',3,0),('A',9,0),('D',7,0),
           ('A',2,1),('D',3,2),('B',9,2),('C',1,1),('A',7,1),('D',8,2),
           ('B',6,2),('D',1,2),('A',4,1),('C',2,1))


def rotations(values):
    values = tuple(values)
    return [values[k:]+values[:k] for k in range(3)]


def build(index):
    naming,q,k = CONFIGS[index]
    names,history = NAMES[naming],History()
    history.add(1,'目标K有N01—N09九个三叉检修工位，N名称不表示尺寸、邻接或先后。每工位三条共面短支通道，'
        '端面距离以cm精确给出，无误差。历史与当前都沿插入轴从相同一侧看去按顺时针扫描，未穿过工位回看。'
        '机械止挡固定探头端位置；滚转只改变起始射线，允许循环移位，不允许反序或任意排序，测距值不变。'
        '九工位、名称、尺度及设备状态稳定，无维修操作；没有可积分的移动命令或里程。'
        'A—I报告N01—N09，J报告无法确定，end放弃；十项报告持续显示，首个合法报告无论对错立即结束。'
        '有效、无效及end合计最多3次，第三次仍可合法报告；无效仅反馈格式，三次无效或主动放弃即终止任务。'
        '须报告完整位置，无需解释；没有旋转、再扫描或定位查询动作，报告不旋转或推进探头。'
        '阅读与原生检索不计调用。',event='worksite_localization_protocol')
    mapping,visits = {},[]
    for j,(slot,visit) in enumerate(zip(ORDERS[naming],VISITS,strict=True)):
        name,distances = location(names[slot-1]),list(GEOMETRY[slot-1])
        at,actual = 2+2*j,clock('15:00',119)+j*180
        mapping[name] = distances
        visits.append({'visit':visit,'location':name,'arrived_s':actual,'scanned_s':actual,'clockwise_cm':distances})
        if index < 6:
            history.add(at,f'{visit}：{story_timestamp(actual)}实际到达K-{name}入口止挡，未实施维修；同侧沿插入轴顺时针实测三距离'
                f'{distances[0]}/{distances[1]}/{distances[2]} cm。',occurred=actual,event='worksite_survey',target='K',
                visit=visit,location=name,arrived_s=actual,scanned_s=actual,clockwise_cm=distances,direction='clockwise',view_side='same_insertion_side')
            history.add(at+1,'该次已完成的测距记录归档确认。',event='closed_worksite_archive')
        else:
            history.add(at,f'{visit}：{story_timestamp(actual)}实际到达K-{name}入口止挡，未实施维修。',occurred=actual,
                event='worksite_arrival',target='K',visit=visit,location=name,arrived_s=actual)
            history.add(at+1,f'{visit}：{story_timestamp(actual)}目标K同侧沿插入轴顺时针实测三距离'
                f'{distances[0]}/{distances[1]}/{distances[2]} cm。',occurred=actual,event='worksite_measurement',target='K',visit=visit,
                scanned_s=actual,clockwise_cm=distances,direction='clockwise',view_side='same_insertion_side')
    history.add(20,'全部测距量已核对固定精度，当前没有尺度或环境变化。',event='worksite_scale_verified')
    history.add(21,'已结束维修的物料凭据完成归档。',event='closed_worksite_archive')
    if index >= 12:
        for j,n in enumerate(names[::-1]):
            distances = list(GEOMETRY[j])
            history.add(22,f'独立设备J工位{location(n)}已完整测绘：同侧沿插入轴顺时针三距离'
                f'{distances[0]}/{distances[1]}/{distances[2]} cm。',occurred=clock('16:00',119)+j*180,
                event='worksite_survey',target='J',location=location(n),clockwise_cm=distances,
                direction='clockwise',view_side='same_insertion_side')
    history.add(23,'当前检修对象固定K；独立设备J的档案不改变K工位登记。',event='worksite_assignment',target='K')
    for at,n in ((24,9),(26,9),(27,4)):
        history.add(at,f'确认实际访问K-{location(n)}，入口止挡正常，没有新距离扫描。'+('随后自主换位，过程终点记录缺失。' if at == 27 else ''),
            event='recent_worksite',target='K',location=location(n),scanned=False)
    history.add(28,'探头已重新在某个K工位的止挡处停稳，没有终点定位记录。',event='worksite_stationary')
    history.add(29,'传感器正常，轴向观察侧未变，滚转零点未保留。',event='worksite_sensor_verified')
    history.add(30,'维修尚未开始，等待位置报告。',event='worksite_ready')
    current = list(rotations(GEOMETRY[q-1])[k])
    task = task_shell('FM-E3-O2',index)
    task.public = {'time_s':clock('09:00'),'target':'K','clockwise_cm':current,'direction':'clockwise',
        'view_side':'same_insertion_side','max_steps':3,'state_fields':[],
        'instruction':f'目标K探头已在工位止挡处停稳。绝对定位暂不可用；沿插入轴同侧观察的顺时针三条测距为'
            f'{current[0]}/{current[1]}/{current[2]} cm。请报告当前工位。','actions':report_options()}
    task.initial = {'time_s':clock('09:00'),'reported_location':None,'maintenance_started':False}
    task.world = {'map':mapping,'visits':visits,'current_location':location(names[q-1]),'current_clockwise_cm':current}
    task.rubric = {'score':'100 for exact worksite under cyclic shift; reversed or sorted geometry earns no partial credit'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def actions(self):
        # This FM retains the complete report menu even in the terminal display.
        return TaskRuntime.actions(self)

    def execute(self,operation):
        self.state['reported_location'] = operation['location']
        self.feedback = '工位定位报告已记录。'
        return 100 if operation['location'] == self.task.world['current_location'] else 0


def reconstruct(history,current):
    arrivals,measurements = {},{}
    target = re.escape(current['target'])
    scan = r'(同侧|异侧)沿插入轴(顺时针|逆时针)实测三距离(\d+)/(\d+)/(\d+) cm。'
    for text in paragraphs(history):
        if match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际到达{target}-(N\d{{2}})入口止挡，未实施维修；{scan}',text):
            visit,stamp,name,side,direction,a,b,c = match.groups()
            arrivals[visit] = {'location':name,'arrived_s':seconds(stamp)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际到达{target}-(N\d{{2}})入口止挡，未实施维修。',text):
            visit,stamp,name = match.groups()
            arrivals[visit] = {'location':name,'arrived_s':seconds(stamp)}
            continue
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})目标{target}{scan}',text):
            visit,stamp,side,direction,a,b,c = match.groups()
        else:
            continue
        if ({'顺时针':'clockwise','逆时针':'counterclockwise'}[direction] != current['direction']
                or {'同侧':'same_insertion_side','异侧':'opposite_insertion_side'}[side] != current['view_side']):
            raise ValueError('Historical and current geometry must use the same directed viewing side')
        measurements[visit] = {'clockwise_cm':list(map(int,(a,b,c))),'scanned_s':seconds(stamp)}
    if len(arrivals) != 9 or arrivals.keys() != measurements.keys():
        raise ValueError('All worksite arrivals must have complete directed scans')
    mapping = {}
    for visit,arrival in arrivals.items():
        if arrival['arrived_s'] != measurements[visit]['scanned_s']:
            raise ValueError('Worksite scan must be at the fixed stop during its visit')
        mapping[arrival['location']] = measurements[visit]['clockwise_cm']
    allowed = {value:name for name,distances in mapping.items() for value in rotations(distances)}
    if len(mapping) != 9 or len(allowed) != 27:
        raise ValueError('All twenty-seven directed cyclic readings must identify unique worksites')
    match = allowed.get(tuple(current['clockwise_cm']))
    if match is None:
        raise ValueError('Current directed scan has no registered cyclic match')
    return {'map':mapping,'current_location':match}


def next_action(facts,current):
    return report_command(facts['current_location'])


def check_world(task,facts):
    if any(facts[key] != task.world[key] for key in facts):
        raise ValueError('Public directed survey differs from the physical worksite identity')
    if tuple(task.world['current_clockwise_cm']) not in rotations(facts['map'][facts['current_location']]):
        raise ValueError('Physical current scan must retain the registered handedness')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op['location'] == facts['current_location'] else 0)
