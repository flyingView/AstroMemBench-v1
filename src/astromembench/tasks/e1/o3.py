"""FM-E1-O3: use measured dose tables and conserve both premixed components."""
from math import gcd
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Each book gives two measured nonzero programs per receiver/ratio, plus archive order.
BOOKS = (
    (((3,8),(8,4)),((11,6),(5,8)),((1,8),(9,2)),((7,4),(2,8)),((10,8),(6,6)),((4,2),(12,8))),
    (((9,6),(2,8)),((6,8),(12,4)),((4,2),(10,8)),((1,8),(8,6)),((11,4),(5,8)),((7,8),(3,2))),
    (((12,8),(5,2)),((2,4),(9,8)),((8,8),(1,6)),((6,2),(11,8)),((3,8),(7,4)),((10,6),(4,8))),
    (((7,4),(11,8)),((3,8),(10,6)),((12,2),(6,8)),((5,8),(9,4)),((1,6),(4,8)),((8,8),(2,2))),
    (((4,8),(10,6)),((8,2),(1,8)),((11,8),(3,4)),((2,6),(7,8)),((12,2),(9,8)),((5,8),(6,4))),
    (((1,2),(6,8)),((10,8),(4,4)),((7,6),(12,8)),((9,8),(3,2)),((5,4),(2,8)),((11,8),(8,6))),
    (((8,8),(12,4)),((5,6),(7,8)),((2,8),(9,2)),((10,4),(6,8)),((4,8),(11,6)),((1,2),(3,8))),
    (((6,6),(3,8)),((12,8),(8,2)),((9,4),(5,8)),((4,8),(11,6)),((7,2),(1,8)),((2,8),(10,4))),
)
ARCHIVES = ((3,6,1,5,2,4),(5,2,4,1,6,3),(2,4,6,3,1,5),(6,1,5,2,4,3),
            (4,3,1,6,5,2),(1,5,3,4,2,6),(5,1,6,3,4,2),(2,6,4,5,3,1))
CONDITIONS = (('R',1,3),('R',1,1),('R',3,1),('F',1,3),('F',1,1),('F',3,1))
RECEIVERS = {'R':'刚性储液腔','F':'柔顺储液囊'}
DOSES = (2,4,6,8)
# Book, current receiver, X/Y mL, repeated/latest program, actual two nonzero deliveries in L.
CONFIGS = (
    (1,'R',2000,6000,3,3,((3,8),(8,4))),
    (1,'R',1000,3000,11,8,((3,4),(8,4))),
    (1,'F',1500,4500,7,10,((7,4),(2,6))),
    (2,'R',6000,2000,10,10,((4,2),(10,8))),
    (3,'F',500,1500,6,11,((6,2),(11,2))),
    (3,'R',3000,1000,9,1,((8,4),(1,4))),
    (4,'R',4000,4000,3,10,((3,8),(10,6))),
    (4,'F',3000,3000,1,4,((1,6),(4,6))),
    (5,'R',1000,1000,8,1,((8,2),(1,2))),
    (5,'F',1500,4500,9,2,((2,6),(7,6))),
    (5,'F',6000,2000,6,10,((5,8),(6,4))),
    (6,'R',6000,2000,7,12,((7,6),(12,8))),
    (7,'R',4000,4000,5,7,((5,6),(7,8))),
    (7,'R',1500,500,2,9,((2,2),(9,2))),
    (8,'R',1500,4500,6,3,((6,6),(3,6))),
    (8,'F',2000,6000,11,8,((4,8),(11,6))),
)


def _program(number):
    return f'U{number:02d}'


def _mixture(x,y,q):
    return {'x_l':q*x/(x+y),'y_l':q*y/(x+y),'q_l':q}


def _ratio(mixture):
    # Every authored amount is an exact multiple of 0.5 L; integer mL avoid float ratio tests.
    x,y = round(mixture['x_l']*1000),round(mixture['y_l']*1000)
    divisor = gcd(x,y)
    return [x//divisor,y//divisor]


def _table(receiver,x,y,results):
    return {'receiver_type':receiver,'ratio':_ratio(_mixture(x,y,2)),'results':results}


def build(index):
    book,receiver,x_ml,y_ml,frequent,recent,nonzero = CONFIGS[index]
    curves = BOOKS[book-1]
    history = History()
    history.add(1,'X/Y为题内惰性工艺液，固定密度和温度，预混均匀后输送，体积可相加；X:Y按约分后的体积比例匹配。'
                '接收器R为刚性储液腔、F为柔顺储液囊。每次初始为空、容量12L，供给侧恰有当前X+Y共QL。'
                '设备相同且健康，连接、支撑、隔离均完成，无未给定的其他环境变量。经验始终有效，没有更新或撤销。'
                '本模型只使用1:3、1:1、3:1三比例和2/4/6/8L四剂量；每种接收结构、比例、剂量和全部十二程序都已分别实测，结果稳定。'
                '只认可离散已测域，不从单次8L推断其他剂量。历史各次都使用独立空接收器和重置后的供液。'
                'U01—U12实际尝试输送，质量闭环可提前截停，所有到达液体都通过均匀性验收，未送液体仍在供给侧，不流入废液池。'
                '历史每项45秒，余15秒换接收器并重置。当前宏共1分钟，前45秒流体动作，余15秒保持闭阀不再增量，不能切换或续注。'
                '有效无效共3次，首次合法动作不可撤回并结束，end放弃；推理与记忆检索不推进故事时间。',event='mixture_experience_protocol')
    history.add(2,'登记源液批次LX/LY，接收器额定容积12L，各次实测后重置供液与空接收器。',event='fluid_inventory',
                source_batches={'X':'LX','Y':'LY'},receiver_capacity_l=12)
    tables = []
    layout = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'
    for position,(at,condition_index,job) in enumerate(zip((4,7,10,13,16,19),ARCHIVES[book-1],('J17','J04','J29','J11','J06','J23'),strict=True)):
        kind,x,y = CONDITIONS[condition_index-1]
        limits = dict(curves[condition_index-1])
        mixtures = [_mixture(x,y,q) for q in DOSES]
        results = [{'program':_program(p),'delivered_l':[min(q,limits.get(p,0)) for q in DOSES]} for p in range(1,13)]
        tables.append(_table(kind,x,y,results))
        first = clock('06:00',119)+(condition_index-1)*48*60
        finish = first+47*60+45
        conditions = {'job':job,'receiver_type':kind,'receiver_name':RECEIVERS[kind],'mixtures':mixtures,'batch_started_s':first}
        receipt = {'job':job,'doses_l':list(DOSES),'results':results,'batch_started_s':first,'batch_finished_s':finish,
                   'trial_interval_s':60,'trial_seconds':45,'order':'按剂量2/4/6/8L，每剂量按U01—U12顺序各做一次'}
        description = f'{RECEIVERS[kind]}，四次配液（X/Y L）依次'+ '、'.join(f'{m["x_l"]}/{m["y_l"]}' for m in mixtures)
        measured = '；'.join(f'{row["program"]}：'+ '、'.join(str(v) for v in row['delivered_l']) for row in results)
        report_text = f'{job}全部48项实际验收量按供液2、4、6、8L顺序逐一登记，单位L，包含0量：{measured}。'
        report_text += f'{story_timestamp(first)}起每分钟一项，每项45秒，'
        report_text += f'先2再4再6再8L，每剂量依U01—U12；末项{story_timestamp(finish)}完成。'
        if layout == 'combined':
            history.add(at,description+'；'+report_text,occurred=finish,event='mixture_trial_batch',**conditions,
                        **{k:v for k,v in receipt.items() if k not in conditions})
        else:
            history.add(at-1 if layout == 'previous_round' else at,f'{job}原批次工况：{description}，实际起点{story_timestamp(first)}。',
                        occurred=first,event='mixture_batch_condition',**conditions)
            history.add(at,report_text,occurred=finish,event='mixture_batch_results',**receipt)
    for position,(at,preset,job) in enumerate(zip((22,24,26,29),(frequent,frequent,frequent,recent),('J41','J36','J43','J38'),strict=True)):
        selected = next((i,amount) for i,row in enumerate(curves) for program,amount in row if program == preset)
        condition_index,amount = selected
        kind,x,y = CONDITIONS[condition_index]
        start = clock('12:00',119)+position*120
        finish = start+45
        mixture = _mixture(x,y,8)
        history.add(at,f'{job}独立实测：{RECEIVERS[kind]}，X={mixture["x_l"]}L、Y={mixture["y_l"]}L，共8L，'
                    f'{_program(preset)}于{story_timestamp(start)}开始，{story_timestamp(finish)}完成，实际接收{amount}L合格混合液，'
                    f'供给侧余{8-amount}L。',occurred=finish,event='mixture_trial',job=job,receiver_type=kind,receiver_name=RECEIVERS[kind],
                    mixture=mixture,program=_program(preset),delivered_l=amount,source_remaining_l=8-amount,started_s=start,finished_s=finish)
    history.add(30,'当前空接收器已就绪，配液量已实测，等待一次完整补给程序。',event='mixture_receiver_ready')
    q_ml = x_ml+y_ml
    mixture = {'x_l':x_ml/1000,'y_l':y_ml/1000,'q_l':q_ml/1000}
    amounts = {_program(p):0 for p in range(1,13)}
    amounts.update({_program(p):v*1000 for p,v in nonzero})
    task = task_shell('FM-E1-O3',index)
    task.public = {'time_s':clock('09:00'),'receiver_type':receiver,'receiver_name':RECEIVERS[receiver],
                   'mixture':mixture,'receiver_empty':True,'receiver_capacity_l':12,'equipment_ready':True,'max_steps':3,'state_fields':[],
                   'instruction':f'第120日09:00，{RECEIVERS[receiver]}初始空置、容量12L，实测X={mixture["x_l"]}L、Y={mixture["y_l"]}L，'
                   f'预混均匀共Q={mixture["q_l"]}L，管路和设备就绪。完成本次Q L补给。',
                   'actions':fixed_options([{'operation':{'program':_program(p)},'description':f'用{_program(p)}输送当前{mixture["q_l"]}L预混液。'} for p in range(1,13)])}
    task.initial = {'time_s':clock('09:00'),'source_ml':{'X':x_ml,'Y':y_ml},'receiver_ml':{'X':0,'Y':0},'transfers':[]}
    task.world = {'tables':sorted(tables,key=lambda r:(r['receiver_type'],r['ratio'])), 'delivered_ml':amounts}
    task.rubric = {'score':'100 times the measured accepted delivery divided by requested Q; all completing programs earn full credit'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        program,start = operation['program'],self.state['time_s']
        delivered = self.task.world['delivered_ml'][program]
        supply = self.state['source_ml']
        q = sum(supply.values())
        moved = {liquid:volume*delivered//q for liquid,volume in supply.items()}
        for liquid,volume in moved.items():
            self.state['source_ml'][liquid] -= volume
            self.state['receiver_ml'][liquid] += volume
        self.state['time_s'] += 60
        self.state['transfers'].append({'program':program,'started_s':start,'flow_finished_s':start+45,'finished_s':start+60,
                                       'delivered_ml':delivered,'components_ml':moved,'valves_closed':True})
        self.feedback = '操作已执行，记录已存档。'
        return 100*delivered/q


def reconstruct(history,current):
    conditions,results,repeats = {},{},[]
    receiver_codes = {name:code for code,name in RECEIVERS.items()}
    for text in paragraphs(history):
        batch = re.search(r'(J\d+)(?:原批次工况：|全部48项实际验收量)',text)
        if batch:
            job = batch[1]
            condition = re.search(r'(刚性储液腔|柔顺储液囊)，四次配液（X/Y L）依次([\d./、]+)',text)
            if condition:
                mixtures = []
                for pair in condition[2].split('、'):
                    x,y = map(float,pair.split('/'))
                    mixtures.append({'x_l':x,'y_l':y,'q_l':x+y})
                conditions[job] = {'receiver_type':receiver_codes[condition[1]],'mixtures':mixtures}
            measured = re.search(r'全部48项实际验收量按供液([\d、]+)L顺序逐一登记，单位L，包含0量：(.+?)。',text)
            if measured:
                rows = []
                for entry in measured[2].split('；'):
                    program,values = entry.split('：')
                    rows.append({'program':program,'delivered_l':list(map(int,values.split('、')))})
                if [r['program'] for r in rows] != [_program(p) for p in range(1,13)]:
                    raise ValueError('Mixture prose must contain each measured program including zero outcomes')
                results[job] = {'doses_l':list(map(int,measured[1].split('、'))),'results':rows}
        repeat = re.fullmatch(rf'J\d+独立实测：(刚性储液腔|柔顺储液囊)，X=([\d.]+)L、Y=([\d.]+)L，共(\d+)L，'
                              rf'(U\d+)于{STORY_STAMP}开始，{STORY_STAMP}完成，实际接收(\d+)L合格混合液，供给侧余(\d+)L。',text)
        if repeat:
            repeats.append({'receiver_type':receiver_codes[repeat[1]],
                            'mixture':{'x_l':float(repeat[2]),'y_l':float(repeat[3]),'q_l':int(repeat[4])},
                            'program':repeat[5],'delivered_l':int(repeat[6])})
    if conditions.keys() != results.keys():
        raise ValueError('Every mixture batch must join its actual conditions and all dose results')
    tables,lookup = [],{}
    for job,condition in conditions.items():
        result = results[job]
        mixtures = condition['mixtures']
        ratio = _ratio(mixtures[0])
        if any(_ratio(m) != ratio or m['x_l']+m['y_l'] != m['q_l'] for m in mixtures):
            raise ValueError('Batch mixtures must express the same ratio at the explicitly measured doses')
        if [m['q_l'] for m in mixtures] != result['doses_l'] or result['doses_l'] != list(DOSES):
            raise ValueError('No interpolation: each of the four doses must have actual trial data')
        tables.append({'receiver_type':condition['receiver_type'],'ratio':ratio,'results':result['results']})
        for row in result['results']:
            for dose,amount in zip(result['doses_l'],row['delivered_l'],strict=True):
                if not 0 <= amount <= dose:
                    raise ValueError('Measured delivery must conserve its available premixed supply')
                lookup[(condition['receiver_type'],*ratio,dose,row['program'])] = amount
    for repeat in repeats:
        key = (repeat['receiver_type'],*_ratio(repeat['mixture']),repeat['mixture']['q_l'],repeat['program'])
        if lookup[key] != repeat['delivered_l']:
            raise ValueError('Repeated trial must agree with its already measured dose/condition')
    key = (current['receiver_type'],*_ratio(current['mixture']),current['mixture']['q_l'])
    amounts = {_program(p):round(lookup[(*key,_program(p))]*1000) for p in range(1,13)}
    return {'tables':sorted(tables,key=lambda r:(r['receiver_type'],r['ratio'])),'delivered_ml':amounts}


def next_action(facts,current):
    requested = round(current['mixture']['q_l']*1000)
    program = next(program for program,amount in facts['delivered_ml'].items() if amount == requested)
    return decision_command(current,{'program':program})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Mixture delivery must follow all actual discrete-dose public trials')


def audit_cases(task,facts,solution):
    requested = round(task.public['mixture']['q_l']*1000)
    return decision_cases(task,solution,lambda op:100*facts['delivered_ml'][op['program']]/requested)
