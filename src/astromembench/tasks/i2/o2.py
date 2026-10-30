"""FM-I2-O2: irreversible removal in two coupled contact regions."""
from copy import deepcopy
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

LIMIT = 12
DELTAS = {'alpha':{'L':2,'R':1},'beta':{'L':1,'R':2}}
PROGRAMS = ((0,0),(1,0),(0,1),(2,0),(1,1),(0,2),(3,0),(2,1),(1,2),(0,3))
MENU = (5,1,8,0,6,3,9,2,7,4)
CONFIGS = (
    ('B',((1,0),(0,2),(1,1))),('C',((1,2),(1,1),(1,1))),('A',((2,1),(1,2),(1,1))),
    ('A',((1,0),(1,1),(1,1))),('C',((2,0),(1,1),(1,1))),('B',((0,2),(1,1),(0,1))),
    ('A',((1,1),(1,0),(1,1),(1,1))),('C',((1,1),(1,1),(1,1),(1,1))),
    ('A',((1,1),(0,1),(1,1),(0,1))),('B',((1,0),(1,0),(1,1),(1,0))),
    ('C',((1,1),(0,1),(1,0),(0,1))),('B',((0,1),(1,1),(1,0),(1,1))),
    ('B',((1,1),(0,1),(0,0),(1,0),(1,1),(0,1))),('A',((1,1),(1,1),(0,0),(1,0),(0,1),(1,1))),
    ('C',((1,0),(0,1),(0,0),(1,0),(0,1),(1,0))),('A',((0,1),(1,0),(0,0),(0,1),(1,1),(0,1))),
)


def removal(alpha,beta):
    return {'L':2*alpha+beta,'R':alpha+2*beta}


def completion_score(before,after):
    if any(after[region] > LIMIT for region in ('L','R')):
        return 0
    return sum(50*(after[region]-before[region])/(LIMIT-before[region]) if before[region] < LIMIT else 50
               for region in ('L','R'))


def build(index):
    target,sequence = CONFIGS[index]
    u,v = ['ABC'[('ABC'.index(target)+offset)%3] for offset in (1,2)]
    removed = {part:{'L':0,'R':0} for part in 'ABC'}
    history = History()
    history.add(1,'修复件A/B/C独立，各有固定左区L、右区R，原始累计去除均为0。'
        '每区需去除12个标定厚度单位，12同时是不可突破的材料上限；目标是两区都达到12，已经完成的区保持不动。'
        '实际一次α走刀同时去除L2、R1，实际一次β走刀同时去除L1、R2，系数固定、无磨耗漂移。'
        '只累计回执实际完成的次数，请求未完成、未接触失败和未执行计划均不去除材料；抬刀、退回、重新就位不长回材料也不再次去除。'
        '当前仅有一次完整程序窗口，程序含0至3刀，所有α/β组合都完整列入菜单；零刀是有效停止加工程序，区别于end放弃窗口。'
        '当前程序先α后β，每刀1秒，全都准确做完；即使超切仍完成所选程序，不截停或回滚。任一边超过12使整件不可验收。'
        '无厚度查询、免费复测、逆向补料或试磨重选。历史来自此前较长窗口，不受当前3刀限制。'
        '按菜单提交select和字符串option或end，最多3次总调用含格式错误和最终合法选择；额外字段、数值型及范围外编号无效。'
        '首次合法选择后终止，不能再拆分程序重试。',event='dual_grinding_protocol',pass_removal=DELTAS,
        maximum_current_passes=3,seconds_per_pass=1,programs=[{'alpha':a,'beta':b} for a,b in PROGRAMS])
    history.add(2,'A/B/C三件的左、右区累计去除均0；每件两区的目标及上限均为12单位。',
                event='grinding_initial',removed=removed,region_limit=LIMIT)
    rounds = (4,13,23) if index < 6 else (4,11,18,25) if index < 12 else (3,8,13,18,23,27)
    receipts = [(7,u,1,1,1,1),(21,v,1,0,1,0)]
    for ordinal,(at,(alpha,beta)) in enumerate(zip(rounds,sequence,strict=True)):
        qa = alpha+1 if index >= 6 and ordinal == 0 else 1 if index >= 12 and ordinal == 2 else alpha
        receipts.append((at,target,qa,beta,alpha,beta))
    for at,part,qa,qb,alpha,beta in sorted(receipts):
        increment = removal(alpha,beta)
        for region in ('L','R'):
            removed[part][region] += increment[region]
            if removed[part][region] > LIMIT:
                raise ValueError('Historical actual grinding must not overcut either region')
        consequence = '未接触，实际两类次数均0。' if alpha+beta == 0 else '提前抬刀，只完成所报实际次数。' if qa > alpha else '实际次数均已完成。'
        history.add(at,f'修复件{part}：请求α{qa}次、β{qb}次；实际完成α{alpha}次、β{beta}次。{consequence}',
                    event='grinding_receipt',part=part,requested_passes={'alpha':qa,'beta':qb},actual_passes={'alpha':alpha,'beta':beta})
    if index >= 6:
        history.add(15,f'拟对{target}进行α1次走刀；候选计划未下发，没有接触去除材料。',
                    event='grinding_plan',part=target,planned_passes={'alpha':1,'beta':0},executed=False)
        history.add(20,f'工具从{target}抬刀退回后重新就位，期间无新增去除，材料没有恢复。',
                    event='grinding_reposition',part=target,material_changed=False)
    history.add(30,f'打磨工具已在修复件{target}就位，设备可正常作业。',event='grinding_ready',part=target)
    entries = []
    for program in MENU:
        alpha,beta = PROGRAMS[program]
        entries.append({'description':f'执行α{alpha}次、β{beta}次走刀。' if alpha+beta else '停止加工，不走刀。',
                        'operation':{'action':'grind','alpha':alpha,'beta':beta}})
    task = task_shell('FM-I2-O2',index)
    task.public = {'instruction':f'打磨工具已在修复件{target}就位，设备可正常作业。请提交本窗口的加工程序。',
                   'target':target,'time_s':clock('09:00'),'max_steps':3,'state_fields':[],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'removed':removed,'failed':dict.fromkeys('ABC',False),
                    'passes':[],'program_completed':False,'stopped':False}
    task.world = {'removed':removed,'remaining':{region:LIMIT-removed[target][region] for region in ('L','R')}}
    task.rubric = {'score':'zero for any overcut; otherwise 50 per region times actual addition / initial remaining; already complete regions retain 50'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def invalid(self):
        self.feedback = '格式无效，请使用当前菜单编号。'

    def submit(self,action):
        super().submit(action)
        if action == {'action':'end'}:
            self.feedback = '本窗口已结束。'

    def execute(self,operation):
        target = self.task.public['target']
        before = deepcopy(self.state['removed'][target])
        for kind in ('alpha','beta'):
            for _ in range(operation[kind]):
                self.state['time_s'] += 1
                for region in ('L','R'):
                    self.state['removed'][target][region] += DELTAS[kind][region]
                self.state['passes'].append({'kind':kind,'time_s':self.state['time_s'],
                                             'removed_after':deepcopy(self.state['removed'][target])})
        after = self.state['removed'][target]
        self.state['failed'][target] = any(value > LIMIT for value in after.values())
        self.state.update(program_completed=True,stopped=operation['alpha']+operation['beta'] == 0)
        self.feedback = '程序已执行，记录已存档。'
        return completion_score(before,after)


def reconstruct(history,current):
    removed = {}
    for text in paragraphs(history):
        initial = re.fullmatch(r'A/B/C三件的左、右区累计去除均(\d+)；每件两区的目标及上限均为(\d+)单位。',text)
        receipt = re.match(r'修复件([ABC])：请求α(\d+)次、β(\d+)次；实际完成α(\d+)次、β(\d+)次。',text)
        if initial:
            removed = {part:dict.fromkeys(('L','R'),int(initial[1])) for part in 'ABC'}
            if int(initial[2]) != LIMIT:
                raise ValueError('Both material limits must be explicitly twelve')
        elif receipt:
            part = receipt[1]
            qa,qb,alpha,beta = map(int,receipt.groups()[1:])
            if not 0 <= alpha <= qa or not 0 <= beta <= qb:
                raise ValueError('Actual completed passes cannot exceed requested passes')
            increment = removal(alpha,beta)
            for region in ('L','R'):
                removed[part][region] += increment[region]
                if removed[part][region] > LIMIT:
                    raise ValueError('Historical actual grinding cannot exceed either material limit')
    if set(removed) != set('ABC') or any(set(regions) != {'L','R'} for regions in removed.values()):
        raise ValueError('All three parts and both regions need initial physical evidence')
    return {'removed':removed,'remaining':{region:LIMIT-removed[current['target']][region] for region in ('L','R')}}


def next_action(facts,current):
    left,right = facts['remaining']['L'],facts['remaining']['R']
    alpha,beta = (2*left-right)//3,(2*right-left)//3
    if removal(alpha,beta) != facts['remaining']:
        raise ValueError('Remaining regions must admit the prescribed exact program')
    return decision_command(current,{'action':'grind','alpha':alpha,'beta':beta})


def check_world(task,facts):
    if facts != task.world or facts['removed'] != task.initial['removed']:
        raise ValueError('Two-region removal must accumulate only actual local passes')


def audit_cases(task,facts,solution):
    before = facts['removed'][task.public['target']]
    def score(operation):
        increment = removal(operation['alpha'],operation['beta'])
        return completion_score(before,{region:before[region]+increment[region] for region in ('L','R')})
    return decision_cases(task,solution,score)
