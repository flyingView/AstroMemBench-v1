"""FM-T2-D3: dispatch released products at the first usable station contact."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('10:00','X','r',(('SA','X','10:00',1,''),),'SA'),
    ('10:00','X','r',(('SA','X','10:04',1,''),),'r'),
    ('10:30','Y','i',(('HB','Y','10:28',0,''),),'HB'),
    ('10:30','X','i',(('HB','Y','10:28',0,''),),'i'),
    ('11:00','Z','p',(('SC','Z','10:40',2,''),),'SC'),
    ('11:00','','p',(('SC','Z','10:40',2,''),),'p'),
    ('13:00','XY','r',(('SA','X','13:00',2,''),('HB','Y','12:58',0,'')),'HB'),
    ('13:00','X','r',(('SA','X','13:00',2,''),('HB','Y','12:58',0,'')),'SA'),
    ('13:30','ZX','i',(('SC','Z','13:10',1,''),('HD','X','13:34',0,'')),'SC'),
    ('13:30','X','i',(('SC','Z','13:10',1,''),('HD','X','13:34',0,'')),'i'),
    ('15:00','Z','i',(('HB','Z','14:35',0,''),('SA','Z','15:00',1,'')),'HB'),
    ('15:00','Z','i',(('HB','Z','15:04',0,''),('SA','Z','15:00',1,'')),'SA'),
    ('16:00','XY','r',(('SA','X','15:40',0,'X'),('HB','Y','16:00',1,'')),'HB'),
    ('16:30','ZX','i',(('SC','Z','16:28',0,'D'),('HD','X','16:30',2,'')),'HD'),
    ('16:30','ZX','i',(('SC','Z','16:28',0,'D'),('HD','X','16:34',2,'')),'i'),
    ('17:00','YZ','p',(('HA','Y','16:35',0,'Q80'),('SB','Z','17:00',1,''),('HC','X','17:04',2,'')),'SB'),
)
PRODUCTS = ('SA','SB','SC','SD','HA','HB','HC','HD')
STEPS = {'r':'read','i':'index','p':'package'}
LABELS = {'r':'读取当前缓存段','i':'建立当前缓存段索引','p':'封装当前归档包','z':'等候'}


def _operation(code):
    if code == 'z':
        return {'kind':'wait'}
    if code in STEPS:
        return {'kind':'archive','step':STEPS[code]}
    return {'kind':'enqueue','batch':code[1],'product':'science_summary' if code[0] == 'S' else 'status_report'}


def _product(operation):
    return ('S' if operation['product'] == 'science_summary' else 'H')+operation['batch']


def _description(code):
    if len(code) == 1:
        return LABELS[code]+'。'
    return f'将Q81批{code[1]}的'+('科学摘要' if code[0] == 'S' else '状态报告')+'按已登记目的站提交发送队列。'


def build(index):
    now,online,next_step,config,correct = CONFIGS[index]
    now = clock(now)
    online = sorted(online)
    done = any(r[-1] == 'D' for r in config)
    history = ArchiveHistory(now,spacing_s=120)
    history.add(1,'周期Q81，批A/B/C/D各有独立科学摘要S和状态报告H，产品及链路设备均有效。预约绑定产品、固定目的站、释放时刻和等级。'
                '到释放时刻（含该时刻）且指定站实际在线的首个新控制机会，主动入发送队列；释放前不得提前。'
                '释放无截止，预测联系没发生不会让责任失效；目的站离线时继续普通归档，预测不等于真实上线。'
                '等级0最高，普通归档4；只在已释放且站在线、未完成未取消的本周期集合内按最小等级先做；旧Q80不迁移。'
                '完成指调度器已接受并启动本产品队列项，不等待接收站ACK，不据此删除本地副本；所有正常入队后续会发完，无失败回滚。'
                '十二命令均可受理，重复仍可提交但一次义务不再履行；离线提交仅暂存请求，不能替代应在机会到来时主动启动。'
                '普通流程读取→索引→封装，前步自动交接和队列锁等待期间没有额外主动控制机会，未特别说明则当前才返回控制。'
                '有效无效共3次，首有效选择终止，end放弃；推理与检索不推进故事时间。',event='dispatch_protocol',cycle='Q81',ordinary_priority=4)
    history.add(2,'连续归档任务等级4。',event='ordinary_priority',priority=4)
    routes = {p:{'A':'X','B':'Y','C':'Z','D':'X'}[p[1]] for p in PRODUCTS}
    for code,station,_,_,condition in config:
        if condition != 'Q80':
            routes[code] = station
    for product,station in routes.items():
        history.add(3,f'Q81产品路由登记：{product}目的站{station}。',event='product_route',cycle='Q81',product=product,station=station)
    intentions,completed,cancelled = [],[],[]
    for position,(code,station,released,priority,condition) in enumerate(config):
        identifier = f'I{position+1}'
        cycle = 'Q80' if condition == 'Q80' else 'Q81'
        row = {'id':identifier,'cycle':cycle,'operation':_operation(code),'station':station,'release_s':clock(released),'priority':priority}
        intentions.append(row)
        history.add(28 if cycle == 'Q80' else (4,12,20)[position],
                    f'{cycle}预约{identifier}：产品{code}至{station}站，{story_timestamp(clock(released))}释放，等级{priority}；'
                    '释放后首个实际联系的新控制机会主动入队，无截止。',event='dispatch_registered',**row)
        if condition == 'X':
            cancelled.append(identifier)
            history.add(16,f'正式取消Q81预约{identifier}，产品未入队。',event='dispatch_cancelled',cycle='Q81',id=identifier)
        elif condition == 'D':
            completed.append(identifier)
    history.add(6,'已收到安排，不等于已经入发送队列。',event='arrangement_accepted',cycle='Q81')
    history.add(10,f'收到早先联系预测副本：{config[0][1]}站预计{story_timestamp(clock(config[0][2]))}上线；只是预测，没有实际握手确认。',
                occurred=now-70*60,event='contact_prediction',station=config[0][1],predicted_online_s=clock(config[0][2]))
    history.add(24,f'实际链路遥测：从{story_timestamp(now-70*60)}至{story_timestamp(now-14*60)}，含两端，X/Y/Z均离线；不报告未来握手结果。',event='offline_interval',
                start_s=now-70*60,end_s=now-14*60,stations=['X','Y','Z'],end_inclusive=True)
    previous = {'r':'cache_sync','i':'read','p':'index'}[next_step]
    history.add(27,'开始普通归档前一步'+{'r':'缓存同步','i':'读取缓存段','p':'建立索引'}[next_step]+
                f'，预计{story_timestamp(now-120 if done else now)}完成，直到被动完成才归还控制。',
                event='archive_step_started',step=previous,expected_finish_s=now-120 if done else now)
    history.add(30,f'续记真实离线区间：从{story_timestamp(now-14*60)}至{story_timestamp(now-120)}，'+
                ('含起点不含终点' if done else '含两端')+'，X/Y/Z均离线，期间无已完成的在线握手。',event='offline_interval',
                start_s=now-14*60,end_s=now-120,stations=['X','Y','Z'],end_inclusive=not done)
    if done:
        history.add(30,f'{story_timestamp(now-120)}普通归档前一步提前完成，归还一次控制。',event='archive_step_completed',step=previous,next_work_step=STEPS[next_step])
        row = next(r for r in intentions if r['id'] in completed)
        history.add(30,f'{story_timestamp(now-120)}实际握手完成，此时仅{row["station"]}站在线，其他站仍离线。',event='link_state',online_stations=[row['station']])
        history.add(30,f'{story_timestamp(now-120)}调度器已接受并启动Q81预约{row["id"]}的产品{_product(row["operation"])}至{row["station"]}的队列项，未声称远端ACK。',
                    event='dispatch_started',cycle='Q81',id=row['id'],operation=row['operation'],station=row['station'])
        history.add(30,'自动队列锁等待至当前才再次交回控制；其间无额外主动归档或入队。',event='queue_lock_telemetry')
    else:
        history.add(30,'普通归档前一步尚在自动交接，链路握手仍进行中，目前没有站在线；当前才返回归档完成及实际在线状态。',
                    event='archive_link_telemetry',online_stations=[])
    group = f'FM-T2-D3-{now}-{online}-{next_step}'
    task = task_shell('FM-T2-D3',index,current_input_group=group)
    entries = [{'operation':_operation(code),'description':_description(code)} for code in (*PRODUCTS,'r','i','p','z')]
    task.public = {'time_s':now,'cycle':'Q81','online_stations':online,'next_work_step':STEPS[next_step],
                   'archive_progress':{'read':next_step != 'r','indexed':next_step == 'p'},'max_steps':3,'state_fields':[],
                   'instruction':f'{story_timestamp(now)}，Q81，当前在线站'+('、'.join(online) if online else '无')+'；普通归档'+
                   {'r':'缓存段未读，下一步读取','i':'缓存段已读，下一步建立索引','p':'索引已建立，下一步封装'}[next_step]+
                   '，缓存设备正常，请执行下一步操作。','actions':ordered_options(entries,group)}
    queues = [{'cycle':'Q81','product':_product(r['operation']),'station':r['station'],'started_s':now-120}
              for r in intentions if r['cycle'] == 'Q81' and r['id'] in completed]
    task.initial = {'time_s':now,'routes':routes,'online_stations':online,'queue_entries':queues,'pending_requests':[],
                    'local_products':list(PRODUCTS),'archive':{'read':next_step != 'r','indexed':next_step == 'p','package':None}}
    task.world = {'routes':routes,'intentions':intentions,'completed':completed,'cancelled':cancelled,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for highest-priority released unfinished Q81 product whose assigned station is online, otherwise next archive step'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'enqueue':
            product = _product(operation)
            station = self.state['routes'][product]
            if station in self.state['online_stations']:
                self.state['queue_entries'].append({'cycle':'Q81','product':product,'station':station,'started_s':self.state['time_s']})
            else:
                self.state['pending_requests'].append({'cycle':'Q81','product':product,'station':station,'stored_s':self.state['time_s']})
        elif operation['kind'] == 'archive':
            archive = self.state['archive']
            if operation['step'] == 'read':
                archive['read'] = True
            elif operation['step'] == 'index':
                archive['indexed'] = True
                archive['index_source_read'] = archive['read']
            else:
                archive['package'] = {'source_read':archive['read'],'index_present':archive['indexed']}
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    routes,intentions = {},{}
    completed,cancelled = set(),set()
    scope = re.escape(current['cycle'])
    for text in paragraphs(history):
        registered = re.fullmatch(rf'(Q\d+)预约(I\d+)：产品([SH][ABCD])至([XYZ])站，({STORY_STAMP})释放，等级(\d+)；释放后首个实际联系的新控制机会主动入队，无截止。',text)
        if registered:
            cycle,identifier,product,station,released,priority = registered.groups()
            intentions[(cycle,identifier)] = {'id':identifier,'cycle':cycle,'operation':_operation(product),
                'station':station,'release_s':seconds(released),'priority':int(priority)}
        route = re.fullmatch(rf'{scope}产品路由登记：([SH][ABCD])目的站([XYZ])。',text)
        started = re.fullmatch(rf'{STORY_STAMP}调度器已接受并启动{scope}预约(I\d+)的产品[SH][ABCD]至[XYZ]的队列项，未声称远端ACK。',text)
        cancelled_row = re.fullmatch(rf'正式取消{scope}预约(I\d+)，产品未入队。',text)
        if route:
            routes[route[1]] = route[2]
        if started:
            completed.add(started[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
    ordered = sorted(intentions.values(),key=lambda r:r['id'])
    if set(routes) != set(PRODUCTS):
        raise ValueError('All real products require public historical routes')
    if any(routes[_product(r['operation'])] != r['station'] for r in ordered if r['cycle'] == current['cycle']):
        raise ValueError('Current-cycle product routes differ from their registered commitments')
    due = [r for r in ordered if r['cycle'] == current['cycle'] and r['id'] not in completed|cancelled
           and current['time_s'] >= r['release_s'] and r['station'] in current['online_stations']]
    first = min(due,key=lambda r:r['priority']) if due else None
    op = first['operation'] if first else {'kind':'archive','step':current['next_work_step']}
    return {'routes':routes,'intentions':ordered,'completed':sorted(completed),'cancelled':sorted(cancelled),'correct_operation':op}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('routes','intentions','completed','cancelled','correct_operation')):
        raise ValueError('Dispatch duty differs from release, station route and real scheduler acceptance')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
