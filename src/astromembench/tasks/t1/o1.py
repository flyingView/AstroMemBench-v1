"""FM-T1-O1: compare exposures within a two-sided interval; accept every valid pair."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('U',(180,60,420),(1,)),('U',(60,420,180),(3,)),('U',(60,420,600),()),
    ('V',(150,240,450),(1,2)),('V',(150,210,270),(1,2,3)),('W',(30,90,110),()),
    ('V',(310,250,100),(2,)),('V',(290,250,100),(1,2)),('W',(110,330,200),(3,)),
    ('W',(130,330,200),(1,3)),('U',(305,115,400),()),('V',(295,115,400),(1,)),
    ('U',(119,300,301),(2,)),('U',(120,300,301),(1,2)),('V',(301,119,120),(3,)),('V',(301,119,119),()),
)


def _operation(component=None,frame=None):
    return {'component':component,'frame':frame}


def build(index):
    target,ages,valid = CONFIGS[index]
    now = clock('12:00')
    all_ages = {'U':(80,160,340),'V':(300,100,500),'W':(40,600,250)}
    all_ages[target] = ages
    exposures = {component:{f'F{i}':now-age for i,age in enumerate(values,1)} for component,values in all_ages.items()}
    history = ArchiveHistory(now)
    history.add(1,'部件U/V/W各存Q8参考帧F1/F2/F3，槽号不编码拍摄时刻或优劣，各旧帧光学质量、同部件配准和曝光条件均满足。'
                '三个独立通道在第120日12:00:00自动取得各部件本轮新帧，当前只处理指定部件。'
                '需要同部件同Q8的新旧两次实际曝光相隔至少120秒且最多300秒，两端均包含。'
                '比较计算耗时固定10秒，配对间隔只按两次曝光，不按计算完成时刻；等待不改变已发生曝光差。'
                '任一满足条件的参考均完成同一产品，无优先级；不得偷偷挑最新或特定编号。'
                '缓存调入、索引重建、重新计划不是曝光。无可用参考时归档新帧等待后续安排，本题不能补拍再等待。'
                '完整菜单的比较操作使用所选部件自己的本轮新帧；有效/无效提交合计3次，首个有效选择实际执行后结束，end是放弃。'
                '不能预检配对条件后改选；记忆检索和实际推理不推进故事时钟。本题不考图像识别，无需加载图片。',
                event='inspection_comparison_protocol',cycle='Q8',minimum_interval_s=120,maximum_interval_s=300,comparison_duration_s=10)
    for component,frames in exposures.items():
        for number,(frame,exposure) in enumerate(frames.items(),1):
            at = 4 if index < 6 else (4,14,24)[number-1]
            history.add(at,f'{story_timestamp(exposure)}，Q8部件{component}参考槽{frame}实际曝光并存储。',occurred=exposure,
                        event='reference_exposed',cycle='Q8',component=component,frame=frame,exposure_s=exposure,exposure_at=story_timestamp(exposure))
            if index >= 12:
                old = clock(('11:57','11:58','11:59')[number-1],119)
                history.add(8,f'{story_timestamp(old)}，旧Q7部件{component}参考槽{frame}实际曝光并存储。',occurred=old,
                            event='reference_exposed',cycle='Q7',component=component,frame=frame,exposure_s=old,exposure_at=story_timestamp(old))
    if 6 <= index < 12:
        history.add(27,'第120日11:59:20索引重建完成，没有曝光。',occurred=clock('11:59:20'),event='index_rebuilt')
    if index >= 12:
        history.add(26,'本轮所有图像已复制到处理缓存，没有曝光。',event='cache_copied')
    history.add(30,'三个通道待取本轮新帧，将于12:00:00自动曝光。',event='new_exposure_scheduled')
    group = f'FM-T1-O1-{target}'
    entries = [{'operation':_operation(component,frame),'description':f'比较Q8部件{component}本轮新帧与参考{frame}，计算10秒。'}
               for component in exposures for frame in ('F1','F2','F3')]
    entries.append({'operation':_operation(),'description':'归档当前帧并结束本次比较。'})
    task = task_shell('FM-T1-O1',index,current_input_group=group)
    task.public = {'time_s':now,'new_frame_s':now,'new_frame_at':story_timestamp(now),'cycle':'Q8','target':target,
                   'components':list(exposures),'reference_slots':['F1','F2','F3'],'max_steps':3,'state_fields':[],
                   'instruction':f'第120日12:00:00，Q8目标{target}，本轮新帧已取得，参考槽F1/F2/F3在库，处理器正常，请执行下一步。',
                   'actions':ordered_options(entries,group)}
    task.initial = {'time_s':now,'comparison':None,'archived_target':None}
    task.world = {'exposures':exposures,'valid_frames':[f'F{i}' for i in valid]}
    task.rubric = {'score':'100 for any target pair with exposure interval in [120,300]; no valid target pair requires archival'}
    return history.finish(task)


def _score(operation,target,valid):
    if operation['component'] is None:
        return 100 if not valid else 0
    return 100 if operation['component'] == target and operation['frame'] in valid else 0


class Runtime(DecisionRuntime):
    def execute(self,operation):
        component,frame = operation['component'],operation['frame']
        if component is None:
            self.state['archived_target'] = self.task.public['target']
            self.feedback = f'Q8部件{self.task.public["target"]}当前新帧已归档，本次未执行比较。'
        else:
            old = self.task.world['exposures'][component][frame]
            new = self.task.public['new_frame_s']
            self.state['time_s'] += 10
            self.state['comparison'] = {'component':component,'old_frame':frame,'old_exposure_s':old,
                                        'new_frame':f'Q8-{component}-NEW','new_exposure_s':new,'finished_s':self.state['time_s']}
            self.feedback = f'已比较Q8-{component}-{frame}（曝光{story_timestamp(old)}）与Q8-{component}-NEW（曝光{story_timestamp(new)}），完成于{story_timestamp(self.state["time_s"])}。'
        return _score(operation,self.task.public['target'],self.task.world['valid_frames'])


def reconstruct(history,current):
    exposures = {c:{} for c in current['components']}
    minimum,maximum = None,None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        bounds = re.search(rf'需要同部件同{cycle}的新旧两次实际曝光相隔至少(\d+)秒且最多(\d+)秒，两端均包含',text)
        if bounds:
            minimum,maximum = map(int,bounds.groups())
        exposed = re.search(rf'({STORY_STAMP})，{cycle}部件([A-Z])参考槽(F\d+)实际曝光并存储。',text)
        if exposed:
            exposures[exposed[2]][exposed[3]] = seconds(exposed[1])
    if minimum is None or any(set(f) != set(current['reference_slots']) for f in exposures.values()):
        raise ValueError('Missing full reference exposure archive or comparison interval')
    valid = [f for f in current['reference_slots'] if minimum <= current['new_frame_s']-exposures[current['target']][f] <= maximum]
    return {'exposures':exposures,'valid_frames':valid,'target':current['target']}


def next_action(facts,current):
    return decision_command(current,_operation(current['target'],facts['valid_frames'][0]) if facts['valid_frames'] else _operation())


def check_world(task,facts):
    if facts['exposures'] != task.world['exposures'] or facts['valid_frames'] != task.world['valid_frames']:
        raise ValueError('Inspection pairing differs from actual exposure times')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['target'],facts['valid_frames']))
