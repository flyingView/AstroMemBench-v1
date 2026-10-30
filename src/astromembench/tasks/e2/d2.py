"""FM-E2-D2: local background-field revisions and unnormalised reference subtraction."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

VECTORS = {'A':(1,2),'B':(2,1),'C':(2,3),'D':(3,2),'E':(3,4),'F':(4,3)}
LINES = ('T','R1','R2','R3','R4','R5')
# Initial target, old (reference,k), actual U/V, final target and final five references.
CONFIGS = (
    ('2B',(2,2),(('T','2D'),),(('R4','F'),('R1','D')),'2D','DBCFE'),
    ('C',(3,1),(('T','D'),),(('R1','D'),),'D','DBCDE'),
    ('2E',(5,2),(('T','2A'),),(('T','2E'),),'2E','ABCDE'),
    ('B',(2,1),(('R2','F'),),(('R4','B'),),'B','AFCBE'),
    ('D',(4,1),(('T','A'),),(('R1','F'),('R3','A')),'A','FBADE'),
    ('2D',(4,2),(('T','2C'),),(('R3','E'),('R2','C')),'2C','ACEDE'),
    ('C',(3,1),(('R3','F'),('R1','C')),(('R1','A'),('R5','C')),'C','ABFDC'),
    ('2C',(3,2),(('T','2A'),('R1','F')),(('T','2C'),('R3','C')),'2C','FBCDE'),
    ('2E',(5,2),(('T','2B'),('R2','D')),(('R5','B'),),'2B','ADCDB'),
    ('2A',(1,2),(('R1','C'),('T','2D')),(('R4','A'),('R2','D')),'2D','CDCAE'),
    ('2B',(2,2),(('T','2C'),('R3','A')),(('R1','C'),('R4','F')),'2C','CBAFE'),
    ('C',(3,1),(('T','A'),('R1','D')),(('R3','A'),('R2','F')),'A','DFADE'),
    ('A',(1,1),(('T','D'),('R1','F')),(('T','A'),('R3','A')),'A','FBADE'),
    ('D',(4,1),(('T','E'),('R5','A'),('R2','E')),(('R4','E'),('R2','F')),'E','AFCEA'),
    ('E',(5,1),(('R5','F'),('T','B'),('R2','A')),(('R1','B'),('R4','B')),'B','BACBF'),
    ('2B',(2,2),(('T','2A'),('R1','E'),('R2','C')),(('R3','A'),('R5','A')),'2A','ECADA'),
)
MODEL = {'science_exposure_s':1,'reference_exposure_s':[1,2],'program_duration_s':4,
         'science_raw_counts':'unknown true signal + target background per second',
         'estimated_signal':'science_raw_counts - reference_exposure_s * reference_background_per_second',
         'normalize_reference':False,'independent_bands':[1,2],'acceptance':'exact recovery of each true signal component'}


def vector(code):
    multiplier = 2 if code.startswith('2') else 1
    return tuple(multiplier*v for v in VECTORS[code[-1]])


def build(index):
    initial_target,old,updates,final_updates,final_target,final_references = CONFIGS[index]
    initial = {'T':vector(initial_target),**{f'R{i}':vector(c) for i,c in enumerate('ABCDE',1)}}
    history,background = History(),{}

    def add(at,text,**facts):
        history.add(at,text,record_id=f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}',**facts)

    add(1,'K片天空的目标视线T含两个独立科学谱段，R1—R5是无科学信号的参考空场；J片天空全部视线独立。'
        '设备响应、指向和几何正常。外部监测器对各视线各谱段的背景计数/秒精确实测，局部变化只更新列明视线与谱段，无未记录漂移。'
        '科学曝光固定1秒，原始计数为未知真实信号s加T背景b；Nj-k以Rj参考曝光k秒，直接减其总计数k*r，不除k。'
        '须分别完整还原两个谱段的真实信号；每谱段b=k*r时恰好还原，无噪声无容差，不跨次拼接。'
        '十程序N1-1/N1-2至N5-1/N5-2加保持始终可选，首合法选择耗用唯一科学曝光机会且终局，不能额外测背景或比较后重选。'
        '有效/无效/end合计3次；各程序先科学1秒、再参考k秒、再归档/空闲至总4秒，能源充足。'
        '计划没有实际效力，J不能覆盖K；推理和检索不推进故事时间。',event='background_subtraction_protocol',model=MODEL)
    add(2,'当前观测属于K的本轮目标T，参考R1—R5均已定义；设备正常，本轮科学曝光尚未发生，旧周期产品已经独立归档。',
        event='science_assignment',region='K',target='T',reference_lines=list(LINES[1:]),equipment_ready=True)

    def measure(at,region,line,band,value):
        key = (region,line,band)
        previous = background.get(key)
        cause = '背景初测' if previous is None else ('发光尘云实际移入/移出后完成背景复测' if previous != value else '背景再次实际复测确认保持')
        add(at,f'{region}-{line}谱段{band}：{cause}，绝对背景{value}计数/秒。',event='spectral_background_measured',
            region=region,line=line,band=band,previous_counts_per_s=previous,counts_per_s=value)
        background[key] = value

    def both(at,region,line,values):
        for band,value in enumerate(values,1):
            measure(at,region,line,band,value)

    def old_observation(at,cycle):
        ref,k = old
        finish = clock(f'08:{at:02d}')
        add(at,f'K片天空旧观测周期{cycle}：{story_timestamp(finish-4)}开始N{ref}-{k}，先科学1秒再参考{k}秒，'
            f'至{story_timestamp(finish)}完成4秒程序归档。两谱段各无偏恢复其当次真实信号，旧周期结束。',
            occurred=finish,event='old_science_completed',region='K',cycle=cycle,reference=f'R{ref}',reference_exposure_s=k,
            started_s=finish-4,science_finished_s=finish-3,reference_finished_s=finish-3+k,finished_s=finish,unbiased_bands=[1,2])

    if index < 6:
        for line in LINES:
            both(3,'K',line,initial[line])
        old_observation(6,'H1')
        old_observation(9,'H2')
        update_rounds,plan_round,final_rounds = (14,14),20,(24,24)
    elif index < 12:
        for at,lines in ((3,('T','R1')),(5,('R2','R3')),(7,('R4','R5'))):
            for line in lines:
                both(at,'K',line,initial[line])
        old_observation(10,'H1')
        old_observation(13,'H2')
        update_rounds,plan_round,final_rounds = (16,18),21,(24,25)
    else:
        for band,at in ((1,3),(2,7)):
            for line in LINES:
                measure(at,'K',line,band,initial[line][band-1])
        old_observation(9,'H1')
        both(11,'K','T',(7,7))
        both(13,'K','T',initial['T'])
        old_observation(15,'H2')
        update_rounds,plan_round,final_rounds = (18,19),22,(24,25)
    for line,code in updates:
        for band,(at,value) in enumerate(zip(update_rounds,vector(code),strict=True),1):
            measure(at,'K',line,band,value)
    add(plan_round,f'拟等待K-T背景恢复至两谱段{initial["T"][0]}/{initial["T"][1]}计数/秒后再作后续调度，目前没有观察到恢复。',
        event='science_background_plan',region='K',line='T',awaited_counts_per_s=list(initial['T']),restoration_observed=False)
    for line,code in final_updates:
        for band,(at,value) in enumerate(zip(final_rounds,vector(code),strict=True),1):
            measure(at,'K',line,band,value)
    for line in LINES:
        both(28,'J',line,initial[line])
    add(30,'K本轮目标T科学1秒曝光就绪，尚未开始观测。',event='science_ready',region='K',target='T')
    task = task_shell('FM-E2-D2',index)
    task.public = {'time_s':clock('09:00'),'region':'K','target':'T','reference_lines':list(LINES[1:]),'subtraction_model':MODEL,
        'max_steps':3,'state_fields':[],'instruction':'任务第120日09:00；本轮目标视线K-T；科学1秒曝光就绪。请选择完整科学/参考观测程序。',
        'actions':fixed_options([{'operation':{'kind':'observe','reference':f'R{j}','reference_exposure_s':k},
            'description':f'N{j}-{k}：科学曝光1秒，R{j}参考曝光{k}秒，直接扣除参考总计数并归档。'} for j in range(1,6) for k in (1,2)]+
            [{'operation':{'kind':'hold'},'description':'保持，不观测。'}])}
    task.initial = {'time_s':clock('09:00'),'science_exposures':0,'products':[],'opportunity_used':False}
    task.world = {'background_counts_per_s':{'T':list(vector(final_target)),**{f'R{i}':list(vector(c)) for i,c in enumerate(final_references,1)}},
                  'true_signal_counts':[100,200]}
    task.rubric = {'score':'50 per exactly unbiased independently recovered science band; reference counts are not normalised'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，不观测，操作结束。'
            return 0
        ref,k = operation['reference'],operation['reference_exposure_s']
        field,signal = self.task.world['background_counts_per_s'],self.task.world['true_signal_counts']
        raw = [s+b for s,b in zip(signal,field['T'],strict=True)]
        reference = [k*r for r in field[ref]]
        estimated = [s-r for s,r in zip(raw,reference,strict=True)]
        accepted = [i for i,(estimate,truth) in enumerate(zip(estimated,signal,strict=True),1) if estimate == truth]
        start = self.state['time_s']
        self.state['products'].append({'reference':ref,'reference_exposure_s':k,'science_raw_counts':raw,
            'reference_counts':reference,'estimated_signal_counts':estimated,'accepted_bands':accepted,'started_s':start,
            'science_finished_s':start+1,'reference_finished_s':start+1+k,'finished_s':start+4,'archived':True})
        self.state.update(time_s=start+4,science_exposures=1,opportunity_used=True)
        self.feedback = '所选科学与参考曝光已完成，两谱段产品已归档。'
        return 50*len(accepted)


def reconstruct(history,current):
    field = {line:{} for line in current['reference_lines']+['T']}
    for text in paragraphs(history):
        measurement = re.fullmatch(r'([KJ])-(T|R[1-5])谱段([12])：(背景初测|发光尘云实际移入/移出后完成背景复测|背景再次实际复测确认保持)，'
                                   r'绝对背景(\d+)计数/秒。',text)
        if measurement and measurement[1] == current['region']:
            _,line,printed_band,cause,printed_value = measurement.groups()
            band,value = int(printed_band),int(printed_value)
            previous = field[line].get(band)
            if ((cause == '背景初测' and previous is not None)
                    or (cause == '背景再次实际复测确认保持' and previous != value)
                    or (cause == '发光尘云实际移入/移出后完成背景复测' and (previous is None or previous == value))):
                raise ValueError('Background revisions must preserve each preceding local spectral component')
            field[line][band] = value
        science = re.fullmatch(rf'([KJ])片天空旧观测周期H\d+：{STORY_STAMP}开始N([1-5])-([12])，先科学1秒再参考([12])秒，'
                               rf'至{STORY_STAMP}完成4秒程序归档。两谱段各无偏恢复其当次真实信号，旧周期结束。',text)
        if science and science[1] == current['region']:
            ref,k = 'R'+science[2],int(science[3])
            if k != int(science[4]) or any(field['T'][b] != k*field[ref][b] for b in (1,2)):
                raise ValueError('Historical science must be unbiased under its actual then-current backgrounds')
    return {'background_counts_per_s':{line:[bands[1],bands[2]] for line,bands in field.items()}}


def next_action(facts,current):
    field = facts['background_counts_per_s']
    for ref in current['reference_lines']:
        for k in (1,2):
            if field['T'] == [k*r for r in field[ref]]:
                return decision_command(current,{'kind':'observe','reference':ref,'reference_exposure_s':k})
    raise ValueError('No reference operation restores both science components')


def check_world(task,facts):
    if facts['background_counts_per_s'] != task.world['background_counts_per_s']:
        raise ValueError('Science backgrounds differ from actual local measurements')


def audit_cases(task,facts,solution):
    field = facts['background_counts_per_s']
    def score(operation):
        if operation['kind'] == 'hold':
            return 0
        return 50*sum(b == operation['reference_exposure_s']*r for b,r in zip(field['T'],field[operation['reference']],strict=True))
    return decision_cases(task,solution,score)
