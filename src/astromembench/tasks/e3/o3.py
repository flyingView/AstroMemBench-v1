"""FM-E3-O3: localize against named range references and an oriented external side."""
import re

from ..common import History, clock, task_shell
from ..decisions import DecisionRuntime, decision_cases
from ..prose import STORY_STAMP, paragraphs, seconds
from .locations import location, report_command, report_options
from ...schema import story_timestamp

POSITIONS = ((2,4),(2,0),(2,-4),(6,4),(6,0),(6,-4),(10,4),(10,0),(10,-4))
NAMES = {'A':(3,7,1,8,4,9,6,2,5),'B':(6,2,8,5,9,3,1,7,4),
         'C':(9,5,2,4,1,7,3,8,6),'D':(1,6,4,2,7,5,8,9,3)}
ORDERS = {'A':(7,3,6,1,8,4,9,2,5),'B':(4,8,2,7,5,1,6,9,3),
          'C':(9,5,1,6,3,8,4,7,2),'D':(2,6,9,4,7,3,5,1,8)}
VISITS = ('V23','V68','V14','V57','V31','V82','V45','V09','V76')
CONFIGS = (('A',1),('C',8),('D',4),('C',5),('A',3),('D',6),
           ('B',9),('C',2),('A',7),('D',1),('A',8),('B',5),
           ('A',5),('C',3),('B',4),('D',9))


def readings(position):
    x,y = position
    return {'a_m2':x*x+y*y,'b_m2':(x-12)**2+y*y,'side':'+' if y > 0 else '-' if y < 0 else '轴上'}


def build(index):
    naming,q = CONFIGS[index]
    names,history = NAMES[naming],History()
    history.add(1,'接收平台K附近有九个独立悬停接近单元，中心x取2/6/10m、y取4/0/−4m的九种组合，空间无实体碰撞。'
        '外部反射基准A=(0,0)、B=(12,0)m固定、视线可见，均与单元中心分离。N01—N09是任意登记名称，不由坐标次序决定。'
        '传感器给平方斜距a=r_A²、b=r_B²，单位m²，a=x²+y²、b=(x−12)²+y²；A/B标签不能互换。'
        '结构定向通道s在平台坐标中归一化：沿A指向B基线，y>0为+侧，y<0为−侧，y=0为轴上，不按航天器朝向猜左右。'
        '所有读数精确无噪声无容差，平台姿态、反射基准、名称及环境全程稳定，自动保持与设备正常。'
        '当前只报告接近单元，不连接、接管或注入，不查询定位或尝试第二个位置。'
        'A—I报告N01—N09，J报告无法确定，end放弃；首个合法报告无论对错立即终局。'
        '有效、无效及end合计最多3次，第三次可合法报告；三次无效或主动结束即终止任务，格式反馈不含几何相容性。'
        '须报告完整位置N，无需坐标或解释。报告不改变位置、测距或侧向，原生检索不计动作。',
        event='approach_localization_protocol',reflectors_m={'A':[0,0],'B':[12,0]},cell_x_m=[2,6,10],cell_y_m=[4,0,-4])
    mapping,visits = {},[]
    for j,(slot,visit) in enumerate(zip(ORDERS[naming],VISITS,strict=True)):
        name,position = location(names[slot-1]),list(POSITIONS[slot-1])
        values = readings(position)
        at,actual = 2+2*j,clock('09:00',119)+j*240
        mapping[name] = {'position_m':position,'readings':values}
        visits.append({'visit':visit,'location':name,'held_s':actual,'measured_s':actual,**mapping[name]})
        description = (f'x/y={position[0]}/{position[1]}m，平方斜距A={values["a_m2"]}、B={values["b_m2"]}m²，'
                       f'结构侧向{values["side"]}。')
        if index < 6:
            history.add(at,f'{visit}：{story_timestamp(actual)}已实际在K-{name}悬停并完成全标定，'+description,
                occurred=actual,event='approach_survey',target='K',visit=visit,location=name,held_s=actual,
                measured_s=actual,position_m=position,readings=values)
            history.add(at+1,'该访问已完成例行归档。',event='closed_approach_archive')
        else:
            history.add(at,f'{visit}：{story_timestamp(actual)}已实际在K-{name}悬停。',occurred=actual,
                event='approach_hold',target='K',visit=visit,location=name,held_s=actual)
            history.add(at+1,f'{visit}：{story_timestamp(actual)}目标K悬停实测并标定，'+description,occurred=actual,
                event='approach_measurement',target='K',visit=visit,measured_s=actual,position_m=position,readings=values)
    history.add(20,'供给装置尚未接出；接近单元与反射基准没有位移。',event='approach_geometry_verified')
    if index >= 12:
        for j,n in enumerate(names[::-1]):
            position = list(POSITIONS[j])
            values = readings(position)
            history.add(22,f'独立接收平台J的{location(n)}已完成全标定：x/y={position[0]}/{position[1]}m，'
                f'平方斜距A={values["a_m2"]}、B={values["b_m2"]}m²，结构侧向{values["side"]}。J与K空间分离，名称不互换。',
                occurred=clock('10:00',119)+j*240,event='approach_survey',target='J',location=location(n),position_m=position,readings=values)
    history.add(23,'本次接收平台确定为K。',event='approach_assignment',target='K')
    for at,n in ((24,9),(26,9),(27,4)):
        history.add(at,f'实际复访K-{location(n)}并完成悬停检查，没有补给或新的定位表。'+('随后开始自主换位。' if at == 27 else ''),
            event='recent_approach_hold',target='K',location=location(n),transferred=False)
    history.add(28,'自主换位结束，终点定位记录没有保存；没有完整推力指令或可重建航迹。',event='approach_motion_finished')
    history.add(29,'A/B测距与结构定向通道正常，平方量单位仍为m²，零侧向为轴上。',event='approach_sensor_verified')
    history.add(30,'已保持相对静止，尚未连接或注入，等待位置报告。',event='approach_ready')
    current = readings(POSITIONS[q-1])
    task = task_shell('FM-E3-O3',index)
    task.public = {'time_s':clock('09:00'),'target':'K','readings':current,'max_steps':3,'state_fields':[],
        'instruction':f'已在接收平台K附近保持相对静止，定位登记暂不可用。当前平方斜距A＝{current["a_m2"]}m²、'
            f'B＝{current["b_m2"]}m²，结构侧向＝{current["side"]}。请报告实际接近单元。','actions':report_options()}
    task.initial = {'time_s':clock('09:00'),'reported_location':None,'connected':False,'transferred':False}
    task.world = {'map':mapping,'visits':visits,'current_location':location(names[q-1]),
                  'current_position_m':list(POSITIONS[q-1]),'current_readings':current}
    task.rubric = {'score':'100 for exact registered approach cell; no credit for only geometry or a mirror position'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['reported_location'] = operation['location']
        self.feedback = '接近位置报告已记录。'
        return 100 if operation['location'] == self.task.world['current_location'] else 0


def reconstruct(history,current):
    held,measured = {},{}
    positions,baseline,sides = None,None,None
    target = re.escape(current['target'])
    calibration = r'x/y=(-?\d+)/(-?\d+)m，平方斜距A=(\d+)、B=(\d+)m²，结构侧向(\+|-|轴上)。'
    for text in paragraphs(history):
        if match := re.match(rf'接收平台{target}附近有九个独立悬停接近单元，中心x取([\d/]+)m、y取([\d/−-]+)m的九种组合',text):
            x_values,y_values = (list(map(int,part.replace('−','-').split('/'))) for part in match.groups())
            positions = {(x,y) for x in x_values for y in y_values}
            reference = re.search(r'外部反射基准A=\(0,0\)、B=\((\d+),0\)m固定',text)
            if reference is None:
                raise ValueError('Public named range references must define the positive baseline')
            baseline = int(reference[1])
            if baseline <= 0 or f'a=x²+y²、b=(x−{baseline})²+y²' not in text:
                raise ValueError('Public squared-range equations must match the named references')
            orientation = re.search(r'沿A指向B基线，y>0为([+−])侧，y<0为([+−])侧，y=0为轴上',text)
            if orientation is None or orientation[1] == orientation[2]:
                raise ValueError('Public external orientation must distinguish the two sides')
            sides = tuple(value.replace('−','-') for value in orientation.groups())
            continue
        if match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})已实际在{target}-(N\d{{2}})悬停并完成全标定，{calibration}',text):
            visit,stamp,name,x,y,a,b,side = match.groups()
            held[visit] = {'location':name,'held_s':seconds(stamp)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})已实际在{target}-(N\d{{2}})悬停。',text):
            visit,stamp,name = match.groups()
            held[visit] = {'location':name,'held_s':seconds(stamp)}
            continue
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})目标{target}悬停实测并标定，{calibration}',text):
            visit,stamp,x,y,a,b,side = match.groups()
        else:
            continue
        measured[visit] = {'measured_s':seconds(stamp),'position_m':[int(x),int(y)],
                           'readings':{'a_m2':int(a),'b_m2':int(b),'side':side}}
    if len(held) != 9 or held.keys() != measured.keys():
        raise ValueError('All approach holds must have complete range and side calibrations')
    if positions is None or baseline is None or sides is None:
        raise ValueError('Approach geometry requires the public cell and reflector model')
    mapping = {}
    for visit,hold in held.items():
        data = measured[visit]
        x,y = data['position_m']
        expected = {'a_m2':x*x+y*y,'b_m2':(x-baseline)**2+y*y,'side':sides[0] if y > 0 else sides[1] if y < 0 else '轴上'}
        if hold['held_s'] != data['measured_s'] or expected != data['readings']:
            raise ValueError('Range and side calibration must describe the actual held geometry')
        mapping[hold['location']] = {key:data[key] for key in ('position_m','readings')}
    if len(mapping) != 9 or {tuple(r['position_m']) for r in mapping.values()} != positions:
        raise ValueError('The nine separated approach cells must all be registered')
    matches = [n for n,row in mapping.items() if row['readings'] == current['readings']]
    if len(matches) != 1:
        raise ValueError('Named range values and external oriented side must identify one approach cell')
    name = matches[0]
    return {'map':mapping,'current_location':name,'current_position_m':mapping[name]['position_m']}


def next_action(facts,current):
    return report_command(facts['current_location'])


def check_world(task,facts):
    if any(facts[key] != task.world[key] for key in facts):
        raise ValueError('Public range/side registration differs from the actual approach position')
    if task.world['current_readings'] != facts['map'][facts['current_location']]['readings']:
        raise ValueError('Actual current sensing differs from registered stable external geometry')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op['location'] == facts['current_location'] else 0)
