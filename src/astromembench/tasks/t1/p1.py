"""FM-T1-P1: simultaneous survey subsets under half-open start permissions."""
import re

from ..common import ArchiveHistory, clock, fixed_options, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

# Current time, A/B/C windows, full-credit subset, direct native publication rounds.
CONFIGS = (
    ('09:42',(('09:30','09:46'),('09:20','09:40'),('09:35','09:48')),'AC',(4,4,4),False),
    ('09:42',(('09:30','09:46'),('09:20','09:44'),('09:35','09:48')),'ABC',(5,5,5),False),
    ('10:08',(('09:40','10:02'),('09:50','10:04'),('09:45','10:06')),'',(4,4,4),False),
    ('10:16',(('10:00','10:15'),('10:05','10:25'),('10:16','10:30')),'BC',(4,4,4),True),
    ('10:40',(('10:42','10:50'),('10:30','10:55'),('10:20','10:39')),'B',(4,4,4),True),
    ('11:00',(('10:40','10:59'),('11:02','11:20'),('10:55','11:05')),'C',(4,4,4),True),
    ('11:18',(('11:00','11:16'),('11:10','11:23'),('11:20','11:32')),'B',(3,13,22),False),
    ('12:26',(('12:15','12:29'),('12:20','12:31'),('12:05','12:24')),'AB',(4,12,24),False),
    ('13:33',(('13:10','13:29'),('13:35','13:48'),('13:28','13:39')),'C',(3,14,23),False),
    ('10:10',(('10:08','10:12'),('10:11','10:18'),('09:55','10:09')),'A',(3,13,23),True),
    ('10:10',(('10:08','10:12'),('10:09','10:18'),('09:55','10:11')),'ABC',(3,13,23),True),
    ('11:48',(('11:49','12:03'),('11:35','11:47'),('11:41','11:48')),'',(3,13,23),True),
    ('14:20:00',(('14:00','14:20'),('14:20','14:24'),('14:21','14:25')),'B',(9,18,25),False),
    ('15:12:30',(('15:10','15:13'),('15:00','15:12:30'),('15:12:30','15:16')),'AC',(9,17,25),False),
    ('11:30:30',(('11:30:31','11:35'),('11:28','11:30:31'),('11:30:30','11:33')),'BC',(9,18,25),True),
    ('13:16:00',(('13:15','13:16'),('13:16:01','13:18'),('13:14','13:16:01')),'C',(9,18,25),True),
)
WEIGHTS = {'A':2,'B':3,'C':1}
FIXED_MENUS = {
    0:('C','AC','B','AB','ABC','','A','Q15','D','BC'),
    1:('B','ABC','C','BC','Q15','AB','','AC','A','D'),
    2:('A','B','C','D','','AB','AC','BC','Q15','ABC'),
    6:('A','AB','','BC','C','D','AC','B','ABC','Q15'),
    7:('B','AC','D','A','Q15','','C','ABC','AB','BC'),
    8:('AC','','D','ABC','Q15','B','AB','A','BC','C'),
    12:('AC','AB','ABC','C','A','B','BC','Q15','D',''),
    13:('ABC','C','AB','B','Q15','AC','','D','BC','A'),
}


def _operation(areas,cycle='Q16'):
    return {'cycle':cycle,'areas':list(areas)}


def build(index):
    now,windows,valid,rounds,channel_check = CONFIGS[index]
    now = clock(now)
    history = ArchiveHistory(now,spacing_s=120)
    add = history.add

    add(1,'本轮Q16测区A/B/C各独立测量通道，可同时启动任意子集；分别产出2/3/1个等价值测量单元，每区只执行一次。'
          '光照许可按轮次和测区绑定，仅限制启动，包含起点、不含终点；后续采集时长已预留。'
          '地形、定位、相机、数据空间均已满足，不必重算太阳几何。所有当前合法测区均是待办，应取得全部可用测量单元。'
          '准备、转位、计划不是实际采集，也不延长许可；不得推迟选择等待新窗口。'
          '组合各通道同刻启动，不串行；若组合含任何非法区则整次不能验收，旧Q15或清单外D同样不能验收。'
          '没有合法区时应待命，提前end是放弃。有效/无效提交合计最多3次，首个有效选择完整执行后结束；记忆检索不推进故事时钟。',
        event='survey_protocol',cycle='Q16',weights=WEIGHTS,start_inclusive=True,end_inclusive=False)

    def permit(at,cycle,area,start,end,extra=''):
        add(at,f'调度许可：{cycle}测区{area}启动区间{story_timestamp(start)}至{story_timestamp(end)}，包含起点不含终点。'+extra,
            event='survey_permission',cycle=cycle,area=area,start_s=start,end_s=end,
            start_at=story_timestamp(start),end_at=story_timestamp(end))

    if index == 12:
        permit(3,'Q15','A',clock('14:00'),clock('14:30'))
    elif index == 13:
        permit(3,'Q15','B',clock('15:00'),clock('15:20'))
    elif index >= 14:
        for area in 'ABC':
            permit(3,'Q15',area,now-86400-600,now-86400+600,'独立旧轮许可不沿用。')
    for area,(start,end),at in zip('ABC',windows,rounds,strict=True):
        extra = '转位预计10分钟；这是估计，不是采集或许可延长。' if index == 2 and area == 'A' else ''
        if index == 7 and area == 'C':
            extra = '测量准备曾预计12:23结束；这是估计，不是采集或许可延长。'
        permit(at,'Q16',area,clock(start),clock(end),extra)
    add(28,'准备任务曾按预估时刻安排；转位与计算耗时后，当前作业计划才生成，尚未执行。',event='planning_status')
    if channel_check:
        add(30,'设备通道检查正常。',event='channel_status')
    group = f'FM-T1-P1-fixed-{index+1:02d}' if index in FIXED_MENUS else f'FM-T1-P1-{now}'
    task = task_shell('FM-T1-P1',index,current_input_group=group)
    entries = [{'operation':_operation(areas),'description':f'同时启动Q16测区{areas}采集。' if areas else '保持待命，不启动测量。'}
               for areas in ('','A','B','C','AB','AC','BC','ABC')]
    entries += [{'operation':_operation('ABC','Q15'),'description':'按旧Q15执行A/B/C全部采集。'},
                {'operation':_operation('D'),'description':'启动本批清单之外的D区采集。'}]
    if index in FIXED_MENUS:
        by_code = {''.join(row['operation']['areas']) if row['operation']['cycle'] == 'Q16' else 'Q15':row for row in entries}
        actions = fixed_options([by_code[code] for code in FIXED_MENUS[index]])
    else:
        actions = ordered_options(entries,group)
    task.public = {'time_s':now,'cycle':'Q16','areas':list('ABC'),'max_steps':3,'state_fields':[],
                   'instruction':f'{story_timestamp(now)}，Q16区域测量，A/B/C各独立通道均就绪。准备完成，请选择现在执行的作业。',
                   'actions':actions}
    task.initial = {'time_s':now,'started':[],'measurement_units':0}
    task.world = {'windows':{a:{'start_s':clock(s),'end_s':clock(e)} for a,(s,e) in zip('ABC',windows,strict=True)},
                  'valid_areas':list(valid),'denominator':sum(WEIGHTS[a] for a in valid)}
    task.rubric = {'score':'100*selected_valid_units/all_current_valid_units; any invalid area is zero; empty validity requires standby'}
    return history.finish(task)


def _score(operation,valid,weights):
    selected = set(operation['areas'])
    if operation['cycle'] != 'Q16' or not selected <= set(valid):
        return 0
    if not valid:
        return 100 if not selected else 0
    return 100*sum(weights[a] for a in selected)/sum(weights[a] for a in valid)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['cycle'] == 'Q16':
            self.state['started'] = [a for a in operation['areas'] if a in WEIGHTS]
            self.state['measurement_units'] = sum(WEIGHTS[a] for a in self.state['started'])
        self.feedback = '操作已执行，记录已存档。'
        return _score(operation,self.task.world['valid_areas'],WEIGHTS)


def reconstruct(history,current):
    windows,weights = {},None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        protocol = re.search(rf'本轮{cycle}测区([A-Z/]+)各独立测量通道，可同时启动任意子集；分别产出([\d/]+)个等价值测量单元',text)
        if protocol:
            weights = dict(zip(protocol[1].split('/'),map(int,protocol[2].split('/')),strict=True))
        permit = re.search(rf'调度许可：{cycle}测区([A-Z])启动区间({STORY_STAMP})至({STORY_STAMP})，包含起点不含终点。',text)
        if permit:
            windows[permit[1]] = {'start_s':seconds(permit[2]),'end_s':seconds(permit[3])}
    if set(windows) != set(current['areas']) or weights is None:
        raise ValueError('Missing complete current-cycle survey permissions or weights')
    valid = [a for a in current['areas'] if windows[a]['start_s'] <= current['time_s'] < windows[a]['end_s']]
    return {'windows':windows,'weights':weights,'valid_areas':valid}


def next_action(facts,current):
    return decision_command(current,_operation(facts['valid_areas']))


def check_world(task,facts):
    if facts['windows'] != task.world['windows'] or facts['valid_areas'] != task.world['valid_areas']:
        raise ValueError('Survey validity differs from public half-open permissions')
    if sum(facts['weights'][a] for a in facts['valid_areas']) != task.world['denominator']:
        raise ValueError('Survey denominator differs from available measurement units')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda operation:_score(operation,facts['valid_areas'],facts['weights']))
