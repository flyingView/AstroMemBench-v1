"""FM-I2-P1: irreversible wheel ruts and a physically executed closed survey route."""
from collections import Counter
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

LIMIT_MM = 6
ROUTES = tuple({'id':f'L{i+1}','bridges':list(bridges),'length_m':length,
                'bridge_distances_m':[100*(j+1) for j in range(len(bridges))]}
               for i,(bridges,length) in enumerate((('AA',400),('BB',500),('CC',600),('AB',700),('AC',800),
                                                     ('BC',900),('A',1000),('B',1100),('C',1200),('',1600))))
MENU = ('L6','L2','L9','L1','L7','L4','L10','L3','L8','L5')
CONFIGS = (
    ((2,2),(3,3),(2,3)),((2,3),(3,2),(3,3)),((2,3),(3,3),(4,2)),
    ((4,2),(3,2),(3,3)),((3,3),(4,2),(2,3)),((3,2),(2,3),(3,2)),
    ((2,1,2),(1,1,2),(2,2,2)),((2,2,2),(1,2,2),(2,1,1)),((2,1,2),(1,3,2),(1,2,2)),
    ((2,2,2),(2,1,2),(1,2,2)),((1,3,2),(2,2,2),(1,3,2)),((2,1,2),(2,1,1),(1,2,2)),
    ((1,0,1,2),(2,0,2,2),(1,0,2,2)),((1,0,2,2),(2,0,1,2),(2,0,2,2)),
    ((3,0,1,2),(2,0,2,2),(1,0,2,2)),((2,0,2,2),(3,0,1,2),(2,0,2,2)),
)


def safe(route,ruts):
    return all(ruts[bridge]+count <= LIMIT_MM for bridge,count in Counter(route['bridges']).items())


def shortest_safe(routes,ruts):
    return min((route for route in routes if safe(route,ruts)),key=lambda route:route['length_m'])


def build(index):
    history = History()
    ruts = dict.fromkeys('ABC',0)
    history.add(1,'车辆在区域K基站，导航与驱动正常，A/B/C三块窄软土桥独立且初始车辙均0毫米。'
        '每次实际完整通过某桥使该桥永久车辙增加1毫米；实际次数计入，请求但未完成的次数不计。'
        '每次通过后车辙不超过6毫米仍承载，超过6毫米会陷车，本次观测失败。返回基站、卸载或里程清零不修复桥面。'
        'J区同名桥属于独立坐标域，不与K累计，计划不碾压。十条闭合路线均完成相同目标观测并返回基站，安全完成时优先较短路线。'
        '路线表给出按序通过的全部软桥，AA是两次实际通过，不是重复记录；其余路段全为硬地。'
        '当前按1米/秒行驶，首桥在该路线累计100米处、第二桥在200米处，到达时记为完成通过并增加车辙。'
        '超限即停在该次桥位，保留已经造成的车辙，其后不再通过；安全路线按完整长度回基站，观察才完成。'
        '历史回执是此前窗口结束的实际次数，不把当前路线长度套作历史耗时。'
        '选定整条路线后不可改线或重选，无免费探测、回填、回档或等待改善地面的动作。'
        '完整菜单按select和字符串option提交，或end结束；总调用最多3次含格式错误和合法选择，首个合法选择执行后终止。'
        '格式错误不走车，额外字段、数值型或范围外编号均无效。',event='rut_survey_protocol',region='K',
        initial_ruts_mm=ruts,increment_mm_per_pass=1,bearing_limit_mm=LIMIT_MM,speed_m_s=1)
    route_text = '；'.join(f'{r["id"]}：软桥'+('→'.join(r['bridges']) or '无')+f'，全长{r["length_m"]}米' for r in ROUTES)
    history.add(2,'已标定的十条闭合勘察路线；各路线完成同一组目标观测，未列部分均为硬地，软桥按列表顺序逐次通过。'+route_text+'。',
                event='rut_route_catalog',routes=ROUTES)
    if index < 6:
        rounds,plan_round = ((4,19),(7,22),(10,25)),15
    elif index < 12:
        rounds,plan_round = ((4,13,24),(6,15,26),(8,17,28)),20
    else:
        rounds,plan_round = ((3,9,18,25),(4,11,20,27),(5,13,22,29)),16
    for bridge,sequence,times in zip('ABC',CONFIGS[index],rounds,strict=True):
        for ordinal,(at,actual) in enumerate(zip(times,sequence,strict=True)):
            requested = actual+1 if 6 <= index < 12 and ordinal == 0 else 1 if index >= 12 and ordinal == 1 else actual
            ruts[bridge] += actual
            if ruts[bridge] > LIMIT_MM:
                raise ValueError('Every historical actual crossing must remain within bearing capacity')
            history.add(at,f'此前窗口已结束：区域K、桥{bridge}，请求通过{requested}次，实际完整通过{actual}次。'+
                (f'其余{requested-actual}次未完成，没有产生碾压。' if requested > actual else '所报实际次数均已完成。'),
                event='bridge_pass_receipt',region='K',bridge=bridge,requested_passes=requested,actual_passes=actual)
    history.add(plan_round,'仅提出以后在K区桥A再通过1次的计划，尚未执行，没有产生碾压。',
                event='bridge_pass_plan',region='K',bridge='A',planned_passes=1,executed=False)
    history.add(23,'另一独立坐标域J区的桥A此前车辙为0毫米，本窗口请求2次、实际完整通过2次；这是J区桥面。',
                event='bridge_pass_receipt',region='J',bridge='A',initial_rut_mm=0,requested_passes=2,actual_passes=2)
    history.add(30,'车辆已正常返回K区基站，里程表显示清零；桥面没有施工、未作回填。',
                event='survey_return',region='K',location='K-base',odometer_m=0,bridge_restored=False)
    entries = [{'operation':{'kind':'survey','route':route_id},'description':f'执行闭合勘察路线{route_id}。'} for route_id in MENU]
    task = task_shell('FM-I2-P1',index)
    task.public = {'time_s':clock('09:00'),'region':'K','location':'K-base','equipment_ready':True,'routes':deepcopy(list(ROUTES)),
                  'max_steps':3,'state_fields':[],'instruction':'车辆已在基站就位，设备正常。请选择本次区域勘察测线。',
                  'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'region':'K','location':'K-base','ruts_mm':ruts,'distance_m':0,
                    'trapped':False,'observations_completed':False,'crossings':[]}
    task.world = {'ruts_mm':ruts,'minimum_distance_m':shortest_safe(ROUTES,ruts)['length_m']}
    task.rubric = {'score':'zero when trapped; otherwise 100 times shortest safe initial route length divided by completed route length'}
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
        route = next(r for r in self.task.public['routes'] if r['id'] == operation['route'])
        minimum = shortest_safe(self.task.public['routes'],self.state['ruts_mm'])['length_m']
        started = self.state['time_s']
        self.feedback = '本测线执行结束，记录已存档。'
        for bridge,distance in zip(route['bridges'],route['bridge_distances_m'],strict=True):
            self.state['time_s'] = started+distance
            self.state['distance_m'] = distance
            self.state['location'] = 'K-'+bridge
            self.state['ruts_mm'][bridge] += 1
            depth = self.state['ruts_mm'][bridge]
            self.state['crossings'].append({'bridge':bridge,'distance_m':distance,'time_s':self.state['time_s'],'rut_mm':depth})
            if depth > LIMIT_MM:
                self.state['trapped'] = True
                return 0
        self.state.update(time_s=started+route['length_m'],distance_m=route['length_m'],location='K-base',observations_completed=True)
        return 100*minimum/route['length_m']


def reconstruct(history,current):
    ruts = {}
    for text in paragraphs(history):
        initial = re.match(r'车辆在区域([A-Z])基站，导航与驱动正常，A/B/C三块窄软土桥独立且初始车辙均(\d+)毫米。', text)
        receipt = re.match(r'此前窗口已结束：区域([A-Z])、桥([ABC])，请求通过(\d+)次，实际完整通过(\d+)次。', text)
        if initial and initial[1] == current['region']:
            ruts = dict.fromkeys('ABC',int(initial[2]))
            if any(clause not in text for clause in ('永久车辙增加1毫米','车辙不超过6毫米仍承载','按1米/秒行驶')):
                raise ValueError('The prescribed rut and current driving model must be explicit')
        elif text.startswith('已标定的十条闭合勘察路线；'):
            listed = [{'id':identity, 'bridges':[] if bridges == '无' else bridges.split('→'), 'length_m':int(length)}
                      for identity,bridges,length in re.findall(r'(L\d+)：软桥([ABC→]+|无)，全长(\d+)米', text)]
            if listed != [{key:r[key] for key in ('id','bridges','length_m')} for r in current['routes']]:
                raise ValueError('Historical route prose and the current route catalog disagree')
        elif receipt and receipt[1] == current['region']:
            _,bridge,requested,actual = receipt.groups()
            requested,actual = int(requested),int(actual)
            if not 0 <= actual <= requested:
                raise ValueError('Actual completed crossings cannot exceed their request')
            ruts[bridge] += actual
            if ruts[bridge] > LIMIT_MM:
                raise ValueError('Historical actual crossings must be safe before the current window')
    if set(ruts) != set('ABC'):
        raise ValueError('All three local bridges require initial physical evidence')
    return {'ruts_mm':ruts,'minimum_distance_m':shortest_safe(current['routes'],ruts)['length_m']}


def next_action(facts,current):
    route = shortest_safe(current['routes'],facts['ruts_mm'])
    return decision_command(current,{'kind':'survey','route':route['id']})


def check_world(task,facts):
    if facts != task.world or facts['ruts_mm'] != task.initial['ruts_mm']:
        raise ValueError('Current local rut depth must equal all actual local passes without plans, requests or other regions')


def audit_cases(task,facts,solution):
    def score(operation):
        route = next(r for r in task.public['routes'] if r['id'] == operation['route'])
        return 100*facts['minimum_distance_m']/route['length_m'] if safe(route,facts['ruts_mm']) else 0
    return decision_cases(task,solution,score)
