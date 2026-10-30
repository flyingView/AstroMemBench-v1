"""FM-E1-O1: recover actual detail counts for the complete imaging condition."""
import re

from ..common import ArchiveHistory, History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

FIELDS = ('head','surface','lighting','distance')
# Current condition, fixed menu, and all actual measurements (round, condition, preset, details).
SOURCES = {
    0:('XMCJ',(11,9,3,1,10,8,7,12,2,4,5,6),(
        (2,'XMCJ',4,5),(2,'YMCJ',6,5),(6,'XMZJ',2,5),(9,'XMCY',11,5),(12,'YRCJ',9,5),
        (13,'XRCJ',7,5),(19,'XRZJ',3,5),(24,'XRCJ',7,5),(28,'XMZJ',2,5))),
    1:('XMCJ',(6,5,2,8,12,3,10,11,9,1,4,7),(
        (2,'XRCJ',4,5),(7,'YMCJ',10,5),(10,'XMZJ',1,5),(14,'XRCJ',4,5),(14,'XMCY',8,5),
        (18,'XMCJ',7,5),(21,'XRZY',12,5),(25,'XRCJ',4,5),(29,'YMZJ',5,5))),
    6:('YRCJ',(9,4,6,5,10,3,11,7,8,2,12,1),(
        (2,'XRCJ',8,5),(4,'YRCJ',1,2),(7,'YMZJ',4,5),(11,'YRZY',11,5),(12,'YMCJ',10,5),
        (16,'XMCY',6,5),(20,'YRZJ',7,5),(23,'XRZJ',2,5),(26,'YRCJ',5,5),(27,'YRCY',3,5),(29,'YRCY',3,5))),
    12:('XRCY',(11,5,10,3,6,1,8,4,2,12,9,7),(
        (2,'YRZY',9,5),(3,'XRCJ',8,5),(5,'XMCJ',6,5),(7,'XRCY',4,3),(10,'YMZY',3,5),
        (12,'XRZY',1,5),(16,'XMCY',7,5),(18,'XRZJ',10,5),(20,'XRCY',11,5),(21,'YRCY',5,5),
        (24,'YRCJ',12,5),(27,'XMZJ',2,5),(29,'XRCJ',8,5))),
}
# Baseline, archive layout, full/backup/detail count, H/S/L/D full and partial presets, F/L, actual query.
EXTENSIONS = {
    2:('YMCY','B',9,1,2,(3,7,5,12),(2,4,6,8),2,0,'YRCY'),
    3:('YMCY','B',1,9,2,(3,7,5,12),(2,4,6,8),0,2,'YMZY'),
    4:('XMZJ','C',3,8,4,(10,2,6,11),(1,4,5,7),0,0,'XMZY'),
    5:('YRZY','A',5,12,3,(7,4,10,2),(1,3,6,8),0,4,'YRZY'),
    7:('YMCJ','C',7,11,3,(2,8,4,10),(1,3,5,6),1,0,'YRCJ'),
    8:('YMCJ','C',11,7,3,(2,8,4,10),(1,3,5,6),0,1,'YMCJ'),
    9:('XRCY','A',4,9,4,(12,3,8,1),(2,5,6,7),0,5,'YRCY'),
    10:('XRCY','A',9,4,4,(12,3,8,1),(2,5,6,7),5,0,'XRZY'),
    11:('YMZY','B',6,2,2,(5,11,1,9),(3,4,7,8),0,2,'YMZJ'),
    13:('YMZJ','B',5,10,4,(8,1,12,4),(2,3,6,7),5,0,'YMZY'),
    14:('YMZJ','B',10,5,4,(8,1,12,4),(2,3,6,7),0,5,'YMZJ'),
    15:('XMCJ','C',7,2,3,(11,5,9,6),(1,3,4,8),0,4,'YMCJ'),
}
LAYOUTS = {'A':(7,2,11,4,1,9,6,12,3,8,5,10),'B':(3,10,5,12,8,1,11,6,2,9,4,7),
           'C':(12,6,2,9,4,11,1,7,10,5,3,8)}
JOBS = ('J17','J04','J29','J11','J06','J23','J08','J15','J31','J02','J19','J10')
CORRECT = (4,7,7,5,11,5,5,8,11,12,8,9,11,4,10,11)


def _condition(code):
    return dict(zip(FIELDS,(code[0],{'M':'镜面','R':'粗糙面'}[code[1]],{'C':'侧光','Z':'正光'}[code[2]],
                            {'J':'近距','Y':'远距'}[code[3]]),strict=True))


def _key(condition):
    return tuple(condition[k] for k in FIELDS)


def _nearby(code):
    return [code[:i]+next(x for x in choices if x != code[i])+code[i+1:] for i,choices in enumerate(('XY','MR','CZ','JY'))]


def _standards(measurements):
    known = {}
    for code,preset,count in measurements:
        key = (_key(_condition(code)),preset)
        if key in known and known[key]['verified_details'] != count:
            raise ValueError('Stable inspection condition has contradictory actual counts')
        known[key] = {'condition':_condition(code),'program':f'P{preset}','verified_details':count}
    return [known[k] for k in sorted(known)]


def build(index):
    source = index in SOURCES
    now = clock('10:00')
    history = ArchiveHistory(now,spacing_s=120) if source else History(times=[now-(31-r)*120+59 for r in range(1,31)])
    history.add(1,'检查头X/Y有P1—P12十二套独立成像预置，编号没有优劣含义。经验绑定检查头、表面、光向、距离四项完整条件。'
                '同一完整条件与同一预置的实测有效细节数稳定，各条件经验一直有效，不因其他新记录而撤销。'
                '本次须验收5项细节，只认可此条件下实际验证过的项目，未经验证的方案不能验收。当前条件由系统直接测得，无需识图。'
                '十二预置都可真实执行；有效无效提交共3次，首个合法选择立即执行并结束，不能试选后改答；end放弃。'
                '推理与记忆检索不推进故事时间。'+('' if source else '每次检查用时1分钟，历史登记保留原试验起止时间。'),
                event='inspection_experience_protocol')
    measurements = []

    def trial(at,job,code,preset,count,start,split):
        condition,finish = _condition(code),start+60
        description = '、'.join(condition.values())
        first = {'job':job,'condition':condition,'started_s':start}
        result = {'job':job,'program':f'P{preset}','verified_details':count,'finished_s':finish}
        if split == 'combined':
            history.add(at,f'{job}：{story_timestamp(start)}在{description}开始检查，使用P{preset}；'
                        f'{story_timestamp(finish)}完成，5项需求中实际验收{count}项。',occurred=finish,
                        event='inspection_trial',**first,program=f'P{preset}',verified_details=count,finished_s=finish)
        else:
            history.add(at-1 if split == 'previous_round' else at,f'{job}：登记已完成检查的工况，{description}，'
                        f'原开始时刻{story_timestamp(start)}。',occurred=start,event='inspection_condition',**first)
            history.add(at,f'{job}：P{preset}于{story_timestamp(finish)}完成检查，5项中实际验收{count}项。',
                        occurred=finish,event='inspection_result',**result)
        measurements.append((code,preset,count))

    if source:
        current_code,menu,rows = SOURCES[index]
        for at,code,preset,count in rows:
            history.add(at,'、'.join(_condition(code).values())+f'，用P{preset}实际检查完成，5项中验收{count}项。',
                        event='inspection_completed',condition=_condition(code),program=f'P{preset}',verified_details=count)
            measurements.append((code,preset,count))
    else:
        baseline,layout,p,q,m,full,partial,frequent,recent,current_code = EXTENSIONS[index]
        nearby = _nearby(baseline)
        references = [(baseline,p,5),*[(c,v,5) for c,v in zip(nearby,full,strict=True)],(baseline,q,m)]
        rows = references+[(c,w,n) for c,w,n in zip(nearby,partial,(2,3,4,2),strict=True)]
        by_program = {row[1]:row for row in rows}
        archive = [preset for preset in LAYOUTS[layout] if preset in by_program]
        start_times = {preset:clock('09:00',119)+order*120 for order,preset in enumerate(sorted(by_program))}
        split = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'
        for at,preset in zip((3,5,7,9,11,13,15,17,19,23),archive,strict=True):
            trial(at,JOBS[preset-1],*by_program[preset],start_times[preset],split)
        for position,(at,reference,job) in enumerate(zip((24,26,28,29),(frequent,frequent,frequent,recent),
                                                       ('J41','J36','J43','J38'),strict=True)):
            trial(at,job,*references[reference],clock('09:30',119)+position*240,'combined')
        history.add(30,'新检查目标已到位，四项工况已测明，设备就绪。',event='inspection_ready')
        menu = range(1,13)
    current = _condition(current_code)
    standards = _standards(measurements)
    counts = {f'P{p}':0 for p in range(1,13)}
    counts.update({r['program']:r['verified_details'] for r in standards if r['condition'] == current})
    task = task_shell('FM-E1-O1',index)
    task.public = {'time_s':now,'condition':current,'required_details':5,'equipment_ready':True,'max_steps':3,'state_fields':[],
                   'instruction':'第120日10:00，当前'+ '、'.join(current.values())+'，设备就绪。按当前已测条件完成一次检查，需验收5项细节。',
                   'actions':fixed_options([{'operation':{'program':f'P{p}'},'description':f'用P{p}执行本次检查。'} for p in menu])}
    if not source:
        task.public['inspection_seconds'] = 60
    task.initial = {'time_s':now,'inspections':[]}
    task.world = {'standards':standards,'detail_counts':counts,'correct_operation':{'program':f'P{CORRECT[index]}'}}
    task.rubric = {'score':'20 times actual verified details for the complete current condition; unverified programs earn zero'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        start = self.state['time_s']
        self.state['time_s'] += self.task.public.get('inspection_seconds',0)
        count = self.task.world['detail_counts'][operation['program']]
        self.state['inspections'].append({'condition':self.task.public['condition'],'program':operation['program'],
                                          'verified_details':count,'started_s':start,'finished_s':self.state['time_s']})
        self.feedback = '操作已执行，记录已存档。'
        return count*20


def _read_condition(text):
    match = re.fullmatch(r'([XY])、(镜面|粗糙面)、(侧光|正光)、(近距|远距)',text)
    if not match:
        raise ValueError('Missing complete imaging condition in prose')
    return dict(zip(FIELDS,match.groups(),strict=True))


def reconstruct(history,current):
    conditions,results,measurements = {},{},[]
    for text in paragraphs(history):
        measured = re.fullmatch(r'(.+)，用(P\d+)实际检查完成，5项中验收(\d+)项。',text)
        combined = re.fullmatch(rf'(J\d+)：({STORY_STAMP})在(.+)开始检查，使用(P\d+)；({STORY_STAMP})完成，5项需求中实际验收(\d+)项。',text)
        condition = re.fullmatch(rf'(J\d+)：登记已完成检查的工况，(.+)，原开始时刻({STORY_STAMP})。',text)
        result = re.fullmatch(rf'(J\d+)：(P\d+)于({STORY_STAMP})完成检查，5项中实际验收(\d+)项。',text)
        if measured:
            measurements.append({'condition':_read_condition(measured[1]),'program':measured[2],'verified_details':int(measured[3])})
        elif combined:
            conditions[combined[1]] = {'condition':_read_condition(combined[3]),'started_s':seconds(combined[2])}
            results[combined[1]] = {'program':combined[4],'finished_s':seconds(combined[5]),'verified_details':int(combined[6])}
        elif condition:
            conditions[condition[1]] = {'condition':_read_condition(condition[2]),'started_s':seconds(condition[3])}
        elif result:
            results[result[1]] = {'program':result[2],'finished_s':seconds(result[3]),'verified_details':int(result[4])}
    if conditions.keys() != results.keys():
        raise ValueError('Inspection jobs must join complete conditions with actual preset/results')
    for job,condition in conditions.items():
        if condition['started_s'] > results[job]['finished_s']:
            raise ValueError('Historical inspection result precedes its trial')
        measurements.append({**condition,**results[job]})
    known = {}
    for r in measurements:
        key = (_key(r['condition']),int(r['program'][1:]))
        value = {k:r[k] for k in ('condition','program','verified_details')}
        if key in known and known[key] != value:
            raise ValueError('Same complete condition and preset must retain its actual detail count')
        known[key] = value
    standards = [known[k] for k in sorted(known)]
    counts = {f'P{p}':0 for p in range(1,13)}
    counts.update({r['program']:r['verified_details'] for r in standards if r['condition'] == current['condition']})
    full = [program for program,count in counts.items() if count == 5]
    if len(full) != 1:
        raise ValueError('Inspection design requires a verified five-detail option')
    return {'standards':standards,'detail_counts':counts,'correct_operation':{'program':full[0]}}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Inspection counts differ from actual public four-condition measurements')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:20*facts['detail_counts'][op['program']])
