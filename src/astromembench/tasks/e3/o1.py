"""FM-E3-O1: one real supplementary scan at the same inspection sector."""
from copy import deepcopy
import re

from ..common import History, clock, selected_option, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds
from .locations import location, report_command, report_options
from ...environment import TaskRuntime
from ...schema import story_timestamp

CHANNELS = ('W','D','H')
MEASUREMENTS = ((10,2,5),(10,4,10),(10,6,15),(20,2,10),(20,4,15),(20,6,5),(30,2,15),(30,4,5),(30,6,10))
NAMES = {'A':(5,2,9,4,8,1,7,3,6),'B':(9,6,3,1,5,8,2,7,4),
         'C':(2,8,5,7,3,6,9,4,1),'D':(6,1,7,3,9,4,5,8,2)}
ORDERS = {'A':(4,8,1,6,2,9,5,3,7),'B':(7,2,6,9,5,1,8,4,3),
          'C':(3,6,8,1,7,4,9,2,5),'D':(8,5,2,7,4,3,1,9,6)}
VISITS = ('V62','V17','V43','V08','V71','V29','V54','V36','V95')
# Naming registration, actual sector, initially visible channels.
CONFIGS = (('A',5,'WD'),('B',2,'DH'),('C',9,'WH'),('B',7,'DH'),('B',9,'WD'),('C',4,'WH'),
           ('A',7,'W'),('B',6,'D'),('C',5,'H'),('A',3,'D'),('C',8,'W'),('D',7,'H'),
           ('B',8,'D'),('C',2,'W'),('D',1,'H'),('A',4,'D'))


def measured(i):
    return dict(zip(CHANNELS,MEASUREMENTS[i-1],strict=True))


def build(index):
    naming,i,visible = CONFIGS[index]
    names = NAMES[naming]
    history = History()
    history.add(1,'目标K外表有N01—N09九个巡检扇区，名称无顺序含义；环境、名称及扫描标定全题稳定，无新增损伤。'
        'W/D/H分别测接缝宽/凹槽深/凸台高，单位mm，精确无误差无容差。每个扇区三量均已实测；单通道各有三处重复，'
        '任意两个不同通道联合值都足以区分九扇区。设备正常，平台相对静止。'
        'A—I报告N01—N09，J报告无法确定；K/L/M分别原地补测W/D/H，所有选项固定显示。'
        '只准补测一次，历时1秒，只返回该通道真实数值，不移动或改环境；补测已知通道也耗额度。'
        '再次补测立即因超额度终止任务，不是格式错误。须报告完整位置N，报告随时可交且立即终局，无需解释。'
        '格式错误独立累计，第三次格式错误终局，不消耗或恢复补测额度；有效、无效及end总计最多4次调用。'
        'end直接放弃；推理与原生检索不计调用。',event='sector_localization_protocol')
    map_rows,visits = {},[]
    for j,(slot,visit) in enumerate(zip(ORDERS[naming],VISITS,strict=True)):
        name,readings = location(names[slot-1]),measured(slot)
        at,actual = 2+2*j,clock('12:00',119)+j*120
        map_rows[name] = readings
        visits.append({'visit':visit,'location':name,'arrived_s':actual,'scanned_s':actual,'readings_mm':readings})
        if index < 6:
            history.add(at,f'{visit}：{story_timestamp(actual)}实际到达K-{name}并驻留，同步采样W{readings["W"]}、'
                f'D{readings["D"]}、H{readings["H"]} mm。',occurred=actual,event='sector_survey',target='K',visit=visit,
                location=name,arrived_s=actual,scanned_s=actual,readings_mm=readings)
            history.add(at+1,'已完成的图像质量检查记录已归档。',event='closed_inspection_archive')
        else:
            history.add(at,f'{visit}：{story_timestamp(actual)}实际到达K-{name}并驻留。',occurred=actual,
                event='sector_arrival',target='K',visit=visit,location=name,arrived_s=actual)
            history.add(at+1,f'{visit}：{story_timestamp(actual)}目标K同次驻留同步采样，W{readings["W"]}、D{readings["D"]}、'
                f'H{readings["H"]} mm。',occurred=actual,event='sector_measurement',target='K',visit=visit,
                scanned_s=actual,readings_mm=readings)
    history.add(20,'K目标三个扫描通道标定正常，按约定精度读取，环境保持稳定。',event='scanner_verified',target='K')
    history.add(21,'已结束的一般巡检资料完成归档，无环境变化。',event='closed_inspection_archive')
    if index >= 12:
        for j,n in enumerate(names[::-1]):
            readings = measured(j+1)
            history.add(22,f'另一独立目标J的扇区{location(n)}已实测：W{readings["W"]}、D{readings["D"]}、'
                f'H{readings["H"]} mm；此登记属于J，J不属于K。',occurred=clock('13:00',119)+j*120,
                event='sector_survey',target='J',location=location(n),readings_mm=readings)
    history.add(23,'自动绕飞链路正常。',event='inspection_health')
    for at,n in ((24,9),(26,9),(27,4)):
        history.add(at,f'实际确认重访K-{location(n)}，没有新增扫描。'+('此后开始自主绕飞，不保留终点定位和完整移动量。' if at == 27 else ''),
            event='recent_sector',target='K',location=location(n),scanned=False)
    history.add(28,'自动绕飞已完成，没有终点定位记录。',event='inspection_motion_finished')
    history.add(29,'相对速度归零，平台已保持相对静止。',event='inspection_stationary')
    history.add(30,'三个扫描通道均可调用，当前可在原地补测一次，额外扫描不移动或改变环境。',event='inspection_ready')
    all_readings = measured(i)
    initial_readings = {c:all_readings[c] for c in visible}
    task = task_shell('FM-E3-O1',index)
    task.public = {'time_s':clock('09:00'),'target':'K','max_steps':4,'format_limit':3,'supplementary_scan_limit':1,
        'state_fields':['time_s','readings_mm','scans_used','format_attempts'],
        'instruction':'目标K巡检平台已保持相对静止，扇区定位暂不可用。当前扫描为'+
            '、'.join(f'{c}{v} mm' for c,v in initial_readings.items())+'。请报告当前所在扇区。',
        'actions':report_options()+[{'action':'select','option':letter,'operation':{'kind':'scan','channel':channel},
                                    'description':f'在同一静止扇区补测{channel}，耗用唯一一次补测额度，历时1秒。'}
                                   for letter,channel in zip('KLM',CHANNELS,strict=True)]}
    task.initial = {'time_s':clock('09:00'),'readings_mm':initial_readings,'scans_used':0,'format_attempts':0,
                    'reported_location':None,'scans':[]}
    task.world = {'map':map_rows,'visits':visits,'current_location':location(names[i-1]),'current_readings_mm':all_readings}
    task.rubric = {'score':'100 for the exact reported sector; any report path is accepted, at most one supplementary scan'}
    return history.finish(task)


class Runtime(TaskRuntime):
    def observation(self):
        result = super().observation()
        result.update(time_s=self.state['time_s'],current_time=story_timestamp(self.state['time_s']))
        return result

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        row = selected_option(self.actions(),action)
        if row is None:
            self.invalid()
            self.state['format_attempts'] += 1
            if self.state['format_attempts'] >= 3:
                self.end('invalid_limit')
            return
        op = row['operation']
        if op['kind'] == 'report':
            self.state['reported_location'] = op['location']
            correct = op['location'] == self.task.world['current_location']
            self.feedback = '扇区报告已记录。'
            self.end('completed',score=100 if correct else 0,full_credit=correct)
            return
        if self.state['scans_used']:
            self.feedback = '补测额度已用完。'
            self.end('scan_limit')
            return
        channel = op['channel']
        value = self.task.world['current_readings_mm'][channel]
        started = self.state['time_s']
        self.state['scans_used'] = 1
        self.state['time_s'] += 1
        self.state['readings_mm'][channel] = value
        self.state['scans'].append({'channel':channel,'value_mm':value,'started_s':started,'finished_s':started+1})
        self.feedback = f'通道{channel}；读数{value} mm'


def reconstruct(history,current):
    arrivals,readings = {},{}
    target = re.escape(current['target'])
    for text in paragraphs(history):
        if match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际到达{target}-(N\d{{2}})并驻留，同步采样W(\d+)、D(\d+)、H(\d+) mm。',text):
            visit,stamp,name,w,d,h = match.groups()
            arrivals[visit] = {'location':name,'arrived_s':seconds(stamp)}
            readings[visit] = {'readings_mm':dict(zip(CHANNELS,map(int,(w,d,h)),strict=True)),'scanned_s':seconds(stamp)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})实际到达{target}-(N\d{{2}})并驻留。',text):
            visit,stamp,name = match.groups()
            arrivals[visit] = {'location':name,'arrived_s':seconds(stamp)}
        elif match := re.fullmatch(rf'(V\d+)：({STORY_STAMP})目标{target}同次驻留同步采样，W(\d+)、D(\d+)、H(\d+) mm。',text):
            visit,stamp,w,d,h = match.groups()
            readings[visit] = {'readings_mm':dict(zip(CHANNELS,map(int,(w,d,h)),strict=True)),'scanned_s':seconds(stamp)}
    if len(arrivals) != 9 or arrivals.keys() != readings.keys():
        raise ValueError('All nine stationary sector visits must have their measurements')
    mapped = {}
    for visit,arrival in arrivals.items():
        if arrival['arrived_s'] != readings[visit]['scanned_s']:
            raise ValueError('Sector measurements must belong to the actual stationary visit')
        mapped[arrival['location']] = readings[visit]['readings_mm']
    if len(mapped) != 9:
        raise ValueError('Every sector must have a distinct registered name')
    for pair in (('W','D'),('W','H'),('D','H')):
        if len({tuple(row[c] for c in pair) for row in mapped.values()}) != 9:
            raise ValueError('Any two different channels must uniquely locate all sectors')
    return {'map':mapped}


def next_action(facts,current):
    readings = current['state']['readings_mm']
    candidates = [n for n,values in facts['map'].items() if all(values[c] == v for c,v in readings.items())]
    if len(candidates) == 1:
        facts['current_location'] = candidates[0]
        return report_command(candidates[0])
    if not candidates or current['state']['scans_used']:
        raise ValueError('Received scan does not provide a unique location within the observation budget')
    channel = next(c for c in CHANNELS if c not in readings)
    return {'action':'select','option':dict(zip(CHANNELS,'KLM',strict=True))[channel]}


def check_world(task,facts):
    if facts['map'] != task.world['map'] or facts['current_location'] != task.world['current_location']:
        raise ValueError('Registered sector or actual received scan differs from the physical world')
    if task.world['current_readings_mm'] != facts['map'][facts['current_location']]:
        raise ValueError('Supplementary scanner values differ from stable historical geometry')


def audit_cases(task,facts,solution):
    report = report_command(facts['current_location'])
    cases = [([{'action':'select','option':letter}],100 if letter == report['option'] else 0) for letter in 'ABCDEFGHIJ']
    for scan in 'KLM':
        command = {'action':'select','option':scan}
        cases.extend([([command,report],100),([{}, {},command,report],100),([command,{}, {},{}],0)])
        for repeated in 'KLM':
            cases.append(([command,{'action':'select','option':repeated}],0))
    cases.extend([([{},{}]+deepcopy(solution),100),([{}, {},{}],0)])
    return cases
