"""FM-T2-D2: paired reference duties after a completed block and geometry entry."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Angle, completed K3 bits, next science target, (code, lower, upper, priority, state), answer.
CONFIGS = (
    (10,'1000','SB',(('BA',10,14,1,''),),'BA'),
    (9,'1000','SB',(('BA',10,14,1,''),),'SB'),
    (16,'0100','SC',(('RB',15,19,0,''),),'RB'),
    (16,'0000','SC',(('RB',15,19,0,''),),'SC'),
    (28,'0001','SA',(('RD',27,31,1,''),),'RD'),
    (28,'0000','SA',(('RD',27,31,1,''),),'SA'),
    (12,'1100','SC',(('BA',12,16,2,''),('RB',11,15,0,'')),'RB'),
    (12,'1000','SC',(('BA',12,16,2,''),('RB',11,15,0,'')),'BA'),
    (18,'0011','SA',(('BC',17,21,1,''),('RD',20,24,0,'')),'BC'),
    (16,'0011','SA',(('BC',17,21,1,''),('RD',20,24,0,'')),'SA'),
    (24,'1010','SB',(('RA',24,28,0,''),('BC',23,27,2,'')),'RA'),
    (24,'0010','SB',(('RA',24,28,0,''),('BC',23,27,2,'')),'BC'),
    (14,'1100','SC',(('BA',13,17,0,'X'),('RB',14,18,1,'')),'RB'),
    (20,'0011','SA',(('BC',19,23,0,'D'),('RD',20,24,2,'')),'RD'),
    (20,'0011','SA',(('BC',19,23,0,'D'),('RD',22,26,2,'')),'SA'),
    (26,'1000','SB',(('RA',26,30,1,''),),'RA'),
)
NAMES = {'background':'离轴背景','standard':'标准参考','science':'下一普通科学曝光'}


def _operation(code):
    return {'kind':'wait'} if code == 'Z' else {'kind':{'B':'background','R':'standard','S':'science'}[code[0]],'target':code[1]}


def _description(code):
    if code == 'Z':
        return '等待，不采集。'
    op = _operation(code)
    detail = '，偏置3度、曝光2秒' if code[0] == 'B' else '，曝光1秒'
    pairing = 'K3配套' if code[0] != 'S' else ''
    return f'采集目标{code[1]}{pairing}{NAMES[op["kind"]]}{detail}。'


def build(index):
    theta,bits,normal,config,correct = CONFIGS[index]
    finished = dict(zip('ABCD',(v == '1' for v in bits),strict=True))
    done = any(r[-1] == 'D' for r in config)
    history = History()
    history.add(1,'周期Q71，目标A/B/C/D各有独立科学块K3。预约绑定目标、K3、背景或标准参考、几何带[l,u)及等级p。'
                '只有该K3实际完成且当前角度在带内才执行，含左不含右；等级0最高，普通队列4，只在已触发未取消未完成项中先做最小p。'
                '每预约一次，旧周期Q70或旧K2产品不迁移。未完成K3的预约不参加优先级比较，没有已触发待办才继续普通队列，不能提前参考或等待。'
                '几何角单调不下降，各带按本轨首次进入后的新控制机会兑现；未到带至少相距1度，下一普通1秒曝光角度只加0.1度。'
                '离轴背景固定偏置3度曝光2秒，标准参考固定1秒；所有操作在所有带均安全可执行，参数与质量已由低层保证。'
                '普通S对未完K3只增加一个子积分，不完成整块；已完K3则开始下一K4子曝光，不删除或重做K3，也不履行参考预约。'
                '自动跟踪组和内置姿态复位期间无中途主动控制。所有十三项可受理，错误对象或产品也真实曝光。'
                '有效无效共3次，首有效选择终止，end放弃；推理与检索不推进故事时间。',event='science_duty_protocol',cycle='Q71',block='K3')
    history.add(2,'普通科学队列等级4。',event='ordinary_priority',priority=4)
    intentions,completed,cancelled = [],[],[]
    if index == 15:
        history.add(3,'归档旧A-K2：07:50科学块完成，旧RA预约带[0,2)、等级1。',
                    occurred=clock('07:50'),event='old_block_archive',cycle='Q71',block='K2',target='A',
                    science_completed_s=clock('07:50'),operation=_operation('RA'),lower_degrees=0,upper_degrees=2,priority=1)
        history.add(3,'07:54:59在0度启动旧A-K2的1秒标准参考。',occurred=clock('07:54:59'),
                    event='reference_started',cycle='Q71',block='K2',id='OLD',operation=_operation('RA'),theta_degrees=0,duration_s=1)
        history.add(3,'07:55旧A-K2标准参考完成；随后角度保持0到08:22，K3为后续独立块。',
                    occurred=clock('07:55'),event='reference_completed',cycle='Q71',block='K2',id='OLD',operation=_operation('RA'),theta_degrees=0)
    history.add(24,f'普通科学队列下一目标{normal[1]}。',occurred=clock('08:24'),received=clock('08:24'),event='ordinary_queue',target=normal[1])
    for position,(code,lower,upper,priority,status) in enumerate(config):
        identifier = f'I{position+1}'
        op = _operation(code)
        row = {'id':identifier,'cycle':'Q71','block':'K3','operation':op,'lower_degrees':lower,'upper_degrees':upper,'priority':priority}
        intentions.append(row)
        history.add((4,12,20)[position],f'Q71/K3预约{identifier}：目标{code[1]}块实际完成后，在几何角[{lower},{upper})度'
                    f'主动采集{NAMES[op["kind"]]}，等级{priority}，一次。',event='reference_registered',**row)
        if status == 'X':
            cancelled.append(identifier)
            history.add(16,f'正式取消Q71/K3预约{identifier}，未拍摄。',event='reference_cancelled',cycle='Q71',block='K3',id=identifier)
        elif status == 'D':
            completed.append(identifier)
            history.add(24,f'{story_timestamp(clock("08:24:58"))}导航角19度，立即启动Q71/K3最高预约{identifier}的BC两秒曝光，曝光中角度保持19度。',
                        occurred=clock('08:24:58'),received=clock('08:24:58'),event='reference_started',cycle='Q71',block='K3',id=identifier,
                        operation=op,theta_degrees=19,duration_s=2)
            history.add(25,f'{story_timestamp(clock("08:25"))}，Q71/K3预约{identifier}的BC实际完成，几何角19度，进入命令内自动姿态复位，09:00才交回控制。',
                        occurred=clock('08:25'),event='reference_completed',cycle='Q71',block='K3',id=identifier,operation=op,theta_degrees=19)
            history.add(26,f'归档{story_timestamp(clock("08:25"))}已完成的同一Q71/K3预约{identifier}的BC回执，几何角19度，非重复成像；仍自动复位。',
                        occurred=clock('08:25'),event='reference_completed',cycle='Q71',block='K3',id=identifier,operation=op,theta_degrees=19)
    history.add(6,'已收到预约安排；接受不等于采集完成。',event='arrangement_accepted',cycle='Q71')
    for target,is_finished in finished.items():
        history.add(23,f'{story_timestamp(clock("08:22"))}，Q71目标{target}K3'+('科学块实际采集完成。' if is_finished else '仍在积分，科学块未完成。'),
                    occurred=clock('08:22'),event='science_block_status',cycle='Q71',block='K3',target=target,completed=is_finished)
    if not done:
        history.add(23,'08:22原始几何遥测角0度。',occurred=clock('08:22'),event='geometry_telemetry',theta_degrees=0)
    if done:
        history.add(27,'动作内置自动姿态复位仍在进行，09:00返回控制，不是新科学曝光组。',event='reset_telemetry')
        history.add(30,'08:30自动复位中，原始几何角19.5度。',
                    occurred=clock('08:30'),event='geometry_telemetry',theta_degrees=19.5)
    else:
        history.add(27,'启动完整跟踪曝光组，09:00才完成当前子积分并归还控制，期间不另选操作。',
                    occurred=clock('08:27'),event='tracking_started')
        history.add(30,f'08:30跟踪组尚未结束，原始几何角{theta-2}度。',
                    occurred=clock('08:30'),event='geometry_telemetry',theta_degrees=theta-2)
    event = 'reset_completed' if done else 'tracking_completed'
    group = f'FM-T2-D2-{theta}-{bits}-{normal}-{event}'
    task = task_shell('FM-T2-D2',index,current_input_group=group)
    entries = [{'operation':_operation(code),'description':_description(code)}
               for code in ('BA','BB','BC','BD','RA','RB','RC','RD','SA','SB','SC','SD','Z')]
    task.public = {'time_s':clock('09:00'),'cycle':'Q71','block':'K3','theta_degrees':theta,'block_completed':finished,'ordinary_next':normal[1],
                   'current_event':event,'max_steps':3,'state_fields':[],'instruction':f'第120日09:00，Q71，导航角{theta}度，'
                   f'A/B/C/D的K3完成位{bits}，普通下一目标{normal[1]}；'+('自动姿态复位刚完成' if done else '跟踪组刚完成')
                   +'，设备正常，请执行下一步操作。','actions':ordered_options(entries,group)}
    products = {b:{t:{k:0 for k in ('background','standard')} for t in 'ABCD'} for b in ('K2','K3')}
    if index == 15:
        products['K2']['A']['standard'] = 1
    for row in intentions:
        if row['id'] in completed:
            products['K3'][row['operation']['target']][row['operation']['kind']] += 1
    task.initial = {'time_s':clock('09:00'),'decision_theta_degrees':theta,'block_completed':finished,'products':products,
                    'science_subexposures':{b:{t:0 for t in 'ABCD'} for b in ('K3','K4')},'exposures':[]}
    task.world = {'intentions':intentions,'completed':completed,'cancelled':cancelled,'correct_operation':_operation(correct)}
    task.rubric = {'score':'100 for highest-priority pending K3 reference with completed science and current geometry, otherwise normal science'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        kind = operation['kind']
        if kind != 'wait':
            target = operation['target']
            duration = 2 if kind == 'background' else 1
            block = ('K4' if self.state['block_completed'][target] else 'K3') if kind == 'science' else 'K3'
            exposure = {'target':target,'block':block,'kind':kind,'started_s':self.state['time_s'],
                        'finished_s':self.state['time_s']+duration,'theta_start_degrees':self.state['decision_theta_degrees']}
            if kind == 'science':
                self.state['science_subexposures'][block][target] += 1
                exposure['theta_end_degrees'] = (self.state['decision_theta_degrees']*10+1)/10
            else:
                self.state['products']['K3'][target][kind] += 1
                if kind == 'background':
                    exposure['offset_degrees'] = 3
            self.state['exposures'].append(exposure)
            self.state['time_s'] += duration
        self.feedback = '操作已执行，记录已存档。'
        return 100 if operation == self.task.world['correct_operation'] else 0


def reconstruct(history,current):
    intentions,completed,cancelled = {},set(),set()
    science = {}
    cycle,block = re.escape(current['cycle']),re.escape(current['block'])
    scope = f'{cycle}/{block}'
    for text in paragraphs(history):
        registered = re.fullmatch(rf'{scope}预约(I\d+)：目标([ABCD])块实际完成后，在几何角\[(\d+),(\d+)\)度主动采集(离轴背景|标准参考)，等级(\d+)，一次。',text)
        if registered:
            identifier,target,lower,upper,kind,priority = registered.groups()
            intentions[identifier] = {'id':identifier,'cycle':current['cycle'],'block':current['block'],
                'operation':{'kind':'background' if kind == '离轴背景' else 'standard','target':target},
                'lower_degrees':int(lower),'upper_degrees':int(upper),'priority':int(priority)}
        fulfilled = re.fullmatch(rf'{STORY_STAMP}，{scope}预约(I\d+)的[BR][ABCD]实际完成，几何角\d+(?:\.\d+)?度，进入命令内自动姿态复位，09:00才交回控制。',text)
        archived = re.fullmatch(rf'归档{STORY_STAMP}已完成的同一{scope}预约(I\d+)的[BR][ABCD]回执，几何角\d+(?:\.\d+)?度，非重复成像；仍自动复位。',text)
        cancelled_row = re.fullmatch(rf'正式取消{scope}预约(I\d+)，未拍摄。',text)
        status = re.fullmatch(rf'{STORY_STAMP}，{cycle}目标([ABCD]){block}(科学块实际采集完成|仍在积分，科学块未完成)。',text)
        if fulfilled or archived:
            completed.add((fulfilled or archived)[1])
        if cancelled_row:
            cancelled.add(cancelled_row[1])
        if status:
            science[status[1]] = status[2] == '科学块实际采集完成'
    if science != current['block_completed']:
        raise ValueError('Current raw completion flags differ from actual science block history')
    ordered = sorted(intentions.values(),key=lambda r:r['id'])
    due = [r for r in ordered if r['id'] not in completed|cancelled and current['block_completed'][r['operation']['target']]
           and r['lower_degrees'] <= current['theta_degrees'] < r['upper_degrees']]
    first = min(due,key=lambda r:r['priority']) if due else None
    op = first['operation'] if first else {'kind':'science','target':current['ordinary_next']}
    return {'intentions':ordered,'completed':sorted(completed),'cancelled':sorted(cancelled),'correct_operation':op}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('intentions','completed','cancelled','correct_operation')):
        raise ValueError('Science reference duty differs from block, geometry and actual fulfillment')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op == facts['correct_operation'] else 0)
