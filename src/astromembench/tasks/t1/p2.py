"""FM-T1-P2: sample age constrains analysis completion, not just its start."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('S1',(120,240,420),'V'),('S1',(240,120,420),'M'),('S1',(420,120,240),'L'),
    ('S1',(600,120,240),None),('S2',(300,150,480),'V'),('S3',(60,540,360),'M'),
    ('S2',(90,170,400),'V'),('S2',(90,190,400),'M'),('S3',(240,120,350),'M'),
    ('S3',(240,120,370),'L'),('S1',(560,240,120),'L'),('S1',(580,240,120),None),
    ('S2',(120,360,570),'M'),('S2',(120,361,570),'L'),('S3',(120,360,570),'L'),('S3',(120,360,571),None),
)
PROGRAMS = {
    'V':{'name':'全组分谱','duration_s':120,'value':4,'lifetime_s':300},
    'M':{'name':'中稳定组分谱','duration_s':60,'value':2,'lifetime_s':420},
    'L':{'name':'稳定元素快谱','duration_s':30,'value':1,'lifetime_s':600},
}


def _operation(sample=None,program=None):
    return {'sample':sample,'program':program}


def build(index):
    target,ages,best = CONFIGS[index]
    now = clock('12:00')
    seals = {f'S{i}':now-age for i,age in enumerate(ages,1)}
    history = ArchiveHistory(now)
    add = history.add

    add(1,'三份样品均已取得并置于独立恒温分析仓，低层分析、定位、编号和精度正常，本题只允许一次不可逆分析，取样质量相同。'
          '只分析当前指定Q8目标，其他样品不能替代；公开目标是最大化当前目标可实现科学价值。'
          '全组分谱V耗时120秒、价值4、须实际采集封口后300秒以内完成；中稳定组分谱M耗时60秒、价值2、须420秒以内完成；'
          '稳定元素快谱L耗时30秒、价值1、须600秒以内完成，完成恰等截止允许。'
          '保持期自实际采集封口起算，批准计划、转入仪器、分析计划生成均不重置；温度恒定且没有延寿处理。'
          '没有项目能按期完成时保持全部仓封闭，等待不能改善，不允许试测探查。'
          '有效/无效提交合计最多3次，首个有效选择完成后结束；分析动作实际消耗所选样品并经历完整耗时，业务错误不可纠正；end是放弃。'
          '记忆检索不推进故事时钟。上述保持期为合成评测模型，不是真实化学寿命经验。',
        event='sample_analysis_protocol',cycle='Q8',programs=PROGRAMS,completion_inclusive=True)
    rounds = (4,4,4) if index < 6 else (4,14,24) if index < 12 else (4,15,25)
    for (sample,sealed),at in zip(seals.items(),rounds,strict=True):
        add(at,f'{story_timestamp(sealed)}，Q8-{sample}采集并完成封口。',occurred=sealed,
            event='sample_sealed',cycle='Q8',sample=sample,sealed_s=sealed,sealed_at=story_timestamp(sealed))
    if 6 <= index < 12:
        add(27,'第120日11:59:20已为三份完成分析计划，无采样或封口动作。',occurred=clock('11:59:20'),event='analysis_planned')
    if index >= 12:
        sealed = clock('11:58',119)
        for sample in seals:
            add(8,f'{story_timestamp(sealed)}，上批Q7-{sample}采集并完成封口。',occurred=sealed,
                event='sample_sealed',cycle='Q7',sample=sample,sealed_s=sealed,sealed_at=story_timestamp(sealed))
        add(20,'第120日11:59:10建议重新采样，方案尚未批准且未执行。',occurred=clock('11:59:10'),event='resampling_proposed')
        add(28,'现有三份Q8样品已转入仪器，温控无改变，没有重新采样或封口。',event='instrument_transfer')
    add(30,'分析方案生成完毕，三个仓都未分析。',event='analysis_ready')
    group = f'FM-T1-P2-{target}'
    entries = [{'operation':_operation(sample,code),
                'description':f'分析{sample}，{program["name"]}，耗时{program["duration_s"]}秒、科学价值{program["value"]}。',
                'duration_s':program['duration_s'],'scientific_value':program['value']}
               for sample in seals for code,program in PROGRAMS.items()]
    entries.append({'operation':_operation(),'description':'保持全部样品仓封闭。','duration_s':0})
    task = task_shell('FM-T1-P2',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q8','target':target,'samples':list(seals),'max_steps':3,'state_fields':[],
                   'instruction':f'第120日12:00:00，Q8当前样品{target}，仓体与仪器正常，分析计划已就绪，请执行下一步。',
                   'actions':ordered_options(entries,group)}
    task.initial = {'time_s':now,'sample_consumed':{s:False for s in seals},'analysis':None}
    task.world = {'sealed_s':seals,'best_program':best,'maximum_value':0 if best is None else PROGRAMS[best]['value']}
    task.rubric = {'score':'100*on_time_target_program_value/maximum_feasible_value; with no feasible program only closed storage is full credit'}
    return history.finish(task)


def _feasible(sealed,now,programs):
    return [code for code,p in programs.items() if now+p['duration_s'] <= sealed+p['lifetime_s']]


def _score(operation,target,seals,now,programs):
    feasible = _feasible(seals[target],now,programs)
    if operation['sample'] is None:
        return 100 if not feasible else 0
    if operation['sample'] != target or operation['program'] not in feasible:
        return 0
    return 100*programs[operation['program']]['value']/max(programs[p]['value'] for p in feasible)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        now = self.state['time_s']
        sample,program = operation['sample'],operation['program']
        if sample is None:
            self.feedback = '全部样品仓保持封闭，未执行分析。'
        else:
            self.state['time_s'] += PROGRAMS[program]['duration_s']
            self.state['sample_consumed'][sample] = True
            self.state['analysis'] = {'sample':sample,'program':program,'started_s':now,'finished_s':self.state['time_s']}
            self.feedback = f'已对Q8-{sample}执行{PROGRAMS[program]["name"]}，完成于{story_timestamp(self.state["time_s"])}。'
        return _score(operation,self.task.public['target'],self.task.world['sealed_s'],now,PROGRAMS)


def reconstruct(history,current):
    seals,programs = {},None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        if f'只分析当前指定{current["cycle"]}目标' in text:
            programs = {code:{'name':name,'duration_s':int(duration),'value':int(value),'lifetime_s':int(lifetime)}
                        for name,code,duration,value,lifetime in re.findall(
                            r'([^。；]+谱)([VML])耗时(\d+)秒、价值(\d+)、须(?:实际采集封口后)?(\d+)秒以内完成',text)}
        seal = re.search(rf'({STORY_STAMP})，{cycle}-(S\d+)采集并完成封口。',text)
        if seal:
            seals[seal[2]] = seconds(seal[1])
    if set(seals) != set(current['samples']) or programs is None or set(programs) != {'V','M','L'}:
        raise ValueError('Missing current-batch actual sample seals or physical analysis model')
    feasible = _feasible(seals[current['target']],current['time_s'],programs)
    best = max(feasible,key=lambda p:programs[p]['value']) if feasible else None
    return {'sealed_s':seals,'programs':programs,'feasible':feasible,'best_program':best,
            'target':current['target'],'time_s':current['time_s']}


def next_action(facts,current):
    best = facts['best_program']
    return decision_command(current,_operation(current['target'],best) if best else _operation())


def check_world(task,facts):
    best = facts['best_program']
    value = 0 if best is None else facts['programs'][best]['value']
    if facts['sealed_s'] != task.world['sealed_s'] or best != task.world['best_program'] or value != task.world['maximum_value']:
        raise ValueError('Sample analysis optimum differs from actual seal and completion deadlines')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['target'],facts['sealed_s'],facts['time_s'],facts['programs']))
