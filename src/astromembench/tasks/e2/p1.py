"""FM-E2-P1: revise individual survey corridors, then score actual safe arrival efficiency."""
import re

from ..common import ArchiveHistory, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..ground import traverse
from ..prose import paragraphs
from ...schema import story_timestamp

LENGTHS = dict(zip('abcdefg',(70,95,80,110,60,130,90),strict=True))
MENUS = {
    'X01':(10,4,6,9,3,0,5,8,2,7,1),'X02':(6,5,2,0,4,1,7,3,9,10,8),
    'X04':(9,1,8,0,3,5,7,2,10,4,6),'X06':(0,6,7,4,1,2,9,3,5,8,10),
    'X07':(4,0,5,1,7,10,8,2,9,6,3),'X08':(9,1,0,8,6,4,2,5,3,10,7),
}
# Process, initial open edges, old route, two actual updates, planned edges, final open set, shortest route.
CONFIGS = (
    ('X01','ac',1,(),(),'','bc',6),('X02','ac',1,(),(),'','ac',1),
    ('S','ae',3,(('e',False),('d',True)),(('d',False),('e',True)),'b','ae',3),
    ('S','bc',6,(('c',False),('g',True)),(('a',True),),'e','abg',5),
    ('S','ag',5,(('g',False),('e',True)),(('b',True),),'d','abe',3),
    ('S','bd',7,(('d',False),('c',True)),(('c',False),('d',True)),'a','bd',7),
    ('X04','ad',2,(),(),'','ae',3),('X06','af',4,(),(),'','afg',5),
    ('M','ac',1,(('a',False),('b',True)),(('c',False),('e',True)),'g','be',8),
    ('M','af',4,(('b',True),('e',True)),(('a',False),('f',False)),'c','be',8),
    ('M','ae',3,(('e',False),('f',True)),(('c',True),),'b','acf',1),
    ('M','ac',1,(('a',False),('b',True)),(('a',True),('c',True)),'g','abc',1),
    ('X07','ac',1,(),(),'','bg',10),('X08','bd',2,(),(),'','ac',1),
    ('H','ag',5,(('a',False),('b',True),('g',False),('c',True)),(('b',False),('a',True),('c',False),('f',True)),'d','af',4),
    ('H','bc',6,(('b',False),('a',True),('c',False),('d',True)),(('b',True),('a',False),('d',False),('g',True)),'e','bg',10),
)
# Actual source events, including temporary alternatives and every local/external reversal.
SOURCE_EVENTS = {
    'X01':((5,'K',(('f',True),),'f铺垫完成并复测通过'),(7,'K',(('c',False),),'c出现松土，复测关闭'),
           (9,'K',(('c',True),),'c清理后复测恢复'),(10,'T',(1,1,True),'同载荷经a/c完成测线并返回S'),
           (13,'K',(('f',False),),'f铺垫破裂，复测关闭'),(17,'J',(('b',True),),'邻区b实际复测通过'),
           (20,'P','b','b处于施工准备，未完成实际复测'),(23,'K',(('a',False),('b',True)),'a下陷复测关闭，b加固完成复测通过')),
    'X02':((5,'K',(('c',False),),'c轮迹下陷，实际关闭'),(7,'K',(('d',True),),'d临时板铺设后复测开放'),
           (9,'K',(('c',True),),'c整平后复测通过'),(10,'T',(1,1,None),'同载荷经a/c实际完成测线，同时提出加固b方案，尚未实施'),
           (14,'K',(('d',False),),'d临时板撤走，实际关闭'),(17,'J',(('b',True),),'邻区b复测开放'),
           (20,'P','b','b材料到场但尚未施工'),(23,'K',(('a',True),),'b仍仅排程；a实际复测仍可通行'),
           (24,'K',(('a',True),),'a再次实际复测通过，c无变化')),
    'X04':((5,'K',(('d',False),),'d沉降，复测关闭'),(6,'K',(('e',True),),'e临时支撑后复测开放'),
           (8,'K',(('d',True),),'d加固后复测恢复'),(9,'T',(2,1,True),'同载荷经a/d完成测线并返回S'),
           (12,'K',(('e',False),),'e临时支撑撤除，实际关闭'),(16,'P','e','提出e清障计划，尚未完成复测'),
           (18,'J',(('d',True),),'邻区d承载复测通过'),(20,'P','e','e正在清障施工，但没有承载复测结论'),
           (22,'K',(('d',False),('e',True)),'d新沉陷关闭，e实际清障且承载复测通过'),(28,'J',(('d',True),),'邻区d实际通行复测正常')),
    'X06':((5,'K',(('f',False),),'f表层塌落，实际关闭'),(7,'K',(('c',True),),'c清障后复测开放'),
           (9,'K',(('f',True),),'f清理后复测恢复'),(10,'T',(4,2,None),'两次同载荷经a/f的观测转位均已实际完成'),
           (13,'K',(('c',False),),'c被散落岩块阻断，实际关闭'),(16,'J',(('g',False),),'邻区g实际复测仍关闭'),
           (19,'K',(('g',True),),'g地表整平后复测开放，f仍可用'),(24,'P','d','提出d清障计划，未实施'),
           (26,'P','d','d计划仍未实施，未产生实际通行变化')),
    'X07':((4,'K',(('c',False),),'c临时沉陷，实际关闭'),(5,'K',(('d',True),),'d铺垫后复测开放'),
           (7,'K',(('c',True),),'c处理后复测通过'),(8,'T',(1,1,None),'同载荷经a/c实际完成测线'),
           (10,'K',(('d',False),),'d铺垫冲散，实际关闭'),(14,'K',(('a',False),('c',False),('b',True),('e',True)),'a/c沉陷关闭，b/e加固完成且承载复测开放'),
           (17,'J',(('e',True),),'邻区e实际复测开放'),(21,'K',(('e',False),('g',True)),'e落石后关闭，g清理后复测开放'),
           (24,'J',(('g',False),),'邻区g实际复测未通过'),(26,'P','ac','a/c清障计划批准但未实施'),
           (28,'J',(('a',True),('c',True)),'邻区a/c实际复测通过')),
    'X08':((5,'K',(('d',False),),'d短时占道，实际关闭'),(7,'K',(('e',True),),'e临时通路复测开放'),
           (9,'K',(('d',True),),'d占道物撤走，复测通过'),(10,'K',(('b',False),('a',True)),'b关闭，a施工完成复测开放，d仍可用'),
           (12,'K',(('e',False),),'e临时通路撤除，实际关闭'),(15,'T',(2,1,None),'同载荷经a/d实际完成测线'),
           (18,'J',(('b',True),),'邻区b实际复测通过'),(21,'K',(('d',False),('c',True)),'d裂隙关闭，c整平后复测开放'),
           (24,'P','d','d材料已确认但尚未开工'),(25,'P','d','d施工队未到，计划没有实施'),(28,'J',(('d',True),),'邻区d实际复测通过')),
}


def _endpoints(edge):
    return ('S','W') if edge in 'ab' else ('W','Q')


def _map():
    return {'nodes':[f'{region}-{node}' for region in ('K','J') for node in ('S','W','Q')],
            'edges':[{'id':f'{region}-{edge}','nodes':[f'{region}-{n}' for n in _endpoints(edge)],'length_m':length,'bidirectional':True}
                     for region in ('K','J') for edge,length in LENGTHS.items()]}


def _routes():
    return [{'id':f'K-R{i+1}','nodes':['K-S','K-W','K-Q'],'edges':[f'K-{a}',f'K-{b}'],'distance_m':LENGTHS[a]+LENGTHS[b]}
            for i,(a,b) in enumerate((a,b) for a in 'ab' for b in 'cdefg')]


def build(index):
    process,initial,old_route,updates,final_updates,planned,final,best = CONFIGS[index]
    source = process in SOURCE_EVENTS
    history = ArchiveHistory(clock('10:00'),spacing_s=120)
    graph,routes = _map(),_routes()
    known = {}
    history.add(1,'携固定测量载荷在K区从S经W转位至测线Q；设备、载荷、电量和低层驾驶保持正常。'
                'K与邻区J不相连，同名通道各自独立；同端点平行通道以边ID分别识别，不共享路面。'
                '所有实际承载复测按发生次序更新同区同通道，未测通道维持原结论；计划、材料到场和施工中不产生通过结论。'
                '目标经全程可通行路线安全到达Q且尽量少走路；只走安全前缀、等待或不执行都未完成抵达任务。'
                '有效无效及end共3次，首合法选择实际执行后结束，不能探路再改答。推理与记忆检索不推进故事时间。'+
                ('' if source else '本次机会于10:04关闭，合法路线或等待统一届时结束，已到达或被阻断后安全停驻，不再改变路况。'),
                event='survey_access_protocol',graph=graph,routes=routes)

    def measure(at,region,values,description=None):
        rows,texts = [],[]
        for edge,passed in values:
            edge_id = f'{region}-{edge}'
            previous = known.get(edge_id)
            cause = ('入口加固已完成' if edge in 'ab' else '松软层清理已完成' if edge in 'cd' else '岩块移除已完成') if passed else (
                     '入口发生沉陷' if edge in 'ab' else '出现松软层' if edge in 'cd' else '岩块堆积阻断')
            if source or region == 'J' or previous is None:
                cause = '实际地表承载测量'
            result = ('仍' if previous is passed else '')+('通过' if passed else '不通过')
            texts.append(f'{edge_id}（'+ '/'.join(f'{region}-{n}' for n in _endpoints(edge))+f'）：{cause}，承载实际复测{result}')
            rows.append({'edge':edge_id,'nodes':[f'{region}-{n}' for n in _endpoints(edge)],'passable':passed})
            known[edge_id] = passed
        history.add(at,(description+'；' if description else '')+'；'.join(texts)+'。',event='ground_retest',region=region,measurements=rows)

    def plan(at,edges,text):
        history.add(at,'K区：'+text+'，不改变尚未复测的通道结论。',event='ground_plan',region='K',edges=[f'K-{e}' for e in edges])

    def trip(at,number,count,returned,description):
        route = routes[number-1]
        if not all(known[e] for e in route['edges']):
            raise ValueError('Old survey movement cannot succeed on a then-closed edge')
        facts = {'event':'survey_trip_completed','region':'K','route':route['id'],'edges':route['edges'],'completed_trips':count,'same_payload':True}
        if returned is not None:
            facts['returned_to'] = 'K-S' if returned else 'K-Q'
        if not source:
            finish = history.events[at-1].time_s
            facts.update(started_s=finish-240,finished_s=finish)
            description += f'，完整转位、作业与返回从{story_timestamp(finish-240)}至{story_timestamp(finish)}共4分钟'
        history.add(at,f'K区历史转位，路线{route["id"]}（'+ '/'.join(route['edges'])+'）：'+description+'。',**facts)

    if source:
        measure(3,'K',[(e,e in initial) for e in LENGTHS],'七通道初始实际承载测量')
        for at,kind,payload,text in SOURCE_EVENTS[process]:
            if kind in ('K','J'):
                measure(at,kind,payload,text)
            elif kind == 'P':
                plan(at,payload,text)
            else:
                trip(at,*payload,text)
        menu = MENUS[process]
    else:
        initial_groups = ((3,'abcdefg'),) if process == 'S' else ((3,'ab'),(7,'cde'),(11,'fg')) if process == 'M' else ((3,'ab'),(5,'cde'),(7,'fg'))
        for at,edges in initial_groups:
            measure(at,'K',[(e,e in initial) for e in edges],'本组通道初始实际承载测量')
        if process == 'H':
            entrance = routes[old_route-1]['edges'][0].split('-')[1]
            measure(9,'K',[(entrance,False)])
            measure(12,'K',[(entrance,True)])
        for at in ((6,10) if process == 'S' else (13,) if process == 'M' else (14,)):
            trip(at,old_route,1,True,f'同载荷经{routes[old_route-1]["id"]}实际完成测线并返回K-S')
        measure(17 if process == 'H' else 16,'K',updates)
        plan(19 if process == 'M' else 20,planned,'提出'+','.join('K-'+e for e in planned)+'清障计划，尚未实施')
        measure(24,'K',final_updates)
        measure(27 if process == 'M' else 28,'J',[(e,not known['K-'+e]) for e in planned],'邻区独立的实际承载复测')
        history.add(30,'K-S测量设备与载荷已就绪，等待到测线Q的完整转位。',event='survey_access_ready',location='K-S')
        menu = (*range(1,11),0)
    task = task_shell('FM-E2-P1',index)
    task.public = {'time_s':clock('10:00'),'location':'K-S','destination':'K-Q','graph':graph,'routes':routes,
                   'equipment_ready':True,'max_steps':3,'state_fields':[],'instruction':'第120日10:00，K-S，装置已就绪，请选择到Q的完整行程。',
                   'actions':fixed_options([{'operation':{'kind':'move','route':routes[n-1]['id']},
                                            'description':f'沿{routes[n-1]["id"]}的'+ '/'.join(routes[n-1]['edges'])+
                                            f'经K-S/K-W/K-Q完成转位，共{routes[n-1]["distance_m"]}米。'} if n else
                                           {'operation':{'kind':'wait'},'description':'在K-S等待。'} for n in menu])}
    if not source:
        task.public['execution_end_s'] = clock('10:04')
    task.initial = {'time_s':clock('10:00'),'location':'K-S','attempts':[]}
    task.world = {'passable':{f'K-{e}':e in final for e in LENGTHS},'minimum_distance_m':routes[best-1]['distance_m'],
                  'correct_operation':{'kind':'move','route':f'K-R{best}'}}
    task.rubric = {'score':'100 times the shortest safe route distance divided by the actually completed route distance; blocked prefixes earn zero'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['time_s'] = self.task.public.get('execution_end_s',self.state['time_s'])
        self.feedback = '操作已执行，记录已存档。'
        if operation['kind'] == 'wait':
            self.state['attempts'].append({'kind':'wait','location':self.state['location']})
            return 0
        route = next(r for r in self.task.public['routes'] if r['id'] == operation['route'])
        result = traverse(self.task.public['graph'],route,self.task.world['passable'])
        self.state['location'] = result['location']
        self.state['attempts'].append({'kind':'move','route':route['id'],**result})
        return 100*self.task.world['minimum_distance_m']/result['travelled_m'] if result['arrived'] else 0


def reconstruct(history,current):
    known = {}
    edges = {row['id']:row for row in current['graph']['edges']}
    routes = {row['id']:row for row in current['routes']}
    for text in paragraphs(history):
        for item in text.removesuffix('。').split('；'):
            measurement = re.fullmatch(r'(K-[a-g])（(K-[SWQ])/(K-[SWQ])）：[^；]+，承载实际复测(?:仍)?(通过|不通过)',item)
            if measurement:
                edge,first,second,result = measurement.groups()
                if [first,second] != edges[edge]['nodes']:
                    raise ValueError('Public survey retest endpoints disagree with the map')
                known[edge] = result == '通过'
        trip = re.fullmatch(r'K区历史转位，路线(K-R\d+)（(K-[ab])/(K-[cdefg])）：.+。',text)
        if trip:
            route = routes[trip[1]]
            if route['edges'] != [trip[2],trip[3]]:
                raise ValueError('Public historical survey route disagrees with its edges')
            if not all(known[e] for e in route['edges']):
                raise ValueError('Historical survey trip must use then-open local edges')
    safe = [route for route in current['routes'] if all(known[e] for e in route['edges'])]
    best = min(safe,key=lambda r:r['distance_m'])
    return {'passable':known,'minimum_distance_m':best['distance_m'],'correct_operation':{'kind':'move','route':best['id']}}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Survey corridor states differ from actual local ground revisions')


def audit_cases(task,facts,solution):
    def score(operation):
        if operation['kind'] == 'wait':
            return 0
        route = next(r for r in task.public['routes'] if r['id'] == operation['route'])
        return 100*facts['minimum_distance_m']/route['distance_m'] if all(facts['passable'][e] for e in route['edges']) else 0
    return decision_cases(task,solution,score)
