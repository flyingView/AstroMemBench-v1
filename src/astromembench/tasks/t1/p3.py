"""FM-T1-P3: refrigeration pauses accumulated exposure without resetting it."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('A',20,40,'R'),('A',50,70,'L'),('A',70,90,'C'),('A',100,100,None),('B',80,90,'C'),('C',10,40,'R'),
    ('B',55,25,'R'),('B',75,25,'L'),('C',65,75,'L'),('C',85,75,'C'),('A',110,65,'C'),('A',120,65,None),
    ('A',43,47,'R'),('A',43,48,'L'),('C',119,61,'C'),('C',120,61,None),
)
ROUTES = {
    'R':{'name':'快坡','duration_s':180,'warm_s':90},
    'L':{'name':'气闸','duration_s':300,'warm_s':30},
    'C':{'name':'全冷链','duration_s':420,'warm_s':0},
}


def _operation(cargo=None,route=None):
    return {'cargo':cargo,'route':route}


def build(index):
    target,p,q,best = CONFIGS[index]
    intervals = {'A':(20,20),'B':(70,70),'C':(100,100)}
    intervals[target] = (p,q)
    now = clock('12:00')
    history = ArchiveHistory(now)
    add = history.add

    add(1,'本批Q8货箱A/B/C各一件、当前均在冷藏，任务只指定其中一件，不能换箱。'
          '从实际首次出冷藏累计暖态暴露，冷藏暂停计时但不清零；计划或预约不产生实际暴露，Q7同名不是本批物件。'
          '允许暖态总时间不超过180秒，恰等合格；一旦超过，回冷也不能恢复。'
          '三通道均授权、可通行、能量充足：快坡R总耗时180秒含暖态90秒；气闸L总耗时300秒含暖态30秒；全冷链C总耗时420秒含暖态0秒。'
          '暖态段已包含在总耗时内，不另加完成时间；整程结束累计暖态不超过180才合格。'
          '公开目标是完成指定箱合格交付且尽早到达；没有可行交付时保持冷藏隔离。'
          '有效/无效提交共最多3次，首个有效选择后结束；转运动作实际完成整程，错误交付不能撤回；end是放弃，记忆检索不推进故事时钟。'
          '180秒为合成评测模型，不是真实药剂标准。',
        event='cold_transfer_protocol',cycle='Q8',warm_limit_s=180,routes=ROUTES)

    def transition(at,kind,cargo,occurred,cycle='Q8'):
        text = '实际离开冷藏' if kind == 'cold_exit' else '实际返回冷藏，暂停但不清零暖态计时'
        add(at,f'{story_timestamp(occurred)}，{cycle}货箱{cargo}{text}。',occurred=occurred,
            event=kind,cycle=cycle,cargo=cargo)

    for cargo,(first,second) in intervals.items():
        transition(4,'cold_exit',cargo,clock('11:00'))
        transition(4 if index < 6 else 8,'cold_entry',cargo,clock('11:00')+first)
        transition(15,'cold_exit',cargo,clock('11:30'))
        transition(15 if index < 6 else 22,'cold_entry',cargo,clock('11:30')+second)
        if index >= 12:
            transition(11,'cold_exit',cargo,clock('10:00',119),'Q7')
            transition(11,'cold_entry',cargo,clock('10:00:10',119),'Q7')
    if index >= 12:
        add(26,'第120日11:58提交下一次取箱计划，未执行。',occurred=clock('11:58'),event='retrieval_planned')
        add(28,'三箱Q8货物实际仍在冷藏。',event='cold_storage_status',cycle='Q8',cargo_ids=list(intervals))
    add(30,'转运计划已生成，三箱尚未离库。',event='transfer_ready')
    group = f'FM-T1-P3-{target}'
    entries = [{'operation':_operation(cargo,code),
                'description':f'送{cargo}经{route["name"]}，总耗时{route["duration_s"]}秒（已含暖态{route["warm_s"]}秒）。',
                'duration_s':route['duration_s'],'warm_s':route['warm_s']}
               for cargo in intervals for code,route in ROUTES.items()]
    entries.append({'operation':_operation(),'description':'保持冷藏隔离。','duration_s':0,'warm_s':0})
    task = task_shell('FM-T1-P3',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q8','target':target,'cargo_ids':list(intervals),'routes':ROUTES,'max_steps':3,'state_fields':[],
                   'instruction':f'第120日12:00:00，Q8指定货箱{target}，出库转运计划已完成，冷库和三通道均可用。请选择实际操作。',
                   'actions':ordered_options(entries,group)}
    task.initial = {'time_s':now,'cargo':{c:{'warm_s':sum(parts),'location':'cold_storage'} for c,parts in intervals.items()},'delivery':None}
    task.world = {'best_route':best,'best_duration_s':0 if best is None else ROUTES[best]['duration_s']}
    task.rubric = {'score':'100*fastest_feasible_duration/actual_duration for target on-time delivery; no feasible route requires isolation'}
    return history.finish(task)


def _feasible(age,routes,limit):
    return [code for code,r in routes.items() if age+r['warm_s'] <= limit]


def _score(operation,target,age,routes,limit):
    feasible = _feasible(age,routes,limit)
    if operation['cargo'] is None:
        return 100 if not feasible else 0
    if operation['cargo'] != target or operation['route'] not in feasible:
        return 0
    return 100*min(routes[r]['duration_s'] for r in feasible)/routes[operation['route']]['duration_s']


class Runtime(DecisionRuntime):
    def execute(self,operation):
        cargo,route = operation['cargo'],operation['route']
        original_age = self.state['cargo'][self.task.public['target']]['warm_s']
        if cargo is None:
            self.feedback = '保持冷藏隔离，未离库转运。'
        else:
            self.state['time_s'] += ROUTES[route]['duration_s']
            self.state['cargo'][cargo]['warm_s'] += ROUTES[route]['warm_s']
            self.state['cargo'][cargo]['location'] = 'receiver'
            self.state['delivery'] = {'cargo':cargo,'route':route,'arrival_s':self.state['time_s']}
            self.feedback = f'Q8货箱{cargo}经{ROUTES[route]["name"]}实际交付，到达时刻{story_timestamp(self.state["time_s"])}。'
        return _score(operation,self.task.public['target'],original_age,ROUTES,180)


def reconstruct(history,current):
    events = {c:[] for c in current['cargo_ids']}
    limit,routes = None,None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        if f'本批{current["cycle"]}货箱' in text:
            bound = re.search(r'允许暖态总时间不超过(\d+)秒，恰等合格',text)
            limit = int(bound[1]) if bound else None
            routes = {code:{'name':name,'duration_s':int(duration),'warm_s':int(warm)}
                      for name,code,duration,warm in re.findall(r'([^：；。]+)([RLC])总耗时(\d+)秒含暖态(\d+)秒',text)}
        transition = re.search(rf'({STORY_STAMP})，{cycle}货箱([A-Z])实际(离开冷藏。|返回冷藏，暂停但不清零暖态计时。)',text)
        if transition:
            events[transition[2]].append((seconds(transition[1]),transition[3].startswith('离开')))
    ages = {}
    for cargo,records in events.items():
        start,total = None,0
        for occurred,is_exit in sorted(records,key=lambda r:r[0]):
            if is_exit:
                if start is not None:
                    raise ValueError('Warm exposure has two exits without reentry')
                start = occurred
            else:
                if start is None:
                    raise ValueError('Cold reentry without a real exit')
                total += occurred-start
                start = None
        if start is not None or not records or limit is None or routes is None or set(routes) != {'R','L','C'}:
            raise ValueError('Incomplete exposure history or physical transfer model')
        ages[cargo] = total
    feasible = _feasible(ages[current['target']],routes,limit)
    best = min(feasible,key=lambda r:routes[r]['duration_s']) if feasible else None
    return {'warm_ages':ages,'routes':routes,'warm_limit_s':limit,'best_route':best,'target':current['target']}


def next_action(facts,current):
    best = facts['best_route']
    return decision_command(current,_operation(current['target'],best) if best else _operation())


def check_world(task,facts):
    best = facts['best_route']
    duration = 0 if best is None else facts['routes'][best]['duration_s']
    if facts['warm_ages'] != {c:s['warm_s'] for c,s in task.initial['cargo'].items()} or best != task.world['best_route'] or duration != task.world['best_duration_s']:
        raise ValueError('Transfer optimum differs from actual warm intervals and route exposure')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['target'],facts['warm_ages'][facts['target']],facts['routes'],facts['warm_limit_s']))
