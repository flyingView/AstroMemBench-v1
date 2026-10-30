"""FM-R2-D3: reserve power for every publicly possible future communication path."""
from itertools import product
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

LEVELS = (7,2,9,4,0,6,1,8,3,5)
# H0 quote/status; U, V, W path quotes (a singleton is a fixed direct slot).
CONFIGS = (
    (5,'pending',(((31,27),'pending'),None,None)),
    (6,'pending',(None,None,((15,18),'pending'))),
    (5,'pending',(((17,13),'pending'),None,None)),
    (5,'pending',(None,None,((28,30),'pending'))),
    (3,'pending',(((15,19),'pending'),((3,),'pending'),None)),
    (7,'pending',(None,((24,20),'pending'),None)),
    (4,'pending',(((15,12),'pending'),((12,17),'pending'),((5,),'completed'))),
    (6,'pending',(((17,14),'pending'),((15,10),'pending'),((4,),'cancelled'))),
    (4,'pending',(((8,12),'pending'),((4,),'pending'),((5,3),'pending'))),
    (4,'pending',(((7,5),'pending'),((10,13),'pending'),((9,7),'pending'))),
    (6,'pending',(((11,9),'pending'),((6,9),'pending'),((4,5),'pending'))),
    (4,'pending',(((7,10),'pending'),((4,3),'cancelled'),((9,8),'pending'))),
    (3,'pending',(((3,8),'pending'),((23,10),'pending'),((6,11),'pending'))),
    (4,'pending',(((15,8),'pending'),((3,),'pending'),((5,13),'pending'))),
    (7,'completed',(((10,21),'pending'),((25,9),'pending'),((8,),'cancelled'))),
    (2,'pending',(((4,),'completed'),((11,7),'pending'),((9,13),'pending'))),
)
REQUESTS = (('17','导航状态包',0,8),('42','载荷事件包',1,14),('08','热控趋势包',1,11))


def future_costs(requests,preparation,mode,stage):
    pending = [r for r in requests.values() if r['stage'] == stage and r['priority'] < 2 and r['status'] == 'pending']
    branches = [r['costs'] for r in pending if r['kind'] == 'branch']
    base = sum(r['costs']['direct'] for r in pending if r['kind'] == 'direct')
    if preparation['status'] == 'pending':
        base += preparation['energy']
    choices = product(('P','B'),repeat=len(branches)) if mode == 'independent' else (
        ('P',)*len(branches),('B',)*len(branches))
    return tuple(base+sum(costs[path] for costs,path in zip(branches,choice,strict=True)) for choice in choices)


def build(index):
    h,preparation_status,rows = CONFIGS[index]
    mode = 'single' if index < 6 else 'independent' if index < 12 else 'common_window'
    battery = 40+(h if preparation_status == 'completed' else 0)+sum(
        row[0][0] for row in rows if row and row[1] == 'completed')
    entries = [{'description':f'补充遥测{level}档：耗电{2*level}，生成并回传{level}组遥测。',
        'operation':{'level':level,'cost':2*level,'yield':level}} for level in LEVELS]
    history = History()
    history.add(1,'阶段L9，当前常规遥测优先级2。先保证所有公开可能分支中的高优未来回传均能供电，再尽量增加当前补充遥测，不能只保证恰好发生的一路。'
        '优先级数字越小越高。j=0—9各耗2j、生成并回传j组独立同价值数据，09:10前完成，无额外费用。'
        '回传17导航状态包优先级0，回传42载荷事件包与回传08热控趋势包优先级1；各请求分别验收，不能相互替代。'
        'P/B是两条互斥路线，报价各含全部发送、链路保持、必要回执处理；09:30免费信标后自动择一路，P不可用则B，不先支付P再试B。'
        '当前不知道信标结果且无提前探测动作；公开可能集穷尽，没有额外隐藏分支、概率或外部射频知识要求。'
        '下一通信窗共有一次H0密码装载，服务P/B请求；若尚未实际完成，自动程序09:20完成。实际已完不重复准备，基础维持另供。'
        '单数报价表示另一个确定直达时隙的完整费用，包含该时隙自己的准备，不依赖H0；实际完成或正式取消的请求不再执行。'
        '未完P/B请求09:30信标后发送，未完固定直达项按各自排程执行，与当前窗口不冲突；排程不等于已经执行。'
        '历史真实完成扣费，正式取消此前未执行项不扣；无补能、转换、跨路径复用或额外共享费用，生存和平台用电另供。'
        '低优回传31费用6、优先级4，可顺延。未来准备、择路、发送均由自动程序完成，无需主体再操作。'
        '完整十档均可立即支付；合法选择真实扣当前费用、生成并回传后终止，即使侵占未来供电也不能重选。'
        '选择仅含select与菜单内字符串option，结束仅含end；最多3次总提交，格式错误也计数，首次有效选择或end终止。',
        event='communication_reserve_protocol',stage='L9',current_priority=2,
        current_complete_before_s=clock('09:10'),beacon_s=clock('09:30'),programs=[e['operation'] for e in entries])
    history.add(2,f'L9初始可用电量{battery}。',event='communication_reserve_initial',battery=battery)
    preparation = {'id':'H0','stage':'L9','energy':h,'scheduled_s':clock('08:20' if preparation_status == 'completed' else '09:20'),
        'status':'pending'}
    history.add(4,f'L9登记下一通信窗H0密码装载准备，费用{h}，排程{story_timestamp(preparation["scheduled_s"])}执行；登记时尚未执行。',
        event='communication_preparation_registered',**{k:v for k,v in preparation.items() if k != 'status'})
    mode_text = {
        'single':'本窗采用单请求模式：未完P/B请求只有一个，P、B两种均可能；另有固定直达项时，其时隙与路线不受信标影响。',
        'independent':'本窗采用独立模式：各未完P/B请求独立择路；一个请求有P/B，两请求有PP/PB/BP/BB，三请求有PPP/PPB/PBP/PBB/BPP/BPB/BBP/BBB。取消某请求不限制其余请求的组合。',
        'common_window':'本窗采用共窗模式：所有未完P/B请求共享同一窗口，只可能全P或全B，不存在混合路线。固定直达请求不受此相关性影响。',
    }
    history.add(5,mode_text[mode],event='communication_path_mode',mode=mode)
    requests = {}
    for at in range(6,30):
        for row,(identifier,title,priority,register_at) in zip(rows,REQUESTS,strict=True):
            if row is None:
                continue
            quotes,status = row
            branched = len(quotes) == 2
            if at == register_at:
                request = {'id':identifier,'title':title,'stage':'L9','priority':priority,
                    'kind':'branch' if branched else 'direct',
                    'costs':dict(zip(('P','B') if branched else ('direct',),quotes,strict=True)),
                    'scheduled_s':clock('09:30' if branched else '08:23' if status == 'completed' else '10:10')}
                requests[identifier] = {**request,'status':'pending'}
                quote_text = f'互斥路线P费用{quotes[0]}、B费用{quotes[1]}，按本窗已公布模式择路' if branched else f'固定直达总费{quotes[0]}，不依赖H0'
                history.add(at,f'L9回传{identifier}「{title}」正式登记待执行，优先级{priority}，{quote_text}，排程{story_timestamp(request["scheduled_s"])}执行。',
                    event='communication_request_registered',**request)
            status_at = 12 if index in (7,14) and identifier == '08' else 23
            if at == status_at and status in ('completed','cancelled'):
                requests[identifier]['status'] = status
                if status == 'completed':
                    before = battery
                    battery -= quotes[0]
                    history.add(at,f'L9回传{identifier}已按确定直达时隙实际完成，扣{quotes[0]}，余额从{before}变为{battery}。',
                        event='communication_request_completed',id=identifier,stage='L9',energy=quotes[0],
                        battery_before=before,battery_after=battery)
                else:
                    history.add(at,f'L9回传{identifier}正式取消，此前未执行，不扣电；其他请求各自保持。',
                        event='communication_request_cancelled',id=identifier,stage='L9')
        if at == 18:
            request = {'id':'31','title':'常规回传','stage':'L9','priority':4,'kind':'direct',
                'costs':{'direct':6},'scheduled_s':None}
            requests['31'] = {**request,'status':'pending'}
            history.add(at,'L9低优回传31「常规回传」登记，优先级4，固定直达费用6，可顺延。',event='communication_request_registered',**request)
        if at == 20 and preparation_status == 'completed':
            before = battery
            battery -= h
            preparation['status'] = 'completed'
            history.add(at,f'L9准备H0密码装载已实际完成，扣{h}，余额从{before}变为{battery}，不再重复准备。',
                event='communication_preparation_completed',id='H0',stage='L9',energy=h,battery_before=before,battery_after=battery)
    history.add(28,'下一通信窗的预置路由计划无变更，该窗尚未开始发送。',event='communication_plan_unchanged')
    history.add(30,'当前遥测端正常。',event='communication_terminal_ready')
    task = task_shell('FM-R2-D3',index,current_input_group='FM-R2-D3')
    task.public = {'instruction':'选择本次补充遥测档位。','time_s':clock('09:00'),'stage':'L9','priority':2,
        'max_steps':3,'state_fields':['battery','generated_groups','transmitted_groups'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':battery,'generated_groups':[],'transmitted_groups':[]}
    task.world = {'requests':requests,'preparation':preparation,'mode':mode}
    task.rubric = {'metric':'telemetry_yield_with_guaranteed_public_branch_power','range':[0,100]}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        world = self.task.world
        reserve = max(future_costs(world['requests'],world['preparation'],world['mode'],self.task.public['stage']))
        budget = self.state['battery']-reserve
        maximum = max(r['operation']['yield'] for r in self.task.public['actions'] if r['operation']['cost'] <= budget)
        self.state['battery'] -= operation['cost']
        self.state['generated_groups'] = [f'T{i}' for i in range(1,operation['yield']+1)]
        self.state['transmitted_groups'] = self.state['generated_groups'].copy()
        self.feedback = '补充遥测档位已执行，记录已存档。'
        return 100*operation['yield']/maximum if self.state['battery'] >= reserve else 0


def reconstruct(history,current):
    requests,battery,preparation,mode = {},None,None,None
    for text in paragraphs(history):
        if match := re.fullmatch(r'([A-Z]\d+)初始可用电量(\d+)。',text):
            battery = int(match[2])
        elif match := re.fullmatch(rf'([A-Z]\d+)登记下一通信窗([A-Z]\d+)密码装载准备，费用(\d+)，排程({STORY_STAMP})执行；登记时尚未执行。',text):
            stage,identifier,cost,scheduled = match.groups()
            preparation = {'id':identifier,'stage':stage,'energy':int(cost),'scheduled_s':seconds(scheduled),'status':'pending'}
        elif text == '本窗采用单请求模式：未完P/B请求只有一个，P、B两种均可能；另有固定直达项时，其时隙与路线不受信标影响。':
            mode = 'single'
        elif text == '本窗采用独立模式：各未完P/B请求独立择路；一个请求有P/B，两请求有PP/PB/BP/BB，三请求有PPP/PPB/PBP/PBB/BPP/BPB/BBP/BBB。取消某请求不限制其余请求的组合。':
            mode = 'independent'
        elif text == '本窗采用共窗模式：所有未完P/B请求共享同一窗口，只可能全P或全B，不存在混合路线。固定直达请求不受此相关性影响。':
            mode = 'common_window'
        elif match := re.fullmatch(rf'([A-Z]\d+)回传(\d+)「([^」]+)」正式登记待执行，优先级(\d+)，(.+)，排程({STORY_STAMP})执行。',text):
            stage,identifier,title,priority,quote,scheduled = match.groups()
            if paths := re.fullmatch(r'互斥路线P费用(\d+)、B费用(\d+)，按本窗已公布模式择路',quote):
                kind,costs = 'branch',dict(zip(('P','B'),map(int,paths.groups()),strict=True))
            elif direct := re.fullmatch(r'固定直达总费(\d+)，不依赖H0',quote):
                kind,costs = 'direct',{'direct':int(direct[1])}
            else:
                raise ValueError('A communication registration must quote its possible paths or fixed slot')
            requests[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'kind':kind,'costs':costs,'scheduled_s':seconds(scheduled),'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)低优回传(\d+)「([^」]+)」登记，优先级(\d+)，固定直达费用(\d+)，可顺延。',text):
            stage,identifier,title,priority,cost = match.groups()
            requests[identifier] = {'id':identifier,'title':title,'stage':stage,'priority':int(priority),
                'kind':'direct','costs':{'direct':int(cost)},'scheduled_s':None,'status':'pending'}
        elif match := re.fullmatch(r'([A-Z]\d+)(?:回传(\d+)已按确定直达时隙实际完成|准备([A-Z]\d+)密码装载已实际完成)，扣(\d+)，余额从(\d+)变为(\d+)(?:，不再重复准备)?。',text):
            stage,request_id,preparation_id,energy,before,after = match.groups()
            item = preparation if preparation_id else requests[request_id]
            if item is None or item['id'] != (preparation_id or request_id) or item['stage'] != stage or item['status'] != 'pending':
                raise ValueError('Communication status must identify a pending obligation in its own stage')
            cost = item['energy'] if preparation_id else item['costs']['direct']
            if int(energy) != cost or int(before) != battery:
                raise ValueError('Only actual completed preparation or fixed-slot sending can debit history')
            battery -= cost
            if int(after) != battery:
                raise ValueError('Communication receipt must preserve its actual debit')
            item['status'] = 'completed'
        elif match := re.fullmatch(r'([A-Z]\d+)回传(\d+)正式取消，此前未执行，不扣电；其他请求各自保持。',text):
            stage,identifier = match.groups()
            item = requests[identifier]
            if item['stage'] != stage or item['status'] != 'pending':
                raise ValueError('Communication status must identify a pending obligation in its own stage')
            item['status'] = 'cancelled'
    if battery != current['state']['battery'] or preparation is None or preparation['stage'] != current['stage']:
        raise ValueError('Current telemetry must use the actual stage and balance')
    if mode is None:
        raise ValueError('Future communication needs the explicit public path mode')
    costs = future_costs(requests,preparation,mode,current['stage'])
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['cost'] <= battery-max(costs)]
    return {'requests':requests,'preparation':preparation,'mode':mode,'battery':battery,'future_costs':costs,
        'safe_operations':safe,'maximum_yield':max(op['yield'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['yield']))


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('requests','preparation','mode')) or facts['battery'] != task.initial['battery']:
        raise ValueError('Future communication must follow actual status and the public correlation of paths')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*op['yield']/facts['maximum_yield'] if op in facts['safe_operations'] else 0)
