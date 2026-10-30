"""FM-I1-D2: a real exposure follows the ordered composition of two prism stages."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

CALIBRATION = ((1,2,3),(2,1,3),(1,3,2))
CONFIGS = (
    ('D1',2,3,((8,'A1'),(26,'P:A0'))),
    ('D2',3,1,((9,'A2'),(25,'P:A1'))),
    ('D3',2,5,((7,'A1'),(18,'B1'),(27,'P:A2'))),
    ('D1',1,8,((7,'A1'),(18,'B2'),(27,'P:A0'))),
    ('D1',2,4,((7,'A2'),(18,'B1'),(27,'P:B0'))),
    ('D1',1,6,((8,'A1'),(20,'A0'),(27,'P:B2'))),
    ('D2',2,6,((4,'A1'),(12,'B2'),(22,'A0'),(28,'P:B0'))),
    ('D2',1,8,((4,'A2'),(12,'B1'),(22,'A1'),(28,'P:B2'))),
    ('D1',3,1,((4,'A2'),(12,'B1'),(22,'A0'),(28,'P:B0'))),
    ('D1',2,3,((4,'A1'),(10,'B1'),(18,'A2'),(26,'B0'))),
    ('D3',1,0,((4,'A2'),(12,'B2'),(22,'A1'),(28,'P:B1'))),
    ('D3',2,8,((4,'B1'),(9,'A1'),(15,'B0'),(21,'A2'),(28,'B1'))),
    ('D1',1,7,((6,'A2'),(13,'F:B1'),(23,'B1'),(28,'P:A0'))),
    ('D2',3,4,((6,'B2'),(13,'F:A1'),(23,'A1'),(28,'P:B0'))),
    ('D3',2,9,((5,'A1'),(14,'W:B2'),(25,'F:A0'))),
    ('D3',3,0,((4,'B1'),(10,'A1'),(18,'F:B2'),(26,'B0'))),
)


def detector(aperture,positions,calibration=CALIBRATION):
    intermediate = calibration[positions['A']][int(aperture[1])-1]
    return 'D'+str(calibration[positions['B']][intermediate-1])


def build(index):
    target,duration,rotation,events = CONFIGS[index]
    history = History()
    positions = {'A':0,'B':0}
    history.add(1,'三个入射孔I1/I2/I3的光线先通过实体棱镜滑块A，再通过B，最后到D1/D2/D3之一。A输出内部1/2/3固定接B输入1/2/3。'
        '每个滑块有0/1/2三个机械止挡，二者采用相同校准表：0位输入1/2/3分别到输出1/2/3；1位分别到2/1/3；2位分别到1/3/2。'
        '每个输入只对应一个输出，无分光、无损耗差异，同一时刻仅开一个入射孔。成功移动以实际止挡更新；失败保持回执明确的旧止挡；计划不移位。'
        '有警告时按明确实际到位结果处理。历史移位期间光闸关闭且不曝光；位置编号不代表优劣，不需其他光学常识。'
        '本阶段使用现有光路采集当前要求的探测器与秒数，不再移动A/B。每个入射孔可曝光1/2/3秒，另有关闭光闸并结束，共10项完整菜单。'
        '曝光打开所选入射孔相应秒数，生成实际接收探测器上的一帧并关闸；时长错误的曝光同样实际发生。关闭光闸不产生帧。'
        'select和字符串option提交或end放弃，总计最多3次含格式无效；首个有效动作立即执行并终止，不可重选。'
        '格式错误不曝光也不推进故事时刻，额外字段、数值型及范围外编号无效。',
        event='prism_protocol',calibration=[list(row) for row in CALIBRATION],propagation_order=['A','B'])
    history.add(2,'初始实体滑块A、B均在0位，光闸关闭。',event='prism_initial',positions=positions,shutter_closed=True)
    for at,code in events:
        status,move = code.split(':',1) if ':' in code else ('success',code)
        stage,destination = move[0],int(move[1])
        if status == 'P':
            history.add(at,f'计划将滑块{stage}移至{destination}止挡，尚未执行，实体位置不变，光闸继续关闭。',
                event='prism_plan',stage=stage,requested_position=destination,executed=False,shutter_closed=True)
            continue
        previous = positions[stage]
        success = status != 'F'
        if success:
            positions[stage] = destination
        description = (f'报告警告，但实际已从{previous}到达{destination}止挡' if status == 'W' else
                       f'实际成功从{previous}移至{destination}止挡' if success else
                       f'尝试移至{destination}失败且未移动，实际仍保持{previous}止挡')
        history.add(at,f'滑块{stage}{description}；整个移位期间光闸关闭，没有曝光。',event='prism_move',
            stage=stage,previous_position=previous,requested_position=destination,actual_position=positions[stage],
            success=success,warning=status == 'W',shutter_closed=True)
    history.add(30,'观测目标已入射，探测器正常、光闸关闭待曝光。',event='prism_exposure_ready',shutter_closed=True)
    entries = [{'description':f'{aperture}曝光{seconds}秒。','operation':{'kind':'expose','aperture':aperture,'duration_s':seconds}}
               for aperture in ('I1','I2','I3') for seconds in (1,2,3)]
    entries.append({'description':'关闭光闸并结束。','operation':{'kind':'close_shutter'}})
    task = task_shell('FM-I1-D2',index)
    task.public = {'time_s':clock('09:00'),'target_detector':target,'duration_s':duration,'max_steps':3,'state_fields':[],
                  'instruction':f'请向探测器{target}采集一帧{duration}秒曝光。',
                  'actions':fixed_options(entries[rotation:]+entries[:rotation])}
    task.initial = {'time_s':clock('09:00'),'positions':positions,'shutter_open':False,'frames':[]}
    task.world = {'positions':positions}
    task.rubric = {'score':'100 only for a frame physically received at the requested detector with exactly the requested exposure duration'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'close_shutter':
            self.state['shutter_open'] = False
            self.feedback = '光闸已关闭。'
            return 0
        aperture,duration = operation['aperture'],operation['duration_s']
        self.state['shutter_open'] = True
        started = self.state['time_s']
        receiver = detector(aperture,self.state['positions'])
        self.state['time_s'] += duration
        self.state['frames'].append({'frame':'F01','aperture':aperture,'detector':receiver,'duration_s':duration,
                                     'started_s':started,'ended_s':self.state['time_s']})
        self.state['shutter_open'] = False
        self.feedback = f'入射孔{aperture}的{duration}秒曝光已执行，光闸已关闭。'
        return 100 if receiver == self.task.public['target_detector'] and duration == self.task.public['duration_s'] else 0


def reconstruct(history,current):
    positions,calibration = {},None
    for text in paragraphs(history):
        if text.startswith('三个入射孔I1/I2/I3的光线'):
            order = re.search(r'先通过实体棱镜滑块([AB])，再通过([AB])，最后到D1/D2/D3之一。',text)
            if order is None or order.groups() != ('A','B'):
                raise ValueError('Physical light propagation must pass A then B')
            table = re.search(r'0位输入1/2/3分别到输出([123]/[123]/[123])；'
                r'1位分别到([123]/[123]/[123])；2位分别到([123]/[123]/[123])。',text)
            if table:
                calibration = [list(map(int,row.split('/'))) for row in table.groups()]
            continue
        match = re.fullmatch(r'初始实体滑块A、B均在([012])位，光闸关闭。',text)
        if match:
            positions = {'A':int(match[1]),'B':int(match[1])}
            continue
        match = re.fullmatch(r'滑块([AB])(?:实际成功从|报告警告，但实际已从)([012])(?:移至|到达)([012])止挡；'
            r'整个移位期间光闸关闭，没有曝光。',text)
        if match:
            stage,previous,actual = match.groups()
            if positions[stage] != int(previous):
                raise ValueError('Actual stage receipts must preserve movement causality and keep historical exposure closed')
            positions[stage] = int(actual)
            continue
        match = re.fullmatch(r'滑块([AB])尝试移至[012]失败且未移动，实际仍保持([012])止挡；'
            r'整个移位期间光闸关闭，没有曝光。',text)
        if match and positions[match[1]] != int(match[2]):
            raise ValueError('Actual stage receipts must preserve movement causality and keep historical exposure closed')
    if set(positions) != {'A','B'} or calibration != [list(row) for row in CALIBRATION]:
        raise ValueError('Both physical stage positions and the complete public calibration must be recoverable')
    return {'positions':positions,'calibration':calibration}


def next_action(facts,current):
    aperture = next(i for i in ('I1','I2','I3') if detector(i,facts['positions'],facts['calibration']) == current['target_detector'])
    return decision_command(current,{'kind':'expose','aperture':aperture,'duration_s':current['duration_s']})


def check_world(task,facts):
    if facts['positions'] != task.world['positions'] or facts['positions'] != task.initial['positions']:
        raise ValueError('Current installed prism positions differ from public physical receipts')


def audit_cases(task,facts,solution):
    def score(op):
        return 100 if (op['kind'] == 'expose' and op['duration_s'] == task.public['duration_s'] and
                       detector(op['aperture'],facts['positions'],facts['calibration']) == task.public['target_detector']) else 0
    return decision_cases(task,solution,score)
