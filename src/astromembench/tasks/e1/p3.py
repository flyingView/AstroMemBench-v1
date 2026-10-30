"""FM-E1-P3: independent outbound and return cargo vibration experiences."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..experience import record_trial, reconstruct_trials
from ..prose import STORY_STAMP, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('F1','R1','abc','uvwx',1,4,'a','u'),
    ('F1','R1','cba','uvwx',5,2,'c','u'),
    ('F2','R3','bac','wxvu',2,6,'a','v'),
    ('F2','R3','bca','wxvu',4,1,'c','v'),
    ('F1','R2','bca','vwux',1,5,'b','w'),
    ('F1','R2','acb','vwux',7,3,'a','w'),
    ('F3','R3','cba','wvux',3,6,'a','u'),
    ('F3','R3','abc','wvux',4,2,'c','u'),
    ('F1','R2','bac','uxvw',1,5,'b','x'),
    ('F1','R2','acb','uxvw',6,3,'a','x'),
    ('F2','R1','bca','xvwu',2,4,'c','x'),
    ('F2','R1','abc','xvwu',7,1,'b','x'),
    ('F1','R3','cba','vuxw',1,6,'c','x'),
    ('F1','R3','abc','vuxw',7,3,'a','x'),
    ('F3','R2','bca','wvxu',3,5,'a','v'),
    ('F3','R2','cab','wvxu',6,2,'b','v'),
)
SURFACES = {'F1':'平整硬面','F2':'细碎砾面','F3':'横向脊面','R1':'硬面','R2':'软垫铺面','R3':'纵向沟纹','R4':'颗粒混合'}
JOBS = ('J17','J04','J29','J11','J06','J23','J08','J15','J31','J02','J19','J10','J27',
        'J12','J21','J09','J34','J13','J25','J07','J30','J16','J28','J05','J22')


def _operation(outbound,returning):
    return {'outbound_mode':outbound,'return_mode':returning}


def build(index):
    outbound,returning,main,other,frequent,recent,correct_out,correct_back = CONFIGS[index]
    programs = {'outbound':dict(zip(('F1','F2','F3'),main,strict=True)),
                'return':dict(zip(('R1','R2','R3','R4'),other,strict=True))}
    history = History()
    history.add(1,'一次完整转运从基地到交接站再返回基地。去程3箱物资各2kg，返程2箱独立周转件各1kg，托架20kg，能源时间充足。'
                '去程F1平整硬面/F2细碎砾面/F3横向脊面，返程R1硬面/R2软垫铺面/R3纵向沟纹/R4颗粒混合，当前分类由侦察直接提供。'
                '去程a/b/c、返程u/v/w/x均为预置，字母不代表优劣；完整方向、载荷、路面条件的实测经验独立持续有效。'
                '每个去程条件只有一个模式使3箱冲击验收全部合格，其余0；返程只有一个模式使2箱合格，其余0。'
                '失败箱仍真实送到终点并卸货，不计合格交付，但不妨碍装载独立周转箱和完成返程。低层装卸自主完成，固定路线均可抵达。'
                '历史每次独立试运用新重置货箱、路线1km运行5分钟，不复用损坏箱；新条件经验不撤销旧条件。'
                '当前宏同时固定两段模式，去程5分钟，卸3箱装2箱1分钟，返程5分钟、终点卸货1分钟，共12分钟；中途不能按结果改选。'
                '有效无效共3次，首个有效宏执行完整往返后结束，end放弃；推理及检索不推进故事时间。',event='cargo_experience_protocol')
    layout = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'

    def trial(at,job,direction,surface,mode,start):
        count,mass = (3,2) if direction == 'outbound' else (2,1)
        accepted = count if mode == programs[direction][surface] else 0
        condition = {'direction':direction,'surface':surface,'surface_name':SURFACES[surface],'cargo_count':count,'unit_mass_kg':mass}
        record_trial(history,at,job=job,condition=condition,method=mode,started_s=start,finished_s=start+300,
                     result={'delivered_boxes':count,'accepted_boxes':accepted},layout=layout,
                     description=f'{story_timestamp(start)}，'+('去程' if direction == 'outbound' else '返程')+
                     f'{count}箱各{mass}kg，{surface}{SURFACES[surface]}，用{mode}模式独立试运1km',
                     result_text=f'{story_timestamp(start+300)}实际送达并交付{count}箱，其中冲击验收合格{accepted}箱。')

    ordinal = 0
    for direction,surfaces,alphabet,rounds in (('outbound',('F1','F2','F3'),'abc',(4,8,12)),
                                               ('return',('R1','R2','R3','R4'),'uvwx',(6,10,14,18))):
        for surface,at in zip(surfaces,rounds,strict=True):
            for mode in alphabet:
                trial(at,JOBS[ordinal],direction,surface,mode,clock('07:00',119)+ordinal*600)
                ordinal += 1
    for position,(at,reference,job) in enumerate(zip((22,24,26,29),(frequent,frequent,frequent,recent),('J41','J36','J43','J38'),strict=True)):
        direction = 'outbound' if reference <= 3 else 'return'
        surface = f'F{reference}' if reference <= 3 else f'R{reference-3}'
        trial(at,job,direction,surface,programs[direction][surface],clock('11:55',119)+position*600)
    history.add(30,'当前去程三箱已在基地装车，交接站两箱独立周转件等待返程接运，装载完成。',event='cargo_ready')
    group = f'FM-E1-P3-pair{index//2+1:02d}'
    task = task_shell('FM-E1-P3',index,group=group,background_group=group,current_input_group=group)
    task.public = {'time_s':clock('09:00'),'outbound_surface':outbound,'return_surface':returning,
                   'route':['基地','交接站','基地'],'outbound_cargo':{'boxes':3,'unit_mass_kg':2},'return_cargo':{'boxes':2,'unit_mass_kg':1},
                   'capacity_kg':20,'equipment_ready':True,'max_steps':3,'state_fields':[],
                   'instruction':f'第120日09:00，基地→交接站→基地固定路线。去程{outbound}{SURFACES[outbound]}，3箱各2kg；'
                   f'返程{returning}{SURFACES[returning]}，接回2箱独立周转件各1kg。设备正常，请执行一趟完整转运。',
                   'actions':fixed_options([{'operation':_operation(a,b),'description':f'去程减振{a}、返程托架{b}，执行完整转运。'} for a in 'abc' for b in 'uvwx'])}
    boxes = {f'outbound-{i}':{'location':'vehicle','mass_kg':2,'accepted':None} for i in range(1,4)}
    boxes.update({f'return-{i}':{'location':'交接站','mass_kg':1,'accepted':None} for i in range(1,3)})
    task.initial = {'time_s':clock('09:00'),'location':'基地','boxes':boxes,'cargo':[f'outbound-{i}' for i in range(1,4)],'journey':[]}
    task.world = {'programs':programs,'correct_operation':_operation(correct_out,correct_back)}
    task.rubric = {'score':'100 times accepted outbound and return boxes divided by 5, with both legs physically completed'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        start = self.state['time_s']
        outbound_ok = operation['outbound_mode'] == self.task.world['programs']['outbound'][self.task.public['outbound_surface']]
        return_ok = operation['return_mode'] == self.task.world['programs']['return'][self.task.public['return_surface']]
        self.state['journey'].append({'event':'depart','from':'基地','to':'交接站','time_s':start,'mode':operation['outbound_mode'],
                                      'cargo':list(self.state['cargo'])})
        self.state['location'] = '交接站'
        self.state['time_s'] = start+300
        self.state['journey'].append({'event':'arrive','location':'交接站','time_s':self.state['time_s']})
        for identifier in self.state['cargo']:
            self.state['boxes'][identifier].update(location='交接站',accepted=outbound_ok)
        self.state['cargo'] = [f'return-{i}' for i in range(1,3)]
        for identifier in self.state['cargo']:
            self.state['boxes'][identifier]['location'] = 'vehicle'
        self.state['time_s'] = start+360
        self.state['journey'].append({'event':'depart','from':'交接站','to':'基地','time_s':self.state['time_s'],'mode':operation['return_mode'],
                                      'cargo':list(self.state['cargo'])})
        self.state['location'] = '基地'
        self.state['time_s'] = start+660
        self.state['journey'].append({'event':'arrive','location':'基地','time_s':self.state['time_s']})
        for identifier in self.state['cargo']:
            self.state['boxes'][identifier].update(location='基地',accepted=return_ok)
        self.state['cargo'] = []
        self.state['time_s'] = start+720
        self.state['journey'].append({'event':'unloaded','location':'基地','time_s':self.state['time_s']})
        self.feedback = '操作已执行，记录已存档。'
        return 100*(3*int(outbound_ok)+2*int(return_ok))/5


def read_trial_description(text):
    match = re.fullmatch(rf'({STORY_STAMP})，(去程|返程)(\d+)箱各(\d+)kg，([FR]\d)([^，]+)，用([abcuvwx])模式独立试运1km',text)
    if not match:
        raise ValueError('Missing actual cargo trial conditions and mode in prose')
    return {'started_s':seconds(match[1]),'condition':{
        'direction':'outbound' if match[2] == '去程' else 'return','surface':match[5],'surface_name':match[6],
        'cargo_count':int(match[3]),'unit_mass_kg':int(match[4])},'method':match[7]}


def read_trial_result(text):
    match = re.fullmatch(rf'({STORY_STAMP})实际送达并交付(\d+)箱，其中冲击验收合格(\d+)箱。',text)
    if not match:
        raise ValueError('Missing actual cargo delivery and acceptance in prose')
    return {'finished_s':seconds(match[1]),'result':{'delivered_boxes':int(match[2]),'accepted_boxes':int(match[3])}}


def reconstruct(history,current):
    outcomes = {}
    for row in reconstruct_trials(history,read_trial_description,read_trial_result):
        c = row['condition']
        key = (c['direction'],c['surface'],c['cargo_count'],c['unit_mass_kg'],row['method'])
        accepted = row['result']['accepted_boxes']
        if key in outcomes and outcomes[key] != accepted:
            raise ValueError('Stable cargo condition has contradictory measured delivery results')
        if row['result']['delivered_boxes'] != c['cargo_count']:
            raise ValueError('Shock rejection must not erase physically delivered cargo')
        outcomes[key] = accepted
    programs = {'outbound':{},'return':{}}
    for direction,surfaces,alphabet,count,mass in (('outbound',('F1','F2','F3'),'abc',3,2),('return',('R1','R2','R3','R4'),'uvwx',2,1)):
        for surface in surfaces:
            valid = [method for method in alphabet if outcomes[(direction,surface,count,mass,method)] == count]
            if len(valid) != 1:
                raise ValueError('Each complete transport condition must have one fully accepted mode')
            programs[direction][surface] = valid[0]
    return {'programs':programs,'correct_operation':_operation(programs['outbound'][current['outbound_surface']],programs['return'][current['return_surface']])}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Transport macro differs from public independent outbound and return experiments')


def audit_cases(task,facts,solution):
    correct = facts['correct_operation']
    return decision_cases(task,solution,lambda op:100*(3*(op['outbound_mode'] == correct['outbound_mode'])+2*(op['return_mode'] == correct['return_mode']))/5)
