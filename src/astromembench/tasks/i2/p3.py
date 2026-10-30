"""FM-I2-P3: conserved cargo counts, lateral moment, and one locked delivery."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

CONFIGS = (
    ('A',('+L3','+R1','+C1')),('C',('+L2','+R2','+C1')),('C',('+L1','+R5','+C1')),
    ('C',('+L6','+R1','+C1')),('B',('+L2','+R1','+C3')),('A',('+L1','+R2','+C3')),
    ('C',('+L1','+R4','+C1','R>L1')),('A',('+L5','+R1','-L1','+C1')),
    ('B',('+L1','+R5','-R2','+C2')),('C',('+L2','+R2','+C3','C>L2')),
    ('B',('+L5','+R1','+C1','R>C1')),('B',('+L2','+R3','+C1','L>R1')),
    ('B',('+L5','+R1','L>C1','0R','+L1','+C1')),('C',('+L1','+R4','R>C1','0L','+R2','+C1')),
    ('A',('+L4','+R4','R>L1','0L','-L2','+C1')),('B',('+L3','+R1','L>R1','0R','+C2','C>L2')),
)
POSITIONS = (1,-3,4,-4,2,-1,5,-2,3,0)
# U's actual L load and V's actual R load; separate vehicles do not cancel.
OTHER_CAR_LOADS = (
    (2,1),(1,3),(3,1),(1,2),(1,3),(4,1),(3,1),(1,4),
    (2,1),(2,3),(1,3),(3,1),(1,2),(4,1),(1,3),(3,1),
)
PLAN_DESTINATIONS = ('L','R','L','R','R','L','R','L','L','R')


def transfer(bins,source,destination,requested,actual):
    if not 0 <= actual <= requested:
        raise ValueError('Moved cargo cannot exceed the requested number of whole boxes')
    if source != 'external' and bins[source] < requested:
        raise ValueError('Historical unloading and transfers require enough source boxes')
    if destination != 'external' and bins[destination]+requested > 6:
        raise ValueError('Historical loading requests must fit the destination bin')
    if source != 'external':
        bins[source] -= actual
    if destination != 'external':
        bins[destination] += actual


def quality(bins,position):
    mass = 4+2*sum(bins.values())+2
    moment = 2*(bins['R']-bins['L'])+2*position
    center = moment/mass
    return 0 if mass > 26 or abs(center) > .5 else 100*(1-abs(center)/.5)


def build(index):
    target,codes = CONFIGS[index]
    u,v = ['ABC'[('ABC'.index(target)+offset)%3] for offset in (1,2)]
    bins = {car:dict.fromkeys(('L','C','R'),0) for car in 'ABC'}
    history = History()
    history.add(1,'三辆独立载车A/B/C初始全空，空车各4kg且重心在x=0；每个密封标准货箱2kg，不拆分。'
        '旧货左L、中C、右R仓横向坐标为−1、0、+1dm，每仓最多6箱。'
        '装入/卸出按回执的本次实际箱数更新；车内移载在源仓扣除并在目标仓增加同量，不改变总质量。'
        '部分执行按实际量，失败0不重置；计划、仅发请求、吊钩回位均不改变已放下的货箱。'
        '外部库可提供请求的箱并接收卸出箱。当前追加一个2kg箱，独立平衡轨有−4至5dm十个空固定位，'
        '它与旧三仓空间分离，±1位置也不会覆盖旧货。所有位置均可选；总质量上限26kg含空车。'
        '任务是将追加箱交付，同时尽量使横向重心位于0；偏离至绝对值0.5dm稳定性收益降至0，超过即质量不合格。'
        '这是本题简化模型。位置准确执行，合法选择即锁定、10秒装载后按预置路线和车速运输60秒到固定交接点；'
        '质量不合格也不会另行假设翻车或丢箱。无免费称重或重心读数、试放或等待改善分布。'
        '提交select和字符串option或end，最多3次总调用含格式错误与最终合法选择；额外字段、数值型或范围外编号无效。'
        '首次合法选择终止，不能重新放置。',event='cargo_balance_protocol',empty_mass_kg=4,box_mass_kg=2,
        bin_positions_dm={'L':-1,'C':0,'R':1},bin_capacity=6,maximum_mass_kg=26,zero_benefit_offset_dm=.5,
        rail_positions_dm=list(range(-4,6)),loading_seconds=10,transport_seconds=60)
    history.add(2,'A/B/C三车的L/C/R仓均为空，仓位坐标固定；所用货箱均为上述2kg标准箱。',event='cargo_initial',bins=bins)
    rounds = (4,13,23) if index < 6 else (4,11,18,25) if index < 12 else (3,8,13,17,23,27)
    other_left,other_right = OTHER_CAR_LOADS[index]
    events = [(7,u,f'+L{other_left}',False),(21,v,f'+R{other_right}',False)]
    events += [(at,target,code,index >= 6 and ordinal == 0) for ordinal,(at,code) in enumerate(zip(rounds,codes,strict=True))]
    for at,car,code,partial in sorted(events):
        if code.startswith('0'):
            source,destination,actual,requested = 'external',code[1],0,1
        else:
            actual = int(code[-1])
            requested = actual+int(partial)
            source,destination = ('external',code[1]) if code[0] == '+' else (code[1],'external') if code[0] == '-' else (code[0],code[2])
        transfer(bins[car],source,destination,requested,actual)
        origin = '外部库' if source == 'external' else f'{source}仓'
        destination_name = '外部库' if destination == 'external' else f'{destination}仓'
        movement = f'由{origin}移至{destination_name}'
        extra = '夹具未取起任何箱，没有箱体移动。' if not actual else '请求只部分完成，其余箱未移动。' if actual < requested else '所报实际箱数均已移动。'
        history.add(at,f'载车{car}：{movement}，请求{requested}箱、实际{actual}箱。{extra}',
                    event='cargo_receipt',car=car,source=source,destination=destination,requested_boxes=requested,actual_boxes=actual)
    if index >= 6:
        destination = PLAN_DESTINATIONS[index-6]
        history.add(15,f'拟向{target}车{destination}仓装入1箱，候选计划尚未下发，没有移动货箱。',
                    event='cargo_plan',car=target,destination=destination,planned_boxes=1,executed=False)
    history.add(29,'吊钩已回停车位，所有已落下的货物均留在各自原仓，未装卸或移载。',event='hook_parked',cargo_moved=False)
    history.add(30,f'载车{target}已停在发运口，驱动正常。',event='cargo_departure_ready',car=target)
    task = task_shell('FM-I2-P3',index)
    entries = [{'description':f'将货箱固定在x={x}dm并执行转运。','operation':{'action':'place','x':x}} for x in POSITIONS]
    task.public = {'instruction':f'载车{target}已在发运口，设备正常。请为待交付货箱选择平衡轨固定位，随后执行转运。',
                   'target':target,'box_mass_kg':2,'time_s':clock('09:00'),'location':'departure',
                   'max_steps':3,'state_fields':[],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'bins':bins,'location':'departure','rail_box':None,'external_pending_boxes':1,
                    'locked':False,'delivered':False,'loading_completed_s':None}
    task.world = {'bins':bins,'final_mass_kg':4+2*sum(bins[target].values())+2,'balance_position_dm':bins[target]['L']-bins[target]['R']}
    task.rubric = {'score':'0 if final mass > 26kg or absolute center > 0.5dm; otherwise 100*(1-abs(center)/0.5)'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def observation(self):
        return {**super().observation(),'location':self.state['location']}

    def invalid(self):
        self.feedback = '格式无效，请使用当前菜单编号。'

    def submit(self,action):
        super().submit(action)
        if action == {'action':'end'}:
            self.feedback = '本窗口已结束。'

    def execute(self,operation):
        position = operation['x']
        self.state.update(rail_box={'car':self.task.public['target'],'x_dm':position,'mass_kg':2},
                          external_pending_boxes=0,locked=True,loading_completed_s=self.state['time_s']+10)
        self.state.update(time_s=self.state['time_s']+70,location='handover',delivered=True)
        self.feedback = '装载与转运窗口已结束，记录已存档。'
        return quality(self.state['bins'][self.task.public['target']],position)


def reconstruct(history,current):
    bins = {}
    for text in paragraphs(history):
        receipt = re.match(r'载车([ABC])：由(外部库|[LCR]仓)移至(外部库|[LCR]仓)，请求(\d+)箱、实际(\d+)箱。', text)
        plan = re.fullmatch(r'拟向([ABC])车([LCR])仓装入(\d+)箱，候选计划尚未下发，没有移动货箱。', text)
        if text.startswith('A/B/C三车的L/C/R仓均为空，'):
            bins = {car:dict.fromkeys('LCR',0) for car in 'ABC'}
        elif receipt:
            car,source,destination,requested,actual = receipt.groups()
            source = 'external' if source == '外部库' else source[0]
            destination = 'external' if destination == '外部库' else destination[0]
            transfer(bins[car],source,destination,int(requested),int(actual))
        elif plan and bins[plan[1]][plan[2]]+int(plan[3]) > 6:
            raise ValueError('A candidate loading plan must fit when proposed')
    if set(bins) != set('ABC') or any(set(slots) != {'L','C','R'} for slots in bins.values()):
        raise ValueError('All three independent carriers and their bins must have initial evidence')
    target = bins[current['target']]
    return {'bins':bins,'final_mass_kg':4+2*sum(target.values())+2,'balance_position_dm':target['L']-target['R']}


def next_action(facts,current):
    return decision_command(current,{'action':'place','x':facts['balance_position_dm']})


def check_world(task,facts):
    if facts != task.world or facts['bins'] != task.initial['bins']:
        raise ValueError('Cargo state must conserve every actual loading, unloading and internal transfer')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:quality(facts['bins'][task.public['target']],op['x']))
