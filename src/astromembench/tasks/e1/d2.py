"""FM-E1-D2: match complete conditions, then intersect measured and requested bands."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Baseline, its abc/adef/bcdef programs, original H/S/T, and the other two programs for each condition.
FAMILIES = (
    ('LDQC',(9,3,7),(5,2,11),(1,4,6,8,10,12)),
    ('MBNW',(2,7,10),(1,6,4),(3,5,8,9,11,12)),
    ('MDQW',(7,2,12),(9,5,3),(1,4,6,8,10,11)),
    ('LDNW',(6,11,3),(2,8,5),(1,4,7,9,10,12)),
    ('LBQW',(3,8,1),(11,7,5),(2,4,6,9,10,12)),
    ('MBNW',(1,6,11),(9,2,8),(3,4,5,7,10,12)),
    ('LBNC',(8,2,7),(10,6,4),(1,3,5,9,11,12)),
    ('MDQW',(4,12,6),(2,11,9),(1,3,5,7,8,10)),
)
# Family, goal bands, archive layout, frequent/latest reference, actual current condition, full program.
CONFIGS = (
    (1,'abc',1,1,1,'LDQC',9),(1,'ade',2,1,4,'MDQC',1),
    (2,'bcf',3,3,3,'MDNW',9),(2,'abc',4,4,3,'MBQW',11),
    (3,'ade',3,2,4,'MDQW',2),(3,'bcf',4,4,3,'LDQW',4),
    (4,'abc',4,1,2,'LDQW',10),(4,'ade',1,2,1,'LBNW',8),
    (5,'ade',4,3,2,'LBQW',8),(5,'bcf',1,3,1,'MBQW',4),
    (6,'ade',2,2,4,'MBQW',12),(6,'bcf',3,4,3,'MDNW',7),
    (7,'abc',3,3,1,'LBNC',8),(7,'ade',4,2,3,'LBQC',12),
    (8,'bcf',1,6,3,'MBQW',7),(8,'abc',2,1,6,'LDQW',2),
)
LAYOUTS = ((7,2,11,4,1,9,6,12,3,8,5,10),(3,10,5,12,8,1,11,6,2,9,4,7),
           (12,6,2,9,4,11,1,7,10,5,3,8),(5,9,1,7,10,3,8,2,12,4,6,11))
JOBS = ('J17','J04','J29','J11','J06','J23','J32','J07','J26','J14','J09','J21')
FIELDS = ('payload','source_brightness','background','temperature_zone')
BANDS = ('abc','adef','bcdef')


def _condition(code):
    return dict(zip(FIELDS,(code[0],{'D':'暗源','B':'亮源'}[code[1]],{'Q':'低背景','N':'高背景'}[code[2]],
                            {'C':'冷区','W':'暖区'}[code[3]]),strict=True))


def _key(condition):
    return tuple(condition[k] for k in FIELDS)


def build(index):
    family,goal,layout,frequent,recent,current_code,correct = CONFIGS[index]
    baseline,main,original,extra = FAMILIES[family-1]
    near = [baseline[:i]+next(v for v in choices if v != baseline[i])+baseline[i+1:] for i,choices in enumerate(('LM','DB','QN'))]
    references = [(baseline,p,bands) for p,bands in zip(main,BANDS,strict=True)] + [(c,p,bands) for c,p,bands in zip(near,original,BANDS,strict=True)]
    rows = references+[(near[0],extra[0],'adef'),(near[0],extra[1],'bcdef'),(near[1],extra[2],'abc'),
                       (near[1],extra[3],'bcdef'),(near[2],extra[4],'abc'),(near[2],extra[5],'adef')]
    by_program = {p:(code,p,bands) for code,p,bands in rows}
    history = History()
    history.add(1,'科学观测在相同完整工况下可复现已实测验收的谱段，各段独立，未验证的段不能本次认定有效。'
                '不同工况的记录持续有效且互不覆盖。P1—P12均为完整预置观测过程，编号无优劣，能耗与用时相同。'
                '三个常见目标分别需要a/b/c、a/d/e、b/c/f，目标字母无优先级。只评价本次明确要求的三段，不按总产物数或解释长度打分。'
                '当前载荷、源亮度、背景与温区均由传感器直接测明，无隐含阈值；设备正常就绪。'
                '一次合法选择固定观测2分钟后结束，不能拼接其他方案。有效无效共3次，end放弃，原生记忆检索不算动作或故事时间。',
                event='spectral_experience_protocol')
    history.add(2,'六个独立谱段为a、b、c、d、e、f，结果列表逐段记录通过验收的产物，未列段没有通过。',event='spectral_band_catalog',bands=list('abcdef'))
    history.add(3,'当前科学任务已分配，目标谱段为'+','.join(goal)+'；正式执行时任务再次明确给出。',event='science_target_assigned',target_bands=list(goal))

    def trial(at,job,code,preset,bands,start,style):
        condition,finish = _condition(code),start+120
        first = {'job':job,'condition':condition,'started_s':start}
        result = {'job':job,'program':f'P{preset}','verified_bands':list(bands),'finished_s':finish}
        description = '、'.join(condition.values())
        if style == 'combined':
            history.add(at,f'{job}：{description}，{story_timestamp(start)}开始用P{preset}观测，{story_timestamp(finish)}完成；'
                        f'实际验收谱段{",".join(bands)}，其余未通过。',occurred=finish,event='spectral_trial',
                        **first,program=f'P{preset}',verified_bands=list(bands),finished_s=finish)
        else:
            history.add(at-1 if style == 'previous_round' else at,f'{job}：登记同一已完成观测的完整工况{description}，原开始时刻{story_timestamp(start)}。',
                        record_id=job+'-条件',occurred=start,event='spectral_condition',**first)
            history.add(at,f'{job}：P{preset}在{story_timestamp(finish)}观测完成，实际验收{",".join(bands)}，其他谱段未通过。',
                        record_id=job+'-结果',occurred=finish,event='spectral_result',**result)

    style = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'
    for at,job,preset in zip(range(4,27,2),JOBS,LAYOUTS[layout-1],strict=True):
        trial(at,job,*by_program[preset],clock('09:00',119)+(preset-1)*180,style)
    for position,(at,reference,job) in enumerate(zip((27,27,27,29),(frequent,frequent,frequent,recent),('J41','J36','J43','J38'),strict=True)):
        trial(at,job,*references[reference-1],clock('10:00',119)+position*300,'combined')
    history.add(30,'当前目标区S18已到位，载荷就绪，等待一次完整科学观测。',event='science_ready',location='S18')
    current = _condition(current_code)
    standards = sorted(({'condition':_condition(c),'program':f'P{p}','verified_bands':list(b)} for c,p,b in rows),key=lambda r:(_key(r['condition']),int(r['program'][1:])))
    verified = {f'P{p}':[] for p in range(1,13)}
    verified.update({r['program']:r['verified_bands'] for r in standards if r['condition'] == current})
    task = task_shell('FM-E1-D2',index)
    task.public = {'time_s':clock('09:00'),'location':'S18','condition':current,'target_bands':list(goal),'equipment_ready':True,
                   'max_steps':3,'state_fields':[],'instruction':'第120日09:00，地点S18，当前'+ '、'.join(current.values())+
                   '；设备就绪，目标谱段为'+','.join(goal)+'。请完成一次观测。',
                   'actions':fixed_options([{'operation':{'program':f'P{p}'},'description':f'用P{p}执行一次完整观测。'} for p in range(1,13)])}
    task.initial = {'time_s':clock('09:00'),'observations':[]}
    task.world = {'standards':standards,'verified_bands':verified,'correct_operation':{'program':f'P{correct}'}}
    task.rubric = {'score':'100 times the intersection of verified current-condition bands and the three requested bands divided by 3'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        start = self.state['time_s']
        self.state['time_s'] += 120
        verified = self.task.world['verified_bands'][operation['program']]
        accepted = sorted(set(verified) & set(self.task.public['target_bands']))
        self.state['observations'].append({'program':operation['program'],'condition':self.task.public['condition'],
                                           'started_s':start,'finished_s':self.state['time_s'],'observation_performed':True,
                                           'verified_bands':verified,'accepted_target_bands':accepted})
        self.feedback = '操作已执行，记录已存档。'
        return 100*len(accepted)/3


def _read_condition(text):
    match = re.fullmatch(r'([LM])、(暗源|亮源)、(低背景|高背景)、(冷区|暖区)',text)
    if not match:
        raise ValueError('Missing complete spectral condition in prose')
    return dict(zip(FIELDS,match.groups(),strict=True))


def reconstruct(history,current):
    conditions,results = {},{}
    for text in paragraphs(history):
        combined = re.fullmatch(rf'(J\d+)：(.+)，{STORY_STAMP}开始用(P\d+)观测，{STORY_STAMP}完成；实际验收谱段([a-f,]+)，其余未通过。',text)
        condition = re.fullmatch(rf'(J\d+)：登记同一已完成观测的完整工况(.+)，原开始时刻{STORY_STAMP}。',text)
        result = re.fullmatch(rf'(J\d+)：(P\d+)在{STORY_STAMP}观测完成，实际验收([a-f,]+)，其他谱段未通过。',text)
        if combined:
            conditions[combined[1]] = _read_condition(combined[2])
            results[combined[1]] = {'program':combined[3],'verified_bands':combined[4].split(',')}
        elif condition:
            conditions[condition[1]] = _read_condition(condition[2])
        elif result:
            results[result[1]] = {'program':result[2],'verified_bands':result[3].split(',')}
    if conditions.keys() != results.keys():
        raise ValueError('Spectral jobs must join complete conditions with actual verified bands')
    known = {}
    for job,result in results.items():
        row = {'condition':conditions[job],**result}
        key = (_key(row['condition']),int(row['program'][1:]))
        if key in known and known[key] != row:
            raise ValueError('Repeated complete-condition observation changed its stable band result')
        known[key] = row
    standards = [known[k] for k in sorted(known)]
    verified = {f'P{p}':[] for p in range(1,13)}
    verified.update({r['program']:r['verified_bands'] for r in standards if r['condition'] == current['condition']})
    full = [p for p,bands in verified.items() if set(current['target_bands']) <= set(bands)]
    if len(full) != 1:
        raise ValueError('The current scientific target needs one fully verified observation preset')
    return {'standards':standards,'verified_bands':verified,'correct_operation':{'program':full[0]}}


def next_action(facts,current):
    return decision_command(current,facts['correct_operation'])


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Scientific results differ from the full public condition and requested target')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*len(set(facts['verified_bands'][op['program']]) & set(task.public['target_bands']))/3)
