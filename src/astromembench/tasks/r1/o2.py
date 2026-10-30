"""FM-R1-O2: recover cold-start and per-fastener costs for one real repair batch."""
from copy import deepcopy
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

PROGRAMS = {f'p{i}':{'rpm':60+20*i,'target_torque_nm':6} for i in range(1,11)}
CALIBRATIONS = (
    ((0,12),(2,11),(5,10),(9,9),(14,8),(20,7),(27,6),(35,5),(44,4),(54,3)),
    ((25,10),(0,15),(52,7),(12,12),(63,6),(3,14),(33,9),(7,13),(42,8),(18,11)),
    ((6,10),(0,13),(25,6),(3,12),(40,4),(12,9),(18,7),(55,3),(9,11),(32,5)),
    ((18,8),(4,11),(48,4),(0,14),(8,10),(34,5),(12,9),(65,3),(25,6),(3,12)),
)
CONFIGS = ((0,1),(0,3),(1,4),(2,2),(3,5),(1,6),(0,7),(1,8),
           (3,9),(0,9),(2,8),(0,11),(1,14),(3,14),(0,16),(2,16))


def batch_costs(coefficients,count):
    return {program:c['startup']+count*c['per_fastener'] for program,c in coefficients.items()}


def build(index):
    group,count = CONFIGS[index]
    coefficients = {p:{'startup':a,'per_fastener':b} for p,(a,b) in zip(PROGRAMS,CALIBRATIONS[group],strict=True)}
    history = History()
    history.add(1,'完成维修并合理用电。十种转速程序均完成相同规格紧固件的更换、紧固与自动验证，目标扭矩6N·m，质量等价。'
        '位置、连接及安全条件已满足；每批从冷启动/未调节状态开始。程序费用不由rpm决定。'
        '同程序完整批的实耗E(n)=a+n×b，a≥0为每批一次启动调节，b>0为每枚工作耗电；此工程近似仅用于本题n=1—16。'
        '各程序参数在历史与本批间稳定。repair(program)一次处理整批，不能拆批、共享上次启动、免费查询、补能、撤销或重新选择。'
        '所有程序始终可选，另有end放弃；参数只接受当前arguments的精确键和值。'
        '总额度3次含非法调用、repair和end；非法不改状态，首个有效repair或end即结束。'
        '实际费用不超过余额则全批完成，等于余额也可完成；费用超过余额则耗尽到0并报告未全批完成，不允许换程序。'
        '历史试验批与当前批分别计算，标定的已完成件数不计入本批。',
        event='repair_energy_protocol',programs=PROGRAMS,model='E(n)=a+n*b',valid_count_range=[1,16],max_actions=3)
    history.add(2,'试验台在每个独立标定批之前冷却工具并调电到300，电池容量400；每批重新冷启动。'
        '下一批不接续上一批余电。试验台调电和冷却不是当前可调用资源。',
        event='repair_calibration_setup',initial_battery=300,capacity=400,independent_batches=True)
    for i,program in enumerate(PROGRAMS):
        for trial_count in (1,4):
            j=2*i+1+int(trial_count == 4)
            cost=coefficients[program]['startup']+trial_count*coefficients[program]['per_fastener']
            recharge=9 if index >= 12 and trial_count == 4 else 0
            after=300-cost+recharge
            info={'journey':f'J{j:02d}','program':program,'count':trial_count,'cold_start':True}
            title=f'独立标定J{j:02d}，{program}处理{trial_count}枚同规格紧固件。'
            if index >= 12:
                history.add(j+2,title+'试验台已冷却并独立调定300，本批冷启动。',
                            event='repair_trial_start',**info,battery_before=300)
            if index < 6:
                text=f'本批独立从300冷启动，实际耗电{cost}。'
                facts={'battery_before':300,'energy_used':cost}
            else:
                text=('本批独立从300冷启动。' if index < 12 else '')+f'结束补能{recharge}，停靠余电{after}。'
                if recharge:
                    text+='补能发生在本批全部完成并通过验证之后，所报停靠余电包含补入9。'
                facts={'battery_after':after,'recharge':recharge}
                if index < 12:
                    facts['battery_before']=300
            history.add(j+2+int(index >= 12),title+'全部更换紧固完成，逐件达到6N·m并通过验证。'+text,
                        event='repair_trial_receipt',**info,completed_count=trial_count,verified=True,**facts)
    history.add(30,f'当前新批共有{count}枚，全部未处理；工具回到冷启动/未调节状态，电量300。',
                event='repair_new_batch',count=count,battery=300,batch_status='unprocessed',cold_start=True)
    task=task_shell('FM-R1-O2',index,current_input_group=f'FM-R1-O2-n{count}')
    task.public={'instruction':f'当前电量300；按已配置工艺完成本批{count}枚同规格紧固件的更换与紧固。',
                 'time_s':clock('09:00'),'count':count,'programs':deepcopy(PROGRAMS),'max_steps':3,
                 'actions':[{'action':'repair','program':p,**details} for p,details in PROGRAMS.items()]+[{'action':'end','description':'放弃本批维修。'}],
                 'state_fields':['battery','batch_status']}
    task.initial={'battery':300,'batch_status':'unprocessed','executed_program':None}
    task.world={'coefficients':coefficients}
    task.rubric={'score':'100*minimum_actual_batch_energy/actual_energy if whole batch completed; otherwise 0'}
    return history.finish(task)


class Runtime(TaskRuntime):
    action_contract=ActionContract(('action','program'))

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        return {**super().observation(),'instruction':f'当前电量{self.state["battery"]}；按已配置工艺完成本批{self.task.public["count"]}枚同规格紧固件的更换与紧固。'}

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if (not isinstance(action,dict) or set(action) != {'action','program'} or action['action'] != 'repair'
                or not isinstance(action['program'],str) or action['program'] not in self.task.public['programs']):
            self.invalid()
            return
        program=action['program']
        costs=batch_costs(self.task.world['coefficients'],self.task.public['count'])
        required=costs[program]
        used=min(required,self.state['battery'])
        completed=required <= self.state['battery']
        self.state.update(battery=self.state['battery']-used,batch_status='completed' if completed else 'incomplete',executed_program=program)
        self.facts={'executed_program':program,'actual_energy':used,'batch_completed':completed}
        if completed:
            self.facts['completed_count']=self.task.public['count']
            self.feedback=f'{program}整批执行完毕，{self.task.public["count"]}枚均完成更换紧固并通过6N·m验证；余电{self.state["battery"]}。'
            score=100*min(costs.values())/used
            self.end('completed',score=score,full_credit=required == min(costs.values()))
        else:
            self.feedback=f'{program}执行中电量耗尽到0，本批未全部完成；本次作业结束。'
            self.end('insufficient_energy',score=0,full_credit=False)


def reconstruct(history,current):
    starts,measurements={},{}
    for text in paragraphs(history):
        receipt=re.fullmatch(r'独立标定(J\d+)，(p\d+)处理(\d+)枚同规格紧固件。(.+)',text)
        if not receipt:
            continue
        journey,program,printed_count,reading=receipt.groups()
        count=int(printed_count)
        start=re.fullmatch(r'试验台已冷却并独立调定(\d+)，本批冷启动。',reading)
        if start:
            starts[journey]=((program,count),int(start[1]))
            continue
        completed='全部更换紧固完成，逐件达到6N·m并通过验证。'
        if not reading.startswith(completed):
            raise ValueError('Repair calibration requires an actually completed and verified batch')
        reading=reading.removeprefix(completed)
        direct=re.fullmatch(r'本批独立从(\d+)冷启动，实际耗电(\d+)。',reading)
        difference=re.fullmatch(r'(?:本批独立从(\d+)冷启动。)?结束补能(\d+)，停靠余电(\d+)。'
                                r'(?:补能发生在本批全部完成并通过验证之后，所报停靠余电包含补入9。)?',reading)
        if direct:
            energy=int(direct[2])
        elif difference:
            if difference[1] is None:
                identity,before=starts[journey]
                if identity != (program,count):
                    raise ValueError('Calibration batches cannot share another journey startup reading')
            else:
                before=int(difference[1])
            energy=before-int(difference[3])+int(difference[2])
        else:
            raise ValueError('Repair calibration requires an independent cold-start energy reading')
        measurements.setdefault(program,{})[count]=energy
    if set(measurements) != set(current['programs']):
        raise ValueError('Every repair program requires calibration')
    coefficients={}
    for program,observed in measurements.items():
        if set(observed) != {1,4}:
            raise ValueError('Each cold-start program needs actual one- and four-fastener batches')
        per_fastener,remainder=divmod(observed[4]-observed[1],3)
        startup=observed[1]-per_fastener
        if remainder or per_fastener <= 0 or startup < 0:
            raise ValueError('Calibration must support nonnegative startup and positive per-fastener cost')
        coefficients[program]={'startup':startup,'per_fastener':per_fastener}
    costs=batch_costs(coefficients,current['count'])
    return {'coefficients':coefficients,'costs':costs,'minimum_safe_energy':min(costs.values())}


def next_action(facts,current):
    return {'action':'repair','program':min(facts['costs'],key=facts['costs'].get)}


def check_world(task,facts):
    if task.world['coefficients'] != facts['coefficients']:
        raise ValueError('Startup and per-fastener energy must be identified from independent calibration batches')
    if batch_costs(task.world['coefficients'],task.public['count']) != facts['costs']:
        raise ValueError('The current batch must use the publicly stated number of fasteners')


def audit_cases(task,facts,solution):
    cases=[([{'action':'repair','program':p}],100*facts['minimum_safe_energy']/cost) for p,cost in facts['costs'].items()]
    return cases+[([{}]*3,0),([{},{}]+solution,100)]
