"""FM-E2-D1: local directional-field revisions and physical circular shielding."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Old orientation and explicit final nonzero directional contributions (all others measured zero).
CONFIGS = (
    (0,{1:3,2:5,6:7}), (7,{7:4,8:6,2:8}), (9,{0:5,1:5,5:9}),
    (5,{4:3,5:4,9:6}), (6,{9:4,0:5,4:8}), (0,{5:6,6:4,0:8}),
    (6,{2:3,3:6,7:8}), (8,{8:5,9:5,3:9}), (3,{0:4,1:6,6:9}),
    (7,{6:3,7:5,2:7}), (2,{9:5,0:4,5:8}), (1,{7:4,8:5,3:8}),
    (0,{2:5,3:5,7:6,8:4}), (4,{4:3,5:6,9:5,0:4}),
    (7,{3:6,4:4,8:5,9:5}), (9,{9:4,0:6,4:7,5:2}),
)
MODEL = {'direction_ring':list(range(10)),'covered':'j and (j+1) mod 10','duration_s':60,
         'internal_background_mgy':1,'dose_mgy':'1 + sum(f) - f[j] - f[(j+1) mod 10]',
         'objective':'maximize external dose avoided relative to the best attainable adjacent pair'}


def build(index):
    old,nonzero = CONFIGS[index]
    initial = {old:4,(old+1)%10:6}
    final = [nonzero.get(i,0) for i in range(10)]
    history,field = History(),{}

    def add(at,text,**facts):
        history.add(at,text,record_id=f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}',**facts)

    add(1,'惯性方向0—9等角成环，9与0相邻，转姿不重编号；外侧探头读数不受遮蔽板或所选姿态影响。'
        'K为当前空间邻域，J为不同邻域，各方向同号也不共享。姿态、板、推进、能源正常，所有姿态均满足通信、供电与导航，无隐藏限制。'
        '每方向f≥0是固定60秒巡航段的外部剂量贡献mGy/段，实际测量给绝对值，仅更新列出的本地方向，其余保持。'
        'Gj覆盖j及(j+1)mod10，覆盖贡献为0，其余相加，再加不可遮蔽内部1mGy；没有健康损伤门槛。'
        '一次合法G瞬时切入姿态、执行完整60秒且累计真实剂量，目标是尽量减少本段实际接收的外部剂量。'
        '不需遮完所有方向，旧累计剂量不影响本段遮蔽能力。'
        'G0—G9加保持共11项始终可选；有效/无效/end合计3次，首合法即终局，不能试转测场、半段或重试。'
        '计划不能改变外部粒子场，没有未记录变化；推理/检索不推进故事时钟。',event='directional_shielding_protocol',model=MODEL)
    add(2,'当前空间邻域K，巡航系统全部正常；本次60秒计量段尚未开始，旧段独立归档。',
        event='cruise_assignment',region='K',equipment_ready=True,current_segment_started=False)

    def measure(at,region,directions,values):
        for direction in directions:
            value = values.get(direction,0)
            previous = field.get((region,direction))
            cause = '稳态初测' if previous is None else '外部粒子场扰动已发生后完成相应方向实际复测'
            add(at,f'{region}-{direction}：{cause}，绝对贡献{value}mGy/段，未列方向保持上次实测。',
                event='direction_measured',region=region,direction=direction,previous_mgy=previous,contribution_mgy=value)
            field[region,direction] = value

    def old_cruise(at,segment):
        finish = clock(f'08:{at:02d}')
        dose = 1+sum(field['K',i] for i in range(10))-field['K',old]-field['K',(old+1)%10]
        add(at,f'空间邻域K旧段{segment}从{story_timestamp(finish-60)}以G{old}切入计量，至{story_timestamp(finish)}完成60秒巡航；'
            f'该段实际剂量{dose}mGy，已归档且结束。',occurred=finish,event='old_cruise_completed',region='K',segment=segment,
            orientation=old,started_s=finish-60,finished_s=finish,dose_mgy=dose)

    if index < 6:
        measure(3,'K',range(10),initial)
        old_cruise(6,'H1')
        old_cruise(9,'H2')
        update_round,plan_round = 14,20
    elif index < 12:
        measure(3,'K',range(5),initial)
        measure(7,'K',range(5,10),initial)
        old_cruise(10,'H1')
        old_cruise(13,'H2')
        update_round,plan_round = 16,21
    else:
        for at,directions in ((3,range(3)),(5,range(3,7)),(7,range(7,10))):
            measure(at,'K',directions,initial)
        old_cruise(9,'H1')
        shifted = (old+4)%10
        measure(11,'K',range(10),{shifted:4,(shifted+1)%10:6})
        measure(13,'K',range(10),initial)
        old_cruise(15,'H2')
        update_round,plan_round = 18,22
    measure(update_round,'K',range(5),nonzero)
    add(plan_round,f'拟等待外部粒子场恢复为方向{old}贡献4、方向{(old+1)%10}贡献6、其余0后，后续航段重新使用G{old}。'
        '目前尚无恢复实测，本计划不对粒子场产生作用。',event='cruise_plan',region='K',future_orientation=old,
        awaited_field_mgy=[initial.get(i,0) for i in range(10)],restoration_observed=False)
    measure(24,'K',range(5,10),nonzero)
    measure(28,'J',range(10),initial)
    add(30,'空间邻域K本段巡航就绪，计量尚未开始。',event='cruise_ready',region='K')
    task = task_shell('FM-E2-D1',index)
    task.public = {'time_s':clock('09:00'),'region':'K','shielding_model':MODEL,'max_steps':3,'state_fields':[],
        'instruction':'任务第120日09:00；空间邻域K；巡航系统就绪。请执行下一段60秒巡航。',
        'actions':fixed_options([{'operation':{'kind':'cruise','orientation':j},
            'description':f'G{j}：覆盖方向{j}/{(j+1)%10}，完整执行60秒巡航。'} for j in range(10)]+
            [{'operation':{'kind':'hold'},'description':'保持，不执行本段。'}])}
    task.initial = {'time_s':clock('09:00'),'orientation':None,'completed_segments':0,'segment_dose_mgy':0,
                    'historical_dose_mgy':2,'accumulated_dose_mgy':2,'external_dose_avoided_mgy':0}
    task.world = {'field_mgy':final,'historical_dose_mgy':2}
    task.rubric = {'score':'100 times the actual external dose avoided divided by the maximum attainable adjacent-pair protection'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，本段未执行。'
            return 0
        j,field = operation['orientation'],self.task.world['field_mgy']
        protected = field[j]+field[(j+1)%10]
        dose = 1+sum(field)-protected
        self.state.update(time_s=self.state['time_s']+60,orientation=j,completed_segments=1,
                          covered_directions=[j,(j+1)%10],segment_dose_mgy=dose,external_dose_avoided_mgy=protected)
        self.state['accumulated_dose_mgy'] += dose
        self.feedback = f'已按G{j}完成本段巡航，剂量记录已归档。'
        return 100*protected/max(field[i]+field[(i+1)%10] for i in range(10))


def reconstruct(history,current):
    field,dose = {},0
    for text in paragraphs(history):
        measurement = re.fullmatch(r'([KJ])-([0-9])：(稳态初测|外部粒子场扰动已发生后完成相应方向实际复测)，'
                                   r'绝对贡献(\d+)mGy/段，未列方向保持上次实测。',text)
        if measurement and measurement[1] == current['region']:
            i = int(measurement[2])
            if (measurement[3] == '稳态初测') != (i not in field):
                raise ValueError('Directional field revisions must retain the prior local contribution')
            field[i] = int(measurement[4])
        cruise = re.fullmatch(rf'空间邻域([KJ])旧段H\d+从{STORY_STAMP}以G([0-9])切入计量，'
                              rf'至{STORY_STAMP}完成60秒巡航；该段实际剂量(\d+)mGy，已归档且结束。',text)
        if cruise and cruise[1] == current['region']:
            j = int(cruise[2])
            expected = 1+sum(field.values())-field[j]-field[(j+1)%10]
            if expected != int(cruise[3]):
                raise ValueError('Historical dose must follow the field during the old actual cruise')
            dose += expected
    return {'field_mgy':[field[i] for i in range(10)],'historical_dose_mgy':dose}


def next_action(facts,current):
    field = facts['field_mgy']
    j = max(range(10),key=lambda i:field[i]+field[(i+1)%10])
    return decision_command(current,{'kind':'cruise','orientation':j})


def check_world(task,facts):
    if facts != task.world or facts['historical_dose_mgy'] != task.initial['historical_dose_mgy']:
        raise ValueError('Directional field and prior physical dose must match actual history')


def audit_cases(task,facts,solution):
    field = facts['field_mgy']
    adjacent = [field[i]+field[(i+1)%10] for i in range(10)]
    def score(operation):
        return 0 if operation['kind'] == 'hold' else 100*adjacent[operation['orientation']]/max(adjacent)
    return decision_cases(task,solution,score)
