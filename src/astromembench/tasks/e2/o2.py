"""FM-E2-O2: local clearance revisions and one irreversible guided tool attempt."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

TOOLS = [{'tool':f'T{i}','width_cm':i+1,'height_cm':12-i} for i in range(1,11)]
# Target, initial K1/K2 (W,H), old tool, actual U/V, target final W/H.
CONFIGS = (
    (1,((3,10),(8,5)),2,((1,'W',6),),((1,'H',8),),(6,8)),
    (2,((4,9),(7,6)),6,((2,'H',10),),((1,'W',5),),(7,10)),
    (2,((6,7),(3,10)),2,((2,'W',5),),((2,'W',3),),(3,10)),
    (2,((8,5),(11,2)),10,((2,'H',4),),((2,'W',10),),(10,4)),
    (1,((5,8),(9,4)),4,((1,'H',11),),((1,'W',3),),(3,11)),
    (1,((10,3),(5,8)),9,((1,'H',5),),((1,'W',11),),(11,5)),
    (2,((5,8),(9,4)),8,((2,'H',7),(1,'W',3)),((2,'W',8),),(8,7)),
    (2,((2,11),(5,8)),4,((2,'W',9),),((2,'W',5),(1,'H',10)),(5,8)),
    (1,((11,2),(6,7)),10,((1,'H',6),),((1,'W',7),(2,'H',9)),(7,6)),
    (1,((3,10),(9,4)),2,((1,'W',6),),((1,'H',9),(2,'W',10)),(6,9)),
    (1,((5,8),(2,11)),4,((1,'H',6),),((1,'W',9),(2,'H',10)),(9,6)),
    (2,((6,7),(11,2)),10,((2,'W',8),),((2,'W',11),(1,'H',8)),(11,2)),
    (2,((9,4),(4,9)),3,((2,'H',5),(1,'W',10)),((2,'H',9),(1,'H',3)),(4,9)),
    (1,((2,11),(8,5)),1,((1,'H',6),(2,'W',7)),((1,'W',9),(2,'H',6)),(9,6)),
    (1,((8,5),(5,8)),7,((1,'W',3),(2,'H',7)),((1,'H',11),(2,'W',6)),(3,11)),
    (1,((4,9),(7,6)),3,((1,'H',3),(2,'W',9)),((1,'W',11),(2,'H',5)),(11,3)),
)


def build(index):
    target,initial,old,updates,final_updates,final = CONFIGS[index]
    station = f'K{target}'
    history,clearance = History(),{}

    def add(at,text,**facts):
        history.add(at,text,record_id=f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}',**facts)

    add(1,'K1/K2相距2m，固定导向口与周围结构相互独立，J1/J2在另一独立目标。每口后有旧紧固件B0与本轮B1。'
        '外部隔热毯边缘/挡片移动改变绝对净宽W与净高H，实际复测只更新对应工位的对应尺寸，未列尺寸保持，没有未记录变化。'
        '十头均可完成相同30N·m定扭，低层对准、换头、能源均正常，包络已含机械间隙；'
        '导轨键槽禁止旋转90度、倾斜或拆外壳，轴向深度/接触长度均足够。'
        '只有w≤W且h≤H才能通过完成B1，等号允许。否则触边限位停止、不产生隐含损伤，唯一作业机会仍被耗用。'
        '一个紧固件须完整处理才能验收，任何适合工具均可完成工作。全部十头加保持始终可选；'
        '有效/无效/end合计最多3次，首个合法选择结束，不准试探、另测或拆障。'
        '完整程序40秒，失败触边后也关闭余下机会；计划不生效，外区J不改K，推理/检索不推进故事时间。',
        event='clearance_protocol',tools=TOOLS)
    add(2,f'当前目标{station}-B1从未操作，初始未拧紧。{station}-B0用于不同旧周期，首次也未拧紧；工具库全部正常。',
        event='maintenance_assignment',station=station,current_fastener=station+'-B1',old_fastener=station+'-B0',tools_ready=True)

    def measure(at,area,dimension,value):
        key = (area,dimension)
        previous = clearance.get(key)
        if previous is None:
            cause = '激光初测'
        elif value < previous:
            cause = '外部挡片实际移入后激光复测'
        elif value > previous:
            cause = '外部挡片实际撤回后激光复测'
        else:
            cause = '再次激光实测保持'
        add(at,f'{area}：{cause}，绝对净{dimension}={value}cm。',event='clearance_measured',station=area,
            dimension=dimension,previous_cm=previous,clearance_cm=value)
        clearance[key] = value

    def old_maintenance(at,cycle):
        finish = clock(f'08:{at:02d}')
        if cycle == 2:
            add(at,f'{station}-B0已于{story_timestamp(finish-50)}由外部机构复位为未拧紧，只作用B0，与B1和净空无关。',
                occurred=finish-50,event='old_fastener_reset',fastener=station+'-B0',tightened=False)
        add(at,f'旧维护周期{cycle}：{story_timestamp(finish-40)}使用T{old}开始完整导轨维修，'
            f'{story_timestamp(finish)}完成{station}-B0的30N·m定扭；该周期结束。',occurred=finish,
            event='old_maintenance_completed',station=station,cycle=cycle,fastener=station+'-B0',tool=f'T{old}',
            started_s=finish-40,finished_s=finish,torque_nm=30,tightened=True)

    if index < 6:
        for area,values in enumerate(initial,1):
            for dimension,value in zip(('W','H'),values,strict=True):
                measure(3,f'K{area}',dimension,value)
        old_maintenance(6,1)
        old_maintenance(9,2)
        update_round,plan_round = 14,20
    else:
        for at,area,dimension in ((3,1,'W'),(5,2,'H'),(7,1,'H'),(9,2,'W')):
            measure(at,f'K{area}',dimension,initial[area-1][('W','H').index(dimension)])
        if index < 12:
            old_maintenance(11,1)
            old_maintenance(13,2)
            update_round,plan_round = 16,21
        else:
            old_maintenance(10,1)
            measure(12,station,'W',1)
            measure(14,station,'W',initial[target-1][0])
            old_maintenance(15,2)
            update_round,plan_round = 18,22
    for area,dimension,value in updates:
        measure(update_round,f'K{area}',dimension,value)
    add(plan_round,f'拟将{station}开口恢复至净宽{initial[target-1][0]}cm、净高{initial[target-1][1]}cm，尚未实施。',
        event='clearance_plan',station=station,planned_dimensions_cm=dict(zip(('W','H'),initial[target-1],strict=True)),implemented=False)
    for area,dimension,value in final_updates:
        measure(24,f'K{area}',dimension,value)
    for dimension,value in zip(('W','H'),initial[target-1],strict=True):
        measure(28,f'J{target}',dimension,value)
    add(30,f'已定位{station}-B1，工具库就绪，等待本轮维修。',event='maintenance_ready',fastener=station+'-B1',tools_ready=True)
    task = task_shell('FM-E2-O2',index)
    task.public = {'time_s':clock('09:00'),'station':station,'fastener':station+'-B1','tools':TOOLS,'tools_ready':True,
        'guided_fit_rule':'width_cm <= W and height_cm <= H; no rotation, tilt or disassembly','max_steps':3,'state_fields':[],
        'instruction':f'任务第120日09:00；工位{station}-B1；工具库就绪。请完成此紧固件的定扭维修。',
        'actions':fixed_options([{'operation':{'kind':'repair','tool':t['tool']},
            'description':f'以{t["tool"]}（宽{t["width_cm"]}cm、高{t["height_cm"]}cm）完整定扭维修B1。'} for t in TOOLS]+
            [{'operation':{'kind':'hold'},'description':'保持，不维修。'}])}
    task.initial = {'time_s':clock('09:00'),'fastener':station+'-B1','tightened':False,'torque_nm':0,'damaged':False,
                    'opportunity_used':False,'attempts':[]}
    task.world = {'clearance':{f'K{i}':{d:clearance[f'K{i}',d] for d in ('W','H')} for i in (1,2)},
                  'target_clearance':dict(zip(('W','H'),final,strict=True))}
    task.rubric = {'score':'100 exactly when the chosen tool fits both inclusive fixed-orientation dimensions and completes B1'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，不维修，操作结束。'
            return 0
        tool = next(t for t in self.task.public['tools'] if t['tool'] == operation['tool'])
        clearance = self.task.world['target_clearance']
        blocked = [dimension for dimension,size in (('W',tool['width_cm']),('H',tool['height_cm'])) if size > clearance[dimension]]
        fits = not blocked
        start = self.state['time_s']
        self.state['attempts'].append({'tool':tool['tool'],'started_s':start,'finished_s':start+40,
                                      'blocked_dimensions':blocked,'passed_guide':fits,'completed':fits})
        self.state.update(time_s=start+40,opportunity_used=True,tightened=fits,torque_nm=30 if fits else 0)
        self.feedback = f'已执行{tool["tool"]}的预置维修过程，操作记录已归档。'
        return 100 if fits else 0


def reconstruct(history,current):
    clearance,old_tightened = {'K1':{},'K2':{}},set()
    for text in paragraphs(history):
        measurement = re.fullmatch(r'(K[12])：(激光初测|外部挡片实际移入后激光复测|外部挡片实际撤回后激光复测|再次激光实测保持)，'
                                   r'绝对净([WH])=(\d+)cm。',text)
        if measurement:
            area,cause,dimension,printed = measurement.groups()
            value,previous = int(printed),clearance[area].get(dimension)
            if ((cause == '激光初测' and previous is not None)
                    or (cause == '再次激光实测保持' and previous != value)
                    or (cause == '外部挡片实际移入后激光复测' and (previous is None or value >= previous))
                    or (cause == '外部挡片实际撤回后激光复测' and (previous is None or value <= previous))):
                raise ValueError('Each actual clearance update must preserve the prior local dimension')
            clearance[area][dimension] = value
        reset = re.fullmatch(rf'(K[12])-B0已于{STORY_STAMP}由外部机构复位为未拧紧，只作用B0，与B1和净空无关。',text)
        if reset:
            old_tightened.discard(reset[1])
        maintenance = re.fullmatch(rf'旧维护周期\d+：{STORY_STAMP}使用(T\d+)开始完整导轨维修，'
                                   rf'{STORY_STAMP}完成(K[12])-B0的30N·m定扭；该周期结束。',text)
        if maintenance:
            tool = next(t for t in current['tools'] if t['tool'] == maintenance[1])
            area = maintenance[2]
            values = clearance[area]
            if area in old_tightened or tool['width_cm'] > values['W'] or tool['height_cm'] > values['H']:
                raise ValueError('Old maintenance needs an untightened B0 and then-current physical clearance')
            old_tightened.add(area)
    return {'clearance':clearance,'target_clearance':clearance[current['station']]}


def next_action(facts,current):
    values = facts['target_clearance']
    tool = next(t for t in current['tools'] if t['width_cm'] <= values['W'] and t['height_cm'] <= values['H'])
    return decision_command(current,{'kind':'repair','tool':tool['tool']})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Current guide clearance differs from the actual local history')


def audit_cases(task,facts,solution):
    values = facts['target_clearance']
    def score(operation):
        if operation['kind'] == 'hold':
            return 0
        tool = next(t for t in task.public['tools'] if t['tool'] == operation['tool'])
        return 100 if tool['width_cm'] <= values['W'] and tool['height_cm'] <= values['H'] else 0
    return decision_cases(task,solution,score)
