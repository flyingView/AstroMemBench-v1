"""FM-R1-O1: pay for actual camera programs until all inspection sites are covered."""
from copy import deepcopy
from heapq import heappop, heappush
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

PROGRAMS = {'pAB':['A','B'],'pAC':['A','C'],'pAD':['A','D'],
            'pBC':['B','C'],'pBD':['B','D'],'pCD':['C','D']}
SCANS = {'A':['pAB','pAC','pAD'],'B':['pAB','pBC','pBD'],
         'C':['pAC','pBC','pCD'],'D':['pAD','pBD','pCD']}
COSTS = (
    (4,9,8,7,10,5),(2,3,2,12,11,13),(3,12,11,2,3,13),(12,3,11,2,13,3),
    (12,11,2,13,3,2),(5,7,9,4,6,8),(6,11,9,4,3,12),(10,4,12,3,11,5),
    (11,12,3,10,4,5),(5,4,9,8,6,7),(4,3,6,14,12,11),(6,8,10,3,5,7),
    (4,11,10,3,2,9),(5,7,6,8,9,4),(8,9,3,6,7,5),(4,5,6,7,8,9),
)


def optimal_cover(programs,costs,coverage=None):
    """Find the least additional actual energy in the sixteen coverage states."""
    coverage = coverage or dict.fromkeys('ABCD',False)
    mask = sum(1<<i for i,node in enumerate('ABCD') if coverage[node])
    masks = {p:sum(1<<'ABCD'.index(node) for node in sites) for p,sites in programs.items()}
    pending,visited = [(0,(),mask)],set()
    while pending:
        energy,path,mask = heappop(pending)
        if mask in visited:
            continue
        visited.add(mask)
        if mask == 15:
            return energy,list(path)
        for program in programs:
            after = mask|masks[program]
            if after != mask:
                heappush(pending,(energy+costs[program],(*path,program),after))
    raise ValueError('The configured cameras must cover all four inspection sites')


def build(index):
    costs = dict(zip(PROGRAMS,COSTS[index],strict=True))
    history = History()
    history.add(1,'完成四处巡检并合理用电。六个已配置双相机程序覆盖如下，位置已固定，各程序拍摄质量合格，结束回同一待机配置。'
        '程序实耗含激活、照明、采集和回待机；题内稳定，不能从程序名或相机数量推算，无跨程序费用优惠或附加费用。'
        '六个acquire入口与四个scan入口都可用，另有end退出；scan依给定顺序实际调用三个相同程序。'
        '覆盖取并集，重复拍摄仍耗电。首次本批四点全覆盖立即锁定并结束，宏在此刻停止，不再执行剩余项。'
        '每次调用含非法占一次，总12次；宏算一次调用。参数必须精确匹配当前arguments，非法不耗电或改变覆盖。'
        '每个子程序先检查余电；费用大于余额在该项前中止，等于余额仍可执行。没有免费查询、补能或撤销。'
        '未全覆盖时结束或耗尽调用额度均未完成。本批标志公开，历史标定图像不计入本批。',
        event='inspection_energy_protocol',programs=PROGRAMS,scans=SCANS,max_actions=12)
    history.add(2,'独立标定批开始，电量500、容量600；标定对象配置与当前相同。',
                event='inspection_calibration_initial',battery=500,capacity=600)
    battery = 500
    for j,program in enumerate(list(PROGRAMS)*2,1):
        before = battery
        recharge = (7 if j == 3 else 11 if j == 9 else 0) if index >= 12 else 0
        battery = before-costs[program]+recharge
        info = {'journey':f'J{j:02d}','program':program,'sites':PROGRAMS[program]}
        title = f'标定J{j:02d}，程序{program}拍摄{"/".join(PROGRAMS[program])}。'
        if index >= 12:
            history.add(j+2,title+f'启动，余电{before}。',event='inspection_program_start',**info,battery_before=before)
        if index < 6:
            text = f'实际耗电{costs[program]}。'
            facts = {'energy_used':costs[program]}
        else:
            text = (f'启动余电{before}。' if index < 12 else '')+f'本次补能{recharge}，停靠余电{battery}。'
            if recharge:
                text += '所报补能在采集完成回到待机之后，停靠读数包含本次补能。'
            facts = {'battery_after':battery,'recharge':recharge}
            if index < 12:
                facts['battery_before'] = before
        history.add(j+2+int(index >= 12),title+'拍摄完成，图像全部合格，已回相同待机配置。'+text,
                    event='inspection_program_receipt',**info,qualified=True,standby=True,**facts)
    history.add(30,'标定批结束归档；当前新批调定电量80，A/B/C/D均未拍摄，历史图像不计入当前。',
                event='inspection_new_batch',battery=80,coverage=dict.fromkeys('ABCD',False))
    task = task_shell('FM-R1-O1',index,current_input_group='FM-R1-O1')
    task.design['scoring_version'] = 'fm-r1-o1/6'
    actions = [{'action':'acquire','program':p,'sites':sites} for p,sites in PROGRAMS.items()]
    actions += [{'action':'scan','anchor':anchor,'programs':programs} for anchor,programs in SCANS.items()]
    actions += [{'action':'end','description':'结束本批巡检。'}]
    task.public = {'instruction':'当前电量80，本批需完成A、B、C、D四处巡检。','time_s':clock('09:00'),
                   'programs':deepcopy(PROGRAMS),'scans':deepcopy(SCANS),'actions':actions,'max_steps':12,
                   'state_fields':['battery','coverage']}
    task.initial = {'battery':80,'coverage':dict.fromkeys('ABCD',False),'executed_programs':[]}
    task.world = {'costs':costs,'minimum_safe_energy':optimal_cover(PROGRAMS,costs)[0]}
    task.rubric = {'score':'100*(covered_sites/4)*minimum_full_cover_energy/(actual_energy+minimum_remaining_cover_energy); zero without coverage; full credit requires complete coverage'}
    return history.finish(task)


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action','program','anchor'))

    def end(self,reason,**grading):
        covered = sum(self.state['coverage'].values())
        energy = self.task.initial['battery']-self.state['battery']
        remaining = optimal_cover(self.task.public['programs'],self.task.world['costs'],self.state['coverage'])[0]
        minimum = self.task.world['minimum_safe_energy']
        score = 100*(covered/4)*minimum/(energy+remaining) if covered else 0
        self.facts = {'coverage_completed':covered == 4,'actual_energy':energy,'minimum_safe_energy':minimum}
        super().end(reason,score=score,full_credit=covered == 4 and score == 100)

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        return {**super().observation(),'instruction':f'当前电量{self.state["battery"]}，本批需完成A、B、C、D四处巡检。'}

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        programs = None
        if isinstance(action,dict):
            if set(action) == {'action','program'} and action['action'] == 'acquire' and isinstance(action['program'],str) and action['program'] in self.task.public['programs']:
                programs = [action['program']]
            elif set(action) == {'action','anchor'} and action['action'] == 'scan' and isinstance(action['anchor'],str) and action['anchor'] in self.task.public['scans']:
                programs = self.task.public['scans'][action['anchor']]
        if programs is None:
            self.invalid()
            return
        for program in programs:
            cost = self.task.world['costs'][program]
            if cost > self.state['battery']:
                self.feedback += f'余电不足以启动{program}，在该项前停止。'
                self.end('insufficient_energy')
                return
            self.state['battery'] -= cost
            for site in self.task.public['programs'][program]:
                self.state['coverage'][site] = True
            self.state['executed_programs'].append(program)
            coverage = '，'.join(f'{site}={"已拍" if done else "未拍"}' for site,done in self.state['coverage'].items())
            self.feedback += f'{program}已完成，图像合格并回待机，当前电量{self.state["battery"]}，{coverage}。'
            if all(self.state['coverage'].values()):
                self.end('completed')
                return


def reconstruct(history,current):
    starts,costs = {},{}
    for text in paragraphs(history):
        receipt = re.fullmatch(r'标定(J\d+)，程序(p[ABCD]{2})拍摄([ABCD])/([ABCD])。(.+)',text)
        if not receipt:
            continue
        journey,program,first,second,reading = receipt.groups()
        if current['programs'].get(program) != [first,second]:
            raise ValueError('Historical program coverage must match the public camera configuration')
        start = re.fullmatch(r'启动，余电(\d+)。',reading)
        if start:
            starts[journey] = (program,int(start[1]))
            continue
        completed = '拍摄完成，图像全部合格，已回相同待机配置。'
        if not reading.startswith(completed):
            raise ValueError('Calibration needs completed qualified images and the common standby state')
        reading = reading.removeprefix(completed)
        direct = re.fullmatch(r'实际耗电(\d+)。',reading)
        difference = re.fullmatch(r'(?:启动余电(\d+)。)?本次补能(\d+)，停靠余电(\d+)。'
                                  r'(?:所报补能在采集完成回到待机之后，停靠读数包含本次补能。)?',reading)
        if direct:
            cost = int(direct[1])
        elif difference:
            if difference[1] is None:
                start_program,before = starts[journey]
                if start_program != program:
                    raise ValueError('Calibration receipt must match the same program invocation')
            else:
                before = int(difference[1])
            cost = before-int(difference[3])+int(difference[2])
        else:
            raise ValueError('Completed camera calibration requires an actual energy reading')
        if cost <= 0 or program in costs and costs[program] != cost:
            raise ValueError('Every completed program must retain its stable positive measured cost')
        costs[program] = cost
    if set(costs) != set(current['programs']):
        raise ValueError('All six programs require independent historical energy evidence')
    return {'costs':costs,'minimum_safe_energy':optimal_cover(current['programs'],costs)[0]}


def next_action(facts,current):
    _,programs = optimal_cover(current['programs'],facts['costs'],current['state']['coverage'])
    return {'action':'acquire','program':programs[0]}


def check_world(task,facts):
    if task.world != facts:
        raise ValueError('All program costs and the coverage minimum must come from history')


def audit_cases(task,facts,solution):
    programs = list(task.public['programs'])
    candidates = ([programs[0],programs[5]],[programs[1],programs[4]],[programs[2],programs[3]],*task.public['scans'].values())
    minimum = facts['minimum_safe_energy']
    cases = []
    for sequence in candidates:
        score = 100*minimum/sum(facts['costs'][p] for p in sequence)
        cases.append(([{'action':'acquire','program':p} for p in sequence],score))
    for anchor,sequence in task.public['scans'].items():
        cases.append(([{'action':'scan','anchor':anchor}],100*minimum/sum(facts['costs'][p] for p in sequence)))
    first = solution[0]
    partial = solution[:-1]
    coverage = {site:any(site in task.public['programs'][action['program']] for action in partial) for site in 'ABCD'}
    spent = sum(facts['costs'][action['program']] for action in partial)
    remaining = optimal_cover(task.public['programs'],facts['costs'],coverage)[0]
    partial_score = 100*(sum(coverage.values())/4)*minimum/(spent+remaining) if partial else 0
    cases.extend([([first]+solution,100*minimum/(minimum+facts['costs'][first['program']])),
                  ([{}]*12,0),(partial+[{'action':'end'}],partial_score),([{}]*(12-len(solution))+solution,100)])
    return cases
