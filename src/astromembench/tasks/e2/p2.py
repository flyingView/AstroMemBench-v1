"""FM-E2-P2: local absolute overburden revisions and two isolated marker cores."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Target region, initial K1/K2/K3, two actual local updates, unexecuted plan, final target depth.
CONFIGS = (
    (3,(0,4,7),((3,8),),((1,5),),2,8),
    (1,(5,9,2),((1,3),),((1,5),),4,5),
    (2,(8,1,6),((2,0),),((3,2),),3,0),
    (1,(7,2,5),((1,9),),((2,8),),0,9),
    (3,(9,5,2),((3,4),),((1,1),),8,4),
    (2,(2,4,7),((2,5),),((3,9),),0,5),
    (1,(3,8,6),((1,6),(3,4)),((1,2),),7,2),
    (2,(0,6,9),((2,3),(1,8)),((2,6),),1,6),
    (3,(2,9,6),((3,8),(1,5)),((3,0),),4,0),
    (2,(4,7,1),((2,9),(3,6)),((1,0),),3,9),
    (1,(6,2,8),((1,3),(2,7)),((1,6),),9,6),
    (3,(7,6,5),((3,4),(2,2)),((1,9),),0,4),
    (1,(2,7,5),((1,6),(2,4)),((1,3),(3,0)),8,3),
    (3,(6,1,8),((3,2),(1,9)),((3,8),(2,5)),4,8),
    (2,(8,5,0),((2,9),(3,4)),((2,1),(1,3)),6,1),
    (1,(9,3,2),((1,1),(3,6)),((1,0),(2,5)),4,0),
)


def build(index):
    target,initial,updates,final_updates,plan,correct = CONFIGS[index]
    region = f'K{target}'
    history = History()
    depths = {}

    def add(at,text,**facts):
        identifier = f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}'
        history.add(at,text,record_id=identifier,**facts)

    add(1,'K1/K2/K3为相隔20m的均质小样区，各区C/W1/W2相距1m且原生层位相同；列出的沉积与清理均匀作用于同区三点。'
        '区间相互独立，邻区J1/J2/J3属于另一组独立地层。覆层h为0—9整数cm，标志层恰为当前表面以下[h,h+2)cm，'
        '上方外来覆土，下方另一基底。实际剖面复测直接给绝对h，只更新该区，持续到下一次实际复测；计划不改变h，没有未记录变化。'
        'D0—D9完整预置先旁路排出前d厘米，再将[d,d+1)、[d+1,d+2)两枚1cm样芯分别密封后收回。'
        '胶囊互不混样，旁路不污染后续样芯，端点接触不混入，完整包含于标志层才验收。目标两枚纯样芯，按每枚50计完成量。'
        '设备、定位、钻头和密封始终正常，支持最大终深11cm。一次采样耗40秒、消耗两枚胶囊并扰动该点，不可撤销或重取。'
        '有效无效及end合计3次，首个合法操作结束，保持或end不取芯；推理与记忆检索不推进故事时间。',event='marker_sampling_protocol')
    add(2,f'本次指定{region}-C；旧作业仅在{region}-W1/W2，各点独立且各只取一次。C从未钻过；'
        '旧见证点各用两枚旧胶囊并独立归档，本次另备两枚新胶囊。设备、耗材与定位正常。',
        event='sampling_assignment',target_region=region,current_point=region+'-C',witness_points=[region+'-W1',region+'-W2'],new_capsules=2)

    def measure(at,area,new):
        old = depths.get(area)
        if old is None:
            cause = '完成初始剖面测量'
        elif new > old:
            cause = '外来松散物已均匀沉积，剖面复测'
        elif new < old:
            cause = '清理已实际完成，剖面复测'
        else:
            cause = '实际复测确认覆层保持'
        add(at,f'{area}：{cause}，'+('' if old is None else f'原h={old}cm，')+f'新绝对h={new}cm，作用于本区C/W1/W2。',
            event='profile_measured',region=area,previous_h_cm=old,h_cm=new,scope_points=[area+'-C',area+'-W1',area+'-W2'])
        depths[area] = new

    def old_sample(at,witness):
        depth = initial[target-1]
        finish = clock(f'08:{at:02d}')
        point = f'{region}-W{witness}'
        add(at,f'{point}：从{story_timestamp(finish-40)}开始执行D{depth}，于{story_timestamp(finish)}完成并自动收回；'
            '两枚独立旧胶囊均为纯标志层样芯，已归档，孔仅扰动该见证点。',occurred=finish,event='witness_sampling_completed',
            point=point,region=region,program=f'D{depth}',depth_cm=depth,started_s=finish-40,finished_s=finish,
            capsules=[{'id':point+f'-{j+1}','interval_cm':[depth+j,depth+j+1],'material':'marker','accepted':True} for j in range(2)])

    rounds = (3,3,3) if index < 6 else (3,6,9) if index < 12 else (3,5,7)
    for i,(at,depth) in enumerate(zip(rounds,initial,strict=True),1):
        measure(at,f'K{i}',depth)
    if index < 6:
        old_sample(6,1)
        old_sample(9,2)
        update_round,plan_round = 14,20
    elif index < 12:
        old_sample(11,1)
        old_sample(13,2)
        update_round,plan_round = 16,20
    else:
        old_sample(8,1)
        measure(10,region,initial[target-1]+1 if initial[target-1] < 9 else 8)
        measure(12,region,initial[target-1])
        old_sample(15,2)
        update_round,plan_round = 18,22
    for area,depth in updates:
        measure(update_round,f'K{area}',depth)
    add(plan_round,f'提出将{region}清理或铺覆至h={plan}cm的计划，尚未开工、没有实际剖面复测。',
        event='profile_plan',region=region,planned_h_cm=plan,implemented=False)
    for area,depth in final_updates:
        measure(24,f'K{area}',depth)
    measure(28,f'J{target}',plan)
    add(30,f'{region}-C已定位，两枚新胶囊就绪，等待本点采样。',event='marker_sampling_ready',point=region+'-C',capsules_ready=2)
    task = task_shell('FM-E2-P2',index)
    task.public = {'time_s':clock('09:00'),'location':region+'-C','target_region':region,'capsules_ready':2,'equipment_ready':True,
                   'max_steps':3,'state_fields':[],'instruction':f'任务第120日09:00；当前位置{region}-C；两枚胶囊就绪；请完成该点的标志层取芯。',
                   'actions':fixed_options([{'operation':{'kind':'sample','depth_cm':d},
                                            'description':f'D{d}：旁路前{d}cm，独立密封获取[{d},{d+1})与[{d+1},{d+2})cm两枚样芯后自动收回。'} for d in range(10)]+
                                           [{'operation':{'kind':'hold'},'description':'保持，不取芯。'}])}
    task.initial = {'time_s':clock('09:00'),'point':region+'-C','point_disturbed':False,'unused_capsules':2,
                    'capsules':[],'drill_depth_cm':0,'maximum_depth_cm':0}
    task.world = {'depths':{f'K{i}':depths[f'K{i}'] for i in range(1,4)},'target_depth_cm':correct}
    task.rubric = {'score':'50 per independently sealed one-centimetre core wholly inside the actual half-open marker layer'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，不取芯，操作结束。'
            return 0
        depth,h = operation['depth_cm'],self.task.world['target_depth_cm']
        for i in range(2):
            start,end = depth+i,depth+i+1
            material = 'overburden' if end <= h else 'substrate' if start >= h+2 else 'marker'
            self.state['capsules'].append({'id':self.state['point']+f'-{i+1}','interval_cm':[start,end],
                                           'sealed':True,'material':material,'accepted':h <= start and end <= h+2})
        self.state.update(point_disturbed=True,unused_capsules=0,maximum_depth_cm=depth+2,drill_depth_cm=0)
        self.state['time_s'] += 40
        self.feedback = f'已执行D{depth}，两枚胶囊已收回并归档。'
        return 50*sum(c['accepted'] for c in self.state['capsules'])


def reconstruct(history,current):
    depths = {}
    for text in paragraphs(history):
        measurement = re.fullmatch(r'(K\d+)：(?:完成初始剖面测量|外来松散物已均匀沉积，剖面复测|清理已实际完成，剖面复测|实际复测确认覆层保持)，'
                                   r'(?:原h=(\d+)cm，)?新绝对h=(\d+)cm，作用于本区C/W1/W2。',text)
        if measurement:
            region,previous,depth = measurement.groups()
            if (int(previous) if previous is not None else None) != depths.get(region):
                raise ValueError('Local profile chronology must retain the previous actual absolute depth')
            depths[region] = int(depth)
        witness = re.fullmatch(rf'(K\d+)-W[12]：从{STORY_STAMP}开始执行D(\d+)，于{STORY_STAMP}完成并自动收回；'
                               r'两枚独立旧胶囊均为纯标志层样芯，已归档，孔仅扰动该见证点。',text)
        if witness and int(witness[2]) != depths[witness[1]]:
            raise ValueError('Old witness sampling must actually have used the then-current marker layer')
    return {'depths':depths,'target_depth_cm':depths[current['target_region']]}


def next_action(facts,current):
    return decision_command(current,{'kind':'sample','depth_cm':facts['target_depth_cm']})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Current marker layer differs from actual local profile revisions')


def audit_cases(task,facts,solution):
    h = facts['target_depth_cm']
    def score(operation):
        if operation['kind'] == 'hold':
            return 0
        d = operation['depth_cm']
        return 50*sum(h <= d+i and d+i+1 <= h+2 for i in range(2))
    return decision_cases(task,solution,score)
