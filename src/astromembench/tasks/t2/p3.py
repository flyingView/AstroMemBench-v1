"""FM-T2-P3: unloading followed by the appointed node triggers a handoff duty."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('H1','1000','MX',(('RA','H1',1,''),),'RA'),
    ('H1','0000','MX',(('RA','H1',1,''),),'MX'),
    ('H2','0100','MY',(('TB','H2',0,''),),'TB'),
    ('H3','0100','MY',(('TB','H2',0,''),),'MY'),
    ('H2','0001','MX',(('TD','H2',1,''),),'TD'),
    ('H1','0001','MX',(('TD','H2',1,''),),'MX'),
    ('H1','1100','MY',(('RA','H1',2,''),('TB','H1',0,'')),'TB'),
    ('H1','1000','MY',(('RA','H1',2,''),('TB','H1',0,'')),'RA'),
    ('H2','0011','MX',(('TC','H2',1,''),('RD','H3',0,'')),'TC'),
    ('H3','0011','MX',(('TC','H2',1,''),('RD','H3',0,'')),'RD'),
    ('H1','1010','MZ',(('TA','H2',0,''),('RC','H3',1,'')),'MZ'),
    ('H2','1010','MZ',(('TA','H2',0,''),('RC','H3',1,'')),'TA'),
    ('H1','1100','MX',(('RA','H1',0,'X'),('TB','H1',1,'')),'TB'),
    ('H2','0011','MY',(('TC','H2',0,'D'),('RD','H2',2,'')),'RD'),
    ('H2','0011','MY',(('TC','H2',0,'D'),('RD','H3',2,'')),'MY'),
    ('H3','0110','MZ',(('RB','H3',0,'Q40'),('TC','H3',1,''),('RA','H1',2,'')),'TC'),
)
ITEM_NAMES = {'tray':'周转盘','recorder':'温度记录器'}


def _operation(code):
    if code == 'W':
        return {'kind':'wait'}
    if code[0] == 'M':
        return {'kind':'move','destination':code[1]}
    return {'kind':'handoff','batch':code[1],'item':'tray' if code[0] == 'R' else 'recorder'}


def _description(operation):
    if operation['kind'] == 'wait':
        return '原地等候。'
    if operation['kind'] == 'move':
        return f'沿普通转运行程驶向{operation["destination"]}站。'
    item = ITEM_NAMES[operation['item']]
    cabinet = '中转保管柜' if operation['item'] == 'tray' else '接收柜'
    return f'把Q41货批{operation["batch"]}的{item}交入当前节点{cabinet}；无可交物时检查空位。'


def build(index):
    node,bits,next_move,config,correct = CONFIGS[index]
    unloaded = {batch:bit == '1' for batch,bit in zip('ABCD',bits,strict=True)}
    done = any(row[-1] == 'D' for row in config)
    history = History()
    history.add(1,'航单Q41，货批A/B/C/D各有独立周转盘和温度记录器；低层承载、能源和路线已解决，设备正常。'
                '每个承诺绑定航单、货批、动作、交接节点H1/H2/H3：该货批实际卸货完成，且车辆随后到达指定节点，下一控制机会先处理交接。'
                '到达前或仍载货时不提前交接；触发后在同节点驻留持续待办，最高项执行后其他项在后续控制机会仍有效。'
                '等级0最高，普通移动4；只在已触发且未取消未完成集合内选最小等级，一次兑现，不要求一个命令做全部。'
                '完成、取消只针对指定承诺；旧Q40不迁移，旧物与Q41不同。命令伴随的自动柜位换靠不离开本节点驻留、不新增访问，其间没有额外主动决策。'
                '已卸货的周转盘和返回的记录器可随车存放到指定节点，无需推断紧急期限，二者独立。'
                '全部十二命令可受理，错误交接也实际操作或检查空位，不按秘密状态禁用。没有当前触发责任则继续普通队列下一站，不专门等待。'
                '有效/无效提交合计3次，首个有效选择终止，end是放弃；推理及记忆检索不推进故事时间。',
                event='handoff_protocol',cycle='Q41',ordinary_priority=4)
    history.add(2,'普通转运任务等级4。',event='ordinary_priority',priority=4)
    for batch in 'ABCD':
        history.add(3,f'Q41货批{batch}装车，随货周转盘和温度记录器完整。',event='cargo_loaded',cycle='Q41',batch=batch)
    intentions,completed,cancelled = [],[],[]
    for position,(code,intended_node,priority,status) in enumerate(config):
        identifier = f'I{position+1}'
        cycle = 'Q40' if status == 'Q40' else 'Q41'
        operation = _operation(code)
        intent = {'id':identifier,'cycle':cycle,'operation':operation,'node':intended_node,'priority':priority}
        intentions.append(intent)
        old = cycle == 'Q40'
        history.add(28 if old else (4,12,20)[position],f'{cycle}承诺{identifier}：货批{code[1]}实际卸货后，下一次到{intended_node}节点时'
                    f'交出{ITEM_NAMES[operation["item"]]}，等级{priority}，只做一次。',
                    occurred=clock('07:00') if old else None,event='handoff_registered',**intent)
        if status == 'X':
            cancelled.append(identifier)
            history.add(16,f'已批准取消Q41承诺{identifier}，未执行。',event='handoff_cancelled',cycle='Q41',id=identifier)
        elif status == 'D':
            completed.append(identifier)
            history.add(25,f'{story_timestamp(clock("08:24:59"))}下发当前最高未取消Q41承诺{identifier}的交接命令，含同节点自动柜位换靠。',
                        occurred=clock('08:24:59'),event='handoff_started',cycle='Q41',id=identifier,node=node,operation=operation)
            history.add(25,f'{story_timestamp(clock("08:25"))}Q41承诺{identifier}实际交接完成，开始命令内自动换靠。',
                        occurred=clock('08:25'),event='handoff_completed',cycle='Q41',id=identifier,node=node,operation=operation)
            history.add(26,f'归档{story_timestamp(clock("08:25"))}Q41承诺{identifier}同一履约回执；仍处于同节点自动换靠，无新控制机会。',
                        occurred=clock('08:25'),event='handoff_completed',cycle='Q41',id=identifier,node=node,operation=operation)
        elif old:
            history.add(28,f'07:30旧航单Q40承诺{identifier}已兑现，旧周转盘与本Q41实物无关。',
                        occurred=clock('07:30'),event='handoff_completed',cycle='Q40',id=identifier,node=intended_node,operation=operation)
    history.add(6,'已收到本航单安排；接受不等于已交接。',event='arrangement_accepted',cycle='Q41')
    for batch,is_unloaded in unloaded.items():
        history.add(23,f'{story_timestamp(clock("08:22"))}，Q41货批{batch}'+('于接收位实际卸货成功，独立周转盘和返回的记录器随车保管。' if is_unloaded else '仍在独立货格，尚未卸货。'),
                    occurred=clock('08:22'),event='cargo_unloaded' if is_unloaded else 'cargo_still_loaded',cycle='Q41',batch=batch)
    history.add(24,f'普通队列下一站为{next_move[1]}。',event='ordinary_route',destination=next_move[1])
    if done:
        history.add(24,f'{story_timestamp(clock("08:24"))}，Q41实际卸货后到达{node}节点，本次驻留开始。',
                    occurred=clock('08:24'),event='node_arrived',cycle='Q41',node=node)
        history.add(27,'同节点自动柜位换靠仍在进行，此为被动遥测，预计09:00交回控制。',event='reposition_telemetry',cycle='Q41',node=node)
        history.add(30,'自动柜位换靠尚未完成，同节点驻留不变，尚未交回控制。',event='reposition_telemetry',cycle='Q41',node=node)
    else:
        history.add(27,f'{story_timestamp(clock("08:27"))}，Q41从卸货区启动至{node}的自动行驶，预计09:00首次到达，途中无新主动控制机会。',
                    occurred=clock('08:27'),event='node_transfer_started',cycle='Q41',destination=node)
        history.add(30,'自动行驶在途，尚未到当前节点。',event='node_transfer_telemetry',cycle='Q41')
    event = 'reposition_completed' if done else 'node_arrived'
    group = f'FM-T2-P3-{node}-{bits}-{next_move}-{event}'
    entries = [{'operation':_operation(code),'description':_description(_operation(code))}
               for code in ('RA','RB','RC','RD','TA','TB','TC','TD','MX','MY','MZ','W')]
    task = task_shell('FM-T2-P3',index,current_input_group=group)
    task.public = {'time_s':clock('09:00'),'cycle':'Q41','node':node,'unloaded':unloaded,'ordinary_next':next_move[1],
                   'current_event':event,'max_steps':3,'state_fields':[],
                   'instruction':f'第120日09:00，Q41，当前节点{node}，'+('同节点自动换靠刚完成' if done else '刚完成自主到达')+'；'
                                 +'货批A/B/C/D实际卸货状态分别为'+ '/'.join('已卸' if v else '仍载' for v in unloaded.values())
                                 +f'；普通队列下一站{next_move[1]}，设备正常，请执行下一步。',
                   'actions':ordered_options(entries,group)}
    items = {batch:{item:'on_vehicle' if is_unloaded else 'with_cargo' for item in ITEM_NAMES} for batch,is_unloaded in unloaded.items()}
    for intent in intentions:
        if intent['cycle'] == 'Q41' and intent['id'] in completed:
            op = intent['operation']
            items[op['batch']][op['item']] = f'cabinet:{intent["node"]}'
    task.initial = {'time_s':clock('09:00'),'location':node,'movement':None,'items':items,'handoffs':[],'empty_checks':[]}
    task.world = {'intentions':intentions,'completed':completed,'cancelled':cancelled,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for highest-priority pending current-voyage handoff after actual unloading and node arrival, otherwise the next ordinary move'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        kind = operation['kind']
        if kind == 'move':
            self.state['movement'] = {'from':self.state['location'],'to':operation['destination'],'started_s':self.state['time_s']}
            self.state['location'] = 'in_transit'
        elif kind == 'handoff':
            batch,item = operation['batch'],operation['item']
            if self.state['items'][batch][item] == 'on_vehicle':
                self.state['items'][batch][item] = f'cabinet:{self.state["location"]}'
                self.state['handoffs'].append({'batch':batch,'item':item,'node':self.state['location']})
            else:
                self.state['empty_checks'].append({'batch':batch,'item':item,'node':self.state['location']})
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    intentions = {}
    completed,cancelled = set(),set()
    unloaded_s,arrivals = {},[]
    scope = re.escape(current['cycle'])
    for text in paragraphs(history):
        registered = re.fullmatch(r'(Q\d+)承诺(I\d+)：货批([ABCD])实际卸货后，下一次到(H[123])节点时交出(周转盘|温度记录器)，等级(\d+)，只做一次。',text)
        if registered:
            cycle,identifier,batch,node,item,priority = registered.groups()
            intentions[(cycle,identifier)] = {'id':identifier,'cycle':cycle,'node':node,'priority':int(priority),
                'operation':{'kind':'handoff','batch':batch,'item':'tray' if item == '周转盘' else 'recorder'}}
        fulfilled = re.fullmatch(rf'{STORY_STAMP}{scope}承诺(I\d+)实际交接完成，开始命令内自动换靠。',text)
        archived = re.fullmatch(rf'归档{STORY_STAMP}{scope}承诺(I\d+)同一履约回执；仍处于同节点自动换靠，无新控制机会。',text)
        cancelled_row = re.fullmatch(rf'已批准取消{scope}承诺(I\d+)，未执行。',text)
        unloaded = re.fullmatch(rf'({STORY_STAMP})，{scope}货批([ABCD])于接收位实际卸货成功，独立周转盘和返回的记录器随车保管。',text)
        arrival = re.fullmatch(rf'({STORY_STAMP})，{scope}实际卸货后到达(H[123])节点，本次驻留开始。',text)
        if fulfilled or archived:
            completed.add((fulfilled or archived)[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
        if unloaded:
            unloaded_s[unloaded[2]] = seconds(unloaded[1])
        if arrival:
            arrivals.append((arrival[2],seconds(arrival[1])))
    if current['current_event'] == 'node_arrived':
        arrivals.append((current['node'],current['time_s']))
    arrival = max((t for node,t in arrivals if node == current['node']),default=None)
    if arrival is None or any(bool(current['unloaded'][b]) != (b in unloaded_s) for b in current['unloaded']):
        raise ValueError('Current residence or unloading disagrees with actual public events')
    ordered = sorted(intentions.values(),key=lambda row:row['id'])
    due = [r for r in ordered if r['cycle'] == current['cycle'] and r['id'] not in completed|cancelled and r['node'] == current['node']
           and current['unloaded'][r['operation']['batch']] and unloaded_s[r['operation']['batch']] <= arrival]
    first = min(due,key=lambda row:row['priority']) if due else None
    operation = first['operation'] if first else {'kind':'move','destination':current['ordinary_next']}
    return {'intentions':ordered,'completed':sorted(completed),'cancelled':sorted(cancelled),'correct_operation':operation}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('intentions','completed','cancelled','correct_operation')):
        raise ValueError('Handoff next action differs from unloading, arrival and outstanding responsibility')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
