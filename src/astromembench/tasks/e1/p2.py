"""FM-E1-P2: compose three independently verified sample-core microprograms."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..experience import record_trial, reconstruct_trials
from ..prose import STORY_STAMP, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('A','124','STTS','TSTS',1,1,'STS'),
    ('A','124','TSST','STST',5,6,'TST'),
    ('B','421','STST','TSTS',4,2,'TTS'),
    ('B','421','TSTS','STST',6,8,'SST'),
    ('B','242','TSST','STTS',2,4,'STS'),
    ('B','242','STTS','TSST',6,8,'TST'),
    ('A','143','SSTT','TSTS',4,1,'STT'),
    ('A','143','TTSS','STST',7,5,'TSS'),
    ('A','131','STST','TSTS',3,1,'SSS'),
    ('A','131','TSTS','STST',7,8,'TTT'),
    ('B','424','SSTT','TTSS',4,2,'TST'),
    ('B','424','TTSS','SSTT',8,6,'STS'),
    ('B','341','SSTT','TSST',3,4,'TTS'),
    ('B','341','TTSS','STTS',7,5,'SST'),
    ('A','122','STSS','TSTT',1,2,'STT'),
    ('A','122','TSTT','STSS',5,6,'TSS'),
)
MACROS = ('SSS','SST','STS','STT','TSS','TST','TTS','TTT','SS-','ST-','TS-','TT-')
MATERIALS = {'1':'细粒干燥','2':'细粒湿润','3':'粗粒干燥','4':'粗粒湿润'}
PROGRAMS = {'S':'低速旋取','T':'脉冲压取','-':'跳过取芯，完成自动定位'}
JOBS = {'A':('J17','J04','J29','J11','J06','J23','J08','J15'),
        'B':('J31','J02','J19','J10','J27','J12','J21','J09')}


def build(index):
    head,layers,main,other,frequent,recent,correct = CONFIGS[index]
    programs = {head:dict(zip('1234',main,strict=True)),('B' if head == 'A' else 'A'):dict(zip('1234',other,strict=True))}
    history = History()
    history.add(1,'采样头A/B各有S低速旋取、T脉冲压取，名称不决定效果。材料1细粒干燥、2细粒湿润、3粗粒干燥、4粗粒湿润已由传感器分类。'
                '同一采样头与完整材料类别的验证结果可重复，不因另一头或条件的新试验而更新；每个条件S/T中一者保留完整芯，另一者只有碎屑。'
                '三层深0—2、2—4、4—6cm，每层需一个独立样芯，各自容器验收。低层自动清洗、换容器与定位，失败不污染或阻断其他层。'
                '三字符宏依次固定上中下层方法，末位-跳过第三层取芯，每层连定位和容器更换共2分钟，跳过仍占2分钟，总6分钟。'
                '每次历史试采使用独立见证样柱，前次碎屑不影响下次。所有十二宏都可执行，内部不提供反馈或中途改选。'
                '有效无效共3次，首个有效宏不可撤回并完成后结束，end放弃；推理与记忆检索不推进故事时间。',event='layer_sampling_protocol')
    layout = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'

    def trial(at,job,trial_head,material,method,start,style):
        finish = start+120
        accepted = int(method == programs[trial_head][material])
        condition = {'head':trial_head,'material':material,'material_name':MATERIALS[material]}
        record_trial(history,at,job=job,condition=condition,method=method,started_s=start,finished_s=finish,
                     result={'accepted_cores':accepted,'specimen':'完整样芯' if accepted else '碎屑'},layout=style,
                     description=f'{story_timestamp(start)}用{trial_head}头在{material}类{MATERIALS[material]}独立见证样柱执行{method}{PROGRAMS[method]}，2分钟完成',
                     result_text=f'{story_timestamp(finish)}取得{accepted}个完整可验收样芯'+('。' if accepted else '，仅有碎屑。'))

    for device in 'AB':
        for material in '1234':
            at = (3 if device == 'A' else 5)+(int(material)-1)*4
            for method_index,method in enumerate('ST'):
                local = (int(material)-1)*2+method_index
                order = ('AB'.index(device)*8)+local
                trial(at,JOBS[device][local],device,material,method,clock('10:00',119)+order*300,layout)
    for position,(at,reference,job) in enumerate(zip((21,23,25,27,29),(frequent,frequent,frequent,frequent,recent),
                                                   ('J41','J36','J43','J38','J45'),strict=True)):
        device = head if reference <= 4 else ('B' if head == 'A' else 'A')
        material = str((reference-1)%4+1)
        # The FM explicitly retains full condition/method/result in each F/L repeat receipt.
        trial(at,job,device,material,programs[device][material],clock('12:00',119)+position*300,'combined')
    history.add(30,'探头已就位，传感器已测得当前层序，等待一次完整采样命令。',event='column_ready')
    group = f'FM-E1-P2-pair{index//2+1:02d}'
    task = task_shell('FM-E1-P2',index,group=group,background_group=group,current_input_group=group)
    layer_data = [{'layer':i+1,'depth_start_cm':i*2,'depth_end_cm':(i+1)*2,'material':m,'material_name':MATERIALS[m]}
                  for i,m in enumerate(layers)]
    task.public = {'time_s':clock('09:00'),'head':head,'layers':layer_data,'required_cores':3,'equipment_ready':True,
                   'max_steps':3,'state_fields':[],'instruction':f'第120日09:00，当前采样头{head}；上中下层类别分别{list(layers)}，'
                   '深度依次0—2、2—4、4—6cm，需各取一个独立样芯，设备已就绪。执行一次完整采样。',
                   'actions':fixed_options([{'operation':{'macro':macro},'description':f'宏{macro}：'+ '；'.join(f'{i+1}层{PROGRAMS[p]}' for i,p in enumerate(macro))+'。'} for macro in MACROS])}
    task.initial = {'time_s':clock('09:00'),'depth_cm':0,'containers':[],'macro':None}
    task.world = {'programs':programs,'correct_operation':{'macro':correct}}
    task.rubric = {'score':'100 times the number of independently accepted layer cores divided by 3; skipped layers yield no core'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        macro = operation['macro']
        self.state['macro'] = macro
        accepted = 0
        for layer,method in zip(self.task.public['layers'],macro,strict=True):
            valid = method == self.task.world['programs'][self.task.public['head']][layer['material']]
            self.state['containers'].append({'layer':layer['layer'],'material':layer['material'],'method':method,
                                             'specimen':'empty' if method == '-' else 'core' if valid else 'debris',
                                             'accepted_cores':int(valid),'started_s':self.state['time_s'],'finished_s':self.state['time_s']+120})
            self.state['time_s'] += 120
            self.state['depth_cm'] = layer['depth_end_cm']
            accepted += valid
        self.feedback = '操作已执行，记录已存档。'
        return 100*accepted/3


def read_trial_description(text):
    match = re.fullmatch(rf'({STORY_STAMP})用([AB])头在([1-4])类(细粒干燥|细粒湿润|粗粒干燥|粗粒湿润)'
                         r'独立见证样柱执行([ST])(低速旋取|脉冲压取)，2分钟完成',text)
    if not match:
        raise ValueError('Missing actual sampling trial conditions and method in prose')
    return {'started_s':seconds(match[1]),'condition':{'head':match[2],'material':match[3],'material_name':match[4]},'method':match[5]}


def read_trial_result(text):
    match = re.fullmatch(rf'({STORY_STAMP})取得([01])个完整可验收样芯(。|，仅有碎屑。)',text)
    if not match or (match[2] == '0') != (match[3] == '，仅有碎屑。'):
        raise ValueError('Missing actual sample-core acceptance in prose')
    count = int(match[2])
    return {'finished_s':seconds(match[1]),'result':{'accepted_cores':count,'specimen':'完整样芯' if count else '碎屑'}}


def reconstruct(history,current):
    outcomes = {}
    for row in reconstruct_trials(history,read_trial_description,read_trial_result):
        condition = row['condition']
        key = (condition['head'],condition['material'],row['method'])
        accepted = row['result']['accepted_cores']
        if key in outcomes and outcomes[key] != accepted:
            raise ValueError('Repeated trial changed a stable sampling condition')
        outcomes[key] = accepted
    programs = {h:{} for h in 'AB'}
    for head in 'AB':
        for material in '1234':
            options = [method for method in 'ST' if outcomes[(head,material,method)] == 1]
            if len(options) != 1:
                raise ValueError('Each material/head must have exactly one empirically accepted program')
            programs[head][material] = options[0]
    macro = ''.join(programs[current['head']][row['material']] for row in current['layers'])
    return {'programs':programs,'correct_operation':{'macro':macro}}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Layer macro differs from the complete public head/material experiments')


def audit_cases(task,facts,solution):
    def score(operation):
        return 100*sum(method == facts['programs'][task.public['head']][layer['material']]
                       for layer,method in zip(task.public['layers'],operation['macro'],strict=True))/3
    return decision_cases(task,solution,score)
