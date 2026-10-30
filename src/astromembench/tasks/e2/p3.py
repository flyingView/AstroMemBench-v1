"""FM-E2-P3: update shared physical edges without replacing the whole transport map."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..ground import traverse
from ..prose import paragraphs

EDGES = {
    'G1':(('e01','JA','U01',90),('e02','JA','U02',70),('e03','JA','U03',110),('e04','JA','U04',130),('e05','JA','U05',100),
          ('e06','JB','U06',80),('e07','JB','U07',120),('e08','JB','U08',100),('e09','JB','U09',140),('e10','JB','U10',160),
          ('f01','S1','P',50),('f02','P','JA',80),('f03','P','JB',100),('f04','R','Q1',60),
          ('f05','U01','R',120),('f06','U02','R',150),('f07','U03','R',110),('f08','U04','R',140),('f09','U05','R',180),
          ('f10','U06','R',130),('f11','U07','R',100),('f12','U08','R',160),('f13','U09','R',110),('f14','U10','R',150)),
    'G2':(('e01','P','U1',80),('e02','P','U2',100),('e03','M','V1',70),('e04','M','V2',90),('e05','M','V3',110),
          ('e06','M','V4',130),('e07','M','V5',150),('f01','S1','P',40),('f02','U1','M',120),('f03','U2','M',130),
          ('f04','V1','R',110),('f05','V2','R',140),('f06','V3','R',90),('f07','V4','R',120),('f08','V5','R',100),('f09','R','Q1',60)),
}
ROUTES = {
    'G1':(('f01','f02','e01','f05','f04'),('f01','f02','e02','f06','f04'),('f01','f02','e03','f07','f04'),
          ('f01','f02','e04','f08','f04'),('f01','f02','e05','f09','f04'),('f01','f03','e06','f10','f04'),
          ('f01','f03','e07','f11','f04'),('f01','f03','e08','f12','f04'),('f01','f03','e09','f13','f04'),('f01','f03','e10','f14','f04')),
    'G2':(('f01','e01','f02','e03','f04','f09'),('f01','e01','f02','e04','f05','f09'),('f01','e01','f02','e05','f06','f09'),
          ('f01','e01','f02','e06','f07','f09'),('f01','e01','f02','e07','f08','f09'),('f01','e02','f03','e03','f04','f09'),
          ('f01','e02','f03','e04','f05','f09'),('f01','e02','f03','e05','f06','f09'),('f01','e02','f03','e06','f07','f09'),
          ('f01','e02','f03','e07','f08','f09')),
}
# Graph, direction, a/b, final actual measurement day suffixes, initial/final open edge numbers, cause, answer.
CONFIGS = (
    ('G1','failure',1,2,25,25,(1,),(2,),'坡缘落石',2),('G1','failure',1,2,25,25,(1,),(1,),'坡缘落石',1),
    ('G2','recovery',7,8,25,25,(2,5),(2,4),'坡缘落石',7),('G2','recovery',7,8,25,25,(2,5),(2,5),'坡缘落石',8),
    ('G2','recovery',2,3,33,33,(1,5),(1,4),'工程作业散落物堆积',2),('G2','recovery',2,3,33,33,(1,5),(1,5),'工程作业散落物堆积',3),
    ('G2','failure',2,7,29,31,(1,4),(2,4),'松散物料滑移',7),('G2','failure',2,7,29,31,(1,4),(1,4),'松散物料滑移',2),
    ('G1','failure',8,9,31,35,(8,),(9,),'工程作业散落物堆积',9),('G1','failure',8,9,31,35,(8,),(8,),'工程作业散落物堆积',8),
    ('G1','recovery',1,4,29,31,(4,),(1,),'松散物料滑移',1),('G1','recovery',1,4,29,31,(4,),(4,),'松散物料滑移',4),
    ('G1','failure',3,7,33,35,(3,),(7,),'坡缘落石',7),('G1','failure',3,7,33,35,(3,),(3,),'坡缘落石',3),
    ('G2','recovery',4,8,35,37,(2,5),(1,6),'坡缘落石',4),('G2','recovery',4,8,35,37,(2,5),(2,5),'坡缘落石',8),
)
SOURCE_GROUPS = ((1,'M07-easy-01'),(4,'M07-easy-04'),(6,'M07-easy-06'),(8,'M07-medium-02'),
                 (9,'M07-medium-03'),(11,'M07-medium-05'),(13,'M07-hard-01'),(16,'M07-hard-04'))


def _catalog(name):
    base = {e:(a,b,length) for e,a,b,length in EDGES[name]}
    graph = {'nodes':[f'{region}-{node}' for region in ('Z3','Z4') for node in sorted({n for _,a,b,_ in EDGES[name] for n in (a,b)})],
             'edges':[{'id':f'{region}-{e}','nodes':[f'{region}-{a}',f'{region}-{b}'],'length_m':length,'bidirectional':True}
                      for region in ('Z3','Z4') for e,a,b,length in EDGES[name]]}
    routes = []
    for i,path in enumerate(ROUTES[name],1):
        nodes,length = ['S1'],0
        for edge in path:
            a,b,metres = base[edge]
            if nodes[-1] not in (a,b):
                raise ValueError('Static transport path has disconnected endpoints')
            nodes.append(b if nodes[-1] == a else a)
            length += metres
        routes.append({'id':f'Z3-L{i:02d}','nodes':['Z3-'+n for n in nodes],'edges':['Z3-'+e for e in path],'distance_m':length})
    return graph,routes


def build(index):
    name,direction,a,b,day_a,day_b,initial,final,cause,correct = CONFIGS[index]
    source_group,menu_identity = SOURCE_GROUPS[index//2]
    graph,routes = _catalog(name)
    schedule = {1:(101,[('protocol',None,None)]),2:(102,[('fixed',None,None)])}
    if index < 6:
        schedule[3] = (103,[('retest',number,initial) for number in range(1,11)])
        repeat_rounds,repeat_days = (5,7,9,11,13),(107,111,115,119,123)
        plan_round,last_a,last_b = 12,15,16
        schedule[12] = (121,[('plan',None,None)])
    elif index < 12:
        for j,at in enumerate(range(3,8)):
            schedule[at] = (103+2*j,[('retest',2*j+1,initial),('retest',2*j+2,initial)])
        repeat_rounds,repeat_days = tuple(range(8,15)),(113,115,117,119,121,123,125)
        plan_round,last_a,last_b = 15,17,19
        schedule[15] = (126,[('plan',None,None)])
    else:
        for j,at in enumerate(range(3,13),1):
            schedule[at] = (102+j,[('retest',j,initial)])
        repeat_rounds,repeat_days = (13,14,15,16,17),(113,115,117,119,121)
        intermediate = CONFIGS[(index//2)*2][7]
        schedule[18] = (123,[('retest',a,intermediate),('retest',b,intermediate)])
        schedule[19] = (129,[('retest',a,initial),('retest',b,initial)])
        plan_round,last_a,last_b = 20,21,22
        schedule[20] = (130,[('plan',None,None)])
    for at,day in zip(repeat_rounds,repeat_days,strict=True):
        schedule[at] = (day,[('trip' if direction == 'failure' else 'retest',a,initial)])
    schedule[last_a] = (100+day_a,[('retest',a,final)])
    schedule[last_b] = (100+day_b,[('retest',b,final)])
    external = b if source_group%2 else a
    if index < 6:
        schedule[27] = (147,[('external',external,None)])
    else:
        schedule[23 if index < 12 else 24] = (137 if index < 12 else 139,[('external',3,None)])
        schedule[26] = (143,[('external',b,None)])
        schedule[28] = (147,[('external',external,None)])
    schedule[30] = (150,[('ready',None,None)])
    times,receipts = [],{}
    previous = clock('09:00',101)-1
    for at in range(1,31):
        if at in schedule:
            day,entries = schedule[at]
            first = clock('09:01' if at == last_b and day_a == day_b else '09:00',day)
            receipts[at] = [first+i*60 for i in range(len(entries))]
            previous = receipts[at][-1]
        else:
            previous += 1
        times.append(previous)
    history = History(times=times)
    known,planned = {},set()
    edge_catalog = {r['id']:r for r in graph['edges']}
    trips = 0

    def add(at,position,text,**facts):
        timestamp = receipts[at][position]
        history.add(at,text,occurred=timestamp,received=timestamp,**facts)

    def retest(at,position,region,edge_ids,target):
        rows,texts = [],[]
        for local in edge_ids:
            edge = region+'-'+local
            value = True if local.startswith('f') or region == 'Z4' else int(local[1:]) in target
            old = known.get(edge)
            if value:
                reason = '复测仍满足承载条件' if old else '清障已完成，实际复测满足承载条件'
            elif edge in planned:
                reason = '清障后实际复测仍不满足承载条件'
            else:
                reason = cause+'，实际环境复测不满足承载条件'
            if old is None and value:
                reason = '实际环境初测满足承载条件'
            texts.append(edge+'（'+'/'.join(edge_catalog[edge]['nodes'])+'）：'+reason)
            rows.append({'edge':edge,'nodes':edge_catalog[edge]['nodes'],'passable':value})
            known[edge] = value
        add(at,position,'；'.join(texts)+'。',event='transport_ground_retest',region=region,measurements=rows)

    for at,(day,entries) in sorted(schedule.items()):
        for position,(kind,number,target) in enumerate(entries):
            if kind == 'protocol':
                add(at,position,'运输区Z3内，同构20kg货箱从S1送达Q1；当前箱为F17，旧成功作业为其他同规格箱。'
                    '车辆、载荷构型、设备和能源正常且充分。所有地图边双向，没有图外边；Z3与Z4为独立不相连区域，同名边不是同一地点。'
                    '实际环境复测只更新同区所列边，结论持续至后续同边复测，所有记录同等可信且按发生时间排列；清障计划不改变状态。'
                    '共享边只有一个实际状态，其变化影响所有经过该边的路线，整条路线旧成功不覆盖新边复测。'
                    '目标把F17完整运抵Z3-Q1，任意全程可行路线均完成任务，没有额外里程要求。'
                    '有效无效及end共3次，首合法选择实际执行后结束，不能探路再改选或改去Z4交付；等待不能完成交付。'
                    '没有额外车速或时限要求，选择后的执行回执保留当前任务时钟；推理与记忆检索不推进故事时间。',
                    event='transport_access_protocol',graph=graph,routes=routes)
            elif kind == 'fixed':
                retest(at,position,'Z3',[e for e,_,_,_ in EDGES[name] if e.startswith('f')],initial)
            elif kind == 'retest':
                retest(at,position,'Z3',[edge for edge in ROUTES[name][number-1] if edge.startswith('e')],target)
            elif kind == 'external':
                retest(at,position,'Z4',ROUTES[name][number-1],())
            elif kind == 'plan':
                number = b if direction == 'failure' else a
                planned_edges = [edge for edge in routes[number-1]['edges'] if '-e' in edge and not known[edge]]
                planned.update(planned_edges)
                add(at,position,'提出'+','.join(planned_edges)+'的清障计划，均待实施；没有实际环境复测通过结论。',
                    event='transport_ground_plan',region='Z3',route=f'Z3-L{number:02d}',edges=planned_edges,implemented=False)
            elif kind == 'trip':
                route = routes[number-1]
                if not all(known[edge] for edge in route['edges']):
                    raise ValueError('Historical cargo cannot be transported through a then-closed shared edge')
                trips += 1
                add(at,position,f'货箱H{trips:02d}为同构20kg，车辆已沿{route["id"]}实际送达Z3-Q1并返回Z3-S1，完成回执。',
                    event='old_transport_completed',region='Z3',cargo={'id':f'H{trips:02d}','mass_kg':20},
                    route=route['id'],edges=route['edges'],destination='Z3-Q1',returned_to='Z3-S1')
            else:
                add(at,position,'Z3-S1，货箱F17装载完成，运输设备就绪。',event='cargo_transport_ready',location='Z3-S1',cargo_id='F17')
    group = f'FM-E2-P3-pair{index//2+1:02d}'
    task = task_shell('FM-E2-P3',index,group=group,background_group=group,current_input_group=group)
    options = [{'operation':{'kind':'transport','route':route['id']},'description':f'沿{route["id"]}执行完整运输：'+
                '/'.join(route['nodes'])+'；通道'+'/'.join(route['edges'])+f'，总长{route["distance_m"]}米。'} for route in routes]
    options.append({'operation':{'kind':'wait'},'description':'在Z3-S1原地等待。'})
    task.public = {'time_s':clock('09:00',151),'location':'Z3-S1','destination':'Z3-Q1','cargo':{'id':'F17','mass_kg':20},
                   'graph':graph,'routes':routes,'equipment_ready':True,'max_steps':3,'state_fields':[],
                   'instruction':'第151日09:00，Z3-S1，货箱F17为20kg，目的Z3-Q1。运输设备已就绪。请继续执行本次运输任务。',
                   'actions':ordered_options(options,menu_identity)}
    task.initial = {'time_s':clock('09:00',151),'location':'Z3-S1','cargo':{'id':'F17','mass_kg':20,'holder':'vehicle'},'attempts':[]}
    task.world = {'passable':{'Z3-'+e:e.startswith('f') or int(e[1:]) in final for e,_,_,_ in EDGES[name]},
                  'correct_operation':{'kind':'transport','route':f'Z3-L{correct:02d}'}}
    task.rubric = {'score':'100 for actual complete transport of F17 to Z3-Q1; distance and safe prefixes do not score'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.feedback = '操作已执行，记录已存档。'
        if operation['kind'] == 'wait':
            self.state['attempts'].append({'kind':'wait','location':self.state['location']})
            return 0
        route = next(r for r in self.task.public['routes'] if r['id'] == operation['route'])
        result = traverse(self.task.public['graph'],route,self.task.world['passable'])
        self.state['location'] = result['location']
        if result['arrived']:
            self.state['cargo']['holder'] = 'Z3-Q1'
        self.state['attempts'].append({'kind':'transport','route':route['id'],'cargo_id':'F17',**result})
        return 100 if result['arrived'] else 0


def reconstruct(history,current):
    passable = {}
    edges = {row['id']:row for row in current['graph']['edges']}
    routes = {row['id']:row for row in current['routes']}
    for text in paragraphs(history):
        for item in text.removesuffix('。').split('；'):
            measurement = re.fullmatch(r'(Z3-[ef]\d+)（(Z3-[A-Z0-9]+)/(Z3-[A-Z0-9]+)）：(.*)',item)
            if measurement:
                edge,first,second,body = measurement.groups()
                if [first,second] != edges[edge]['nodes']:
                    raise ValueError('Public transport retest endpoints disagree with the map')
                if body in ('复测仍满足承载条件','清障已完成，实际复测满足承载条件','实际环境初测满足承载条件'):
                    value = True
                elif body == '清障后实际复测仍不满足承载条件' or body.endswith('，实际环境复测不满足承载条件'):
                    value = False
                else:
                    raise ValueError('Incomplete public transport ground retest')
                passable[edge] = value
        trip = re.fullmatch(r'货箱H\d+为同构20kg，车辆已沿(Z3-L\d+)实际送达Z3-Q1并返回Z3-S1，完成回执。',text)
        if trip and not all(passable[e] for e in routes[trip[1]]['edges']):
            raise ValueError('Old cargo success cannot replace actual then-current shared-edge states')
    safe = [r['id'] for r in current['routes'] if all(passable[e] for e in r['edges'])]
    if len(safe) != 1:
        raise ValueError('This transport design must have exactly one full physical route')
    return {'passable':passable,'correct_operation':{'kind':'transport','route':safe[0]}}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Cargo routing differs from actual local edge revision history')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
