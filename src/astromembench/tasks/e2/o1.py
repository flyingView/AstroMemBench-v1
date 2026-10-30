"""FM-E2-O1: actual local illumination changes and a single physical exposure."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

FLUX = {'1':(40,80),'2':(20,40),'3':(10,20),'4':(5,10),'5':(2.5,5),'X':(2,100)}
EXPOSURES = (1,2,4,8,16)
# Private shorthand only; every public measurement expands to actual L/R flux.
CONFIGS = (
    (('3','X'),('a',4),(('a','2'),),(('b','5'),),('a','1'),('2','5')),
    (('X','4'),('b',8),(('b','2'),),(('b','4'),),('a','3'),('X','4')),
    (('5','X'),('a',16),(('a','4'),),(('b','X'),),('b','1'),('4','X')),
    (('2','X'),('a',2),(('a','X'),),(('b','1'),),('a','5'),('X','1')),
    (('X','1'),('b',1),(('b','3'),),(('a','4'),),('b','5'),('4','3')),
    (('1','X'),('a',1),(('a','5'),),(('b','2'),),('a','3'),('5','2')),
    (('3','X'),('a',4),(('a','1'),('b','4')),(('b','X'),),('a','5'),('1','X')),
    (('4','X'),('a',8),(('a','2'),),(('b','3'),),('a','5'),('2','3')),
    (('5','X'),('a',16),(('a','3'),),(('a','5'),),('b','2'),('5','X')),
    (('1','X'),('a',1),(('a','3'),('b','5')),(('a','1'),),('b','2'),('1','5')),
    (('X','5'),('b',16),(('b','4'),),(('a','3'),),('a','1'),('3','4')),
    (('3','X'),('a',4),(('a','X'),('b','2')),(('b','4'),),('a','5'),('X','4')),
    (('X','4'),('b',8),(('b','1'),('a','2')),(('b','4'),),('a','5'),('2','4')),
    (('5','X'),('a',16),(('a','1'),('b','4')),(('a','3'),),('b','2'),('3','4')),
    (('X','3'),('b',4),(('b','5'),('a','1')),(('a','X'),),('b','2'),('X','5')),
    (('4','X'),('a',8),(('a','2'),('b','1')),(('a','5'),),('b','3'),('5','1')),
)
MODEL = {'counts_per_region':'flux_per_ms * exposure_ms','accepted_count_interval':[40,80],
         'independent_regions':['L','R'],'exposure_ms':list(EXPOSURES),'program_duration_s':20}


def build(index):
    initial,old,updates,final_updates,plan,final = CONFIGS[index]
    history,flux = History(),{}

    def add(at,text,**facts):
        history.add(at,text,record_id=f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}',**facts)

    add(1,'目标K/J独立，两固定拍摄位a/b均完整看见各自外表L/R。机身、相机、镜头、增益和指向固定正常；'
        '外部遮光帆/反光罩移动可改变光通量，实际测量只更新该目标、拍摄位、区域，持续到后续实际变化，没有未记录漂移。'
        '精确光度单位计数/ms，曝光t ms计数=f×t；闭区间[40,80]验收一项细节，低于40欠曝、高于80饱和。'
        '须分别完成两个独立区域的观测；只能拍一张图，不跨位拼接，不把重复图像当作新增观测。'
        'a/b均可曝光1/2/4/8/16ms，加保持共11项，所有选项始终开放。有效/无效/end合计最多3次，合法选择不可撤销且终局。'
        '每个拍摄程序20秒，最后t毫秒曝光，其余用于自动转位、对焦和归档，时间能源均充足，不能试拍或补拍。'
        '计划和材料到位不改光度，J的测量不改K。推理与检索不推进故事时间。',event='illumination_protocol',model=MODEL)
    add(2,'相机固定正常；K本轮L/R两项细节均尚未拍摄，过去巡检属于各自已结束的旧周期。',
        event='inspection_assignment',target='K',current_details_acquired=[])

    def measure(at,target,position,region,value):
        key = (target,position,region)
        previous = flux.get(key)
        cause = '初始光度测量' if previous is None else ('外部遮光帆/反光罩已实际移动后复测' if previous != value else '再次实际复测确认保持')
        add(at,f'{target}-{position}-{region}：{cause}，绝对光通量{value:g}计数/ms。',event='flux_measured',
            target=target,position=position,region=region,previous_flux_per_ms=previous,flux_per_ms=value)
        flux[key] = value

    def both(at,target,position,code):
        for region,value in zip(('L','R'),FLUX[code],strict=True):
            measure(at,target,position,region,value)

    def old_capture(at,cycle):
        position,exposure = old
        finish = clock(f'08:{at:02d}')
        counts = {region:flux['K',position,region]*exposure for region in ('L','R')}
        add(at,f'目标K旧巡检周期{cycle}：{story_timestamp(finish-20)}开始预置转位对焦，最后{exposure}ms在{position}曝光；'
            f'{story_timestamp(finish)}完成归档，L/R计数分别{counts["L"]:g}/{counts["R"]:g}，两项细节均合格。该旧周期已经结束。',
            occurred=finish,event='old_inspection_completed',target='K',cycle=cycle,position=position,exposure_ms=exposure,
            started_s=finish-20,finished_s=finish,exposure_start_offset_ms=20000-exposure,counts=counts,accepted_regions=['L','R'])

    if index < 6:
        for position,code in zip(('a','b'),initial,strict=True):
            both(3,'K',position,code)
        old_capture(6,'V1')
        old_capture(9,'V2')
        update_rounds,plan_round,final_rounds = (14,14),20,(24,24)
    else:
        for at,position,region in ((3,'a','L'),(5,'b','R'),(7,'a','R'),(9,'b','L')):
            measure(at,'K',position,region,FLUX[initial[('a','b').index(position)]][('L','R').index(region)])
        if index < 12:
            old_capture(11,'V1')
            old_capture(13,'V2')
            update_rounds,plan_round = (16,18),21
        else:
            old_capture(10,'V1')
            both(12,'K',old[0],'X')
            both(14,'K',old[0],initial[('a','b').index(old[0])])
            old_capture(15,'V2')
            update_rounds,plan_round = (18,19),22
        final_rounds = (24,25)
    for position,code in updates:
        for at,region,value in zip(update_rounds,('L','R'),FLUX[code],strict=True):
            measure(at,'K',position,region,value)
    position,code = plan
    add(plan_round,f'拟移动K-{position}的外部遮光件至L/R光通量{FLUX[code][0]:g}/{FLUX[code][1]:g}计数/ms，尚未执行。',
        event='illumination_plan',target='K',position=position,planned_flux_per_ms=dict(zip(('L','R'),FLUX[code],strict=True)),implemented=False)
    for position,code in final_updates:
        for at,region,value in zip(final_rounds,('L','R'),FLUX[code],strict=True):
            measure(at,'K',position,region,value)
    both(28,'J',plan[0],plan[1])
    add(30,'目标K本轮相机就绪，等待一次外表巡检拍摄。',event='inspection_ready',target='K',camera_ready=True)
    task = task_shell('FM-E2-O1',index)
    task.public = {'time_s':clock('09:00'),'target':'K','camera_ready':True,'exposure_model':MODEL,'max_steps':3,'state_fields':[],
        'instruction':'任务第120日09:00；目标K；相机就绪。请完成本轮外表巡检。',
        'actions':fixed_options([{'operation':{'kind':'capture','position':p,'exposure_ms':t},'description':f'在{p}位曝光{t}ms。'}
                                 for p in ('a','b') for t in EXPOSURES]+[{'operation':{'kind':'hold'},'description':'保持，不拍摄。'}])}
    task.initial = {'time_s':clock('09:00'),'images':[],'capture_opportunity_used':False}
    task.world = {'flux':{p:dict(zip(('L','R'),FLUX[c],strict=True)) for p,c in zip(('a','b'),final,strict=True)}}
    task.rubric = {'score':'50 per independent region whose actual image counts lie in the inclusive interval [40,80]'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，不拍摄，操作结束。'
            return 0
        position,exposure = operation['position'],operation['exposure_ms']
        counts = {region:value*exposure for region,value in self.task.world['flux'][position].items()}
        accepted = [region for region,value in counts.items() if 40 <= value <= 80]
        start = self.state['time_s']
        self.state['images'].append({'target':'K','position':position,'exposure_ms':exposure,'counts':counts,
            'accepted_regions':accepted,'started_s':start,'finished_s':start+20,'exposure_start_offset_ms':20000-exposure,'archived':True})
        self.state.update(time_s=start+20,capture_opportunity_used=True)
        self.feedback = f'已在{position}完成{exposure} ms曝光，图像已归档。'
        return 50*len(accepted)


def reconstruct(history,current):
    flux = {'a':{},'b':{}}
    def number(value):
        return float(value) if '.' in value else int(value)
    for text in paragraphs(history):
        measurement = re.fullmatch(r'([KJ])-([ab])-([LR])：(初始光度测量|外部遮光帆/反光罩已实际移动后复测|再次实际复测确认保持)，'
                                   r'绝对光通量(\d+(?:\.\d+)?)计数/ms。',text)
        if measurement and measurement[1] == current['target']:
            _,position,region,cause,printed = measurement.groups()
            value,previous = number(printed),flux[position].get(region)
            if ((cause == '初始光度测量' and previous is not None)
                    or (cause == '再次实际复测确认保持' and previous != value)
                    or (cause == '外部遮光帆/反光罩已实际移动后复测' and (previous is None or previous == value))):
                raise ValueError('Illumination revision must match the preceding local measurement')
            flux[position][region] = value
        capture = re.fullmatch(rf'目标([KJ])旧巡检周期V\d+：{STORY_STAMP}开始预置转位对焦，最后(\d+)ms在([ab])曝光；'
                               rf'{STORY_STAMP}完成归档，L/R计数分别(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)，'
                               r'两项细节均合格。该旧周期已经结束。',text)
        if capture and capture[1] == current['target']:
            counts = {r:f*int(capture[2]) for r,f in flux[capture[3]].items()}
            reported = {'L':number(capture[4]),'R':number(capture[5])}
            if counts != reported or not all(40 <= c <= 80 for c in counts.values()):
                raise ValueError('Past inspection must actually succeed under its then-current illumination')
    return {'flux':flux}


def next_action(facts,current):
    for position,values in facts['flux'].items():
        for exposure in EXPOSURES:
            if all(40 <= f*exposure <= 80 for f in values.values()):
                return decision_command(current,{'kind':'capture','position':position,'exposure_ms':exposure})
    raise ValueError('No complete exposure under the observed local illumination')


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Current illumination must follow each local actual measurement')


def audit_cases(task,facts,solution):
    def score(operation):
        if operation['kind'] == 'hold':
            return 0
        return 50*sum(40 <= f*operation['exposure_ms'] <= 80 for f in facts['flux'][operation['position']].values())
    return decision_cases(task,solution,score)
