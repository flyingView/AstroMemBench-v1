"""FM-T1-O3: independent pumps under start-only or whole-segment permissions."""
import re

from ..common import ArchiveHistory, clock, fixed_options, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('09:48',(('F','09:35','09:52',120),('F','09:20','09:49',180),('S','09:40','09:53',240)),'AC',(4,4,4),False),
    ('09:48',(('F','09:35','09:52',120),('F','09:20','09:51',180),('S','09:40','09:53',240)),'ABC',(5,5,5),False),
    ('10:22',(('F','10:00','10:23',120),('S','10:05','10:21',60),('S','10:25','10:40',180)),'',(4,4,4),False),
    ('10:00',(('F','09:50','10:03',120),('F','09:40','10:02',180),('S','09:59','10:00',240)),'A',(4,4,4),True),
    ('10:00',(('F','09:50','10:01',120),('S','09:58','10:01',180),('F','09:55','10:04',240)),'BC',(4,4,4),True),
    ('11:00',(('F','10:50','11:01',120),('S','10:40','11:00',180),('F','10:55','11:02',120)),'C',(4,4,4),True),
    ('11:36',(('S','11:20','11:38',240),('F','11:25','11:40',180),('F','11:30','11:38',180)),'AB',(3,13,24),False),
    ('12:44',(('F','12:25','12:45',120),('S','12:20','12:43',180),('S','12:44','12:49',120)),'C',(4,12,24),False),
    ('13:18',(('F','13:00','13:20',180),('S','13:10','13:19',300),('S','13:20','13:28',120)),'B',(3,14,23),False),
    ('11:42',(('F','11:30','11:43',120),('F','11:25','11:44',180),('S','11:42:01','11:50',60)),'',(3,13,24),True),
    ('12:08',(('S','12:00','12:09',300),('F','11:55','12:10',180),('F','12:00','12:12',240)),'AC',(3,13,24),True),
    ('12:08',(('F','12:00','12:09',300),('F','11:55','12:11',180),('F','12:00','12:12',240)),'BC',(3,13,24),True),
    ('14:32:00',(('F','14:20','14:34',120),('S','14:20','14:32',120),('S','14:32','14:35',180)),'AC',(10,18,25),False),
    ('15:16:01',(('F','15:00','15:18',120),('S','15:00','15:16',60),('S','15:15','15:19',180)),'C',(9,17,25),False),
    ('10:00:00',(('F','09:50','10:02',120),('S','10:00','10:00:01',240),('F','09:55','10:01:59',120)),'AB',(10,18,25),True),
    ('10:00:01',(('F','09:50','10:02',120),('S','10:00','10:00:01',240),('F','09:55','10:02',120)),'',(10,18,25),True),
)
QUANTITIES = {'A':4,'B':2,'C':3}
FIXED_MENUS = {
    0:('Q15','AB','A','C','AC','D','B','','BC','ABC'),
    1:('Q15','A','BC','AC','ABC','C','D','','B','AB'),
    2:('','AB','Q15','A','BC','ABC','D','C','AC','B'),
    6:('C','AB','ABC','A','BC','AC','Q15','','D','B'),
    7:('C','D','A','','BC','ABC','B','AB','AC','Q15'),
    8:('AB','BC','AC','','D','C','Q15','B','ABC','A'),
    12:('Q15','ABC','B','D','A','','BC','AC','AB','C'),
    13:('A','C','Q15','AC','B','AB','','D','ABC','BC'),
}


def _operation(segments,cycle='Q16'):
    return {'cycle':cycle,'segments':list(segments)}


def build(index):
    now,config,valid,rounds,status = CONFIGS[index]
    now = clock(now)
    history = ArchiveHistory(now,spacing_s=120)
    history.add(1,'Q16补给A/B/C有独立泵组和储罐，每段不可拆分；供给端各初有4/2/3个等值补给单位，接收端各有4/2/3单位空余容量。'
                '每段按固定流量完成全量等额扣供增收，流率为该段全量除许可档案中的段耗时，耗时为正整数秒，无中途故障。'
                'S型许可只限启动，起点包含、终点不包含，已预留后续耗时；F型还要求整个段在截止前完成，结束恰等截止允许。'
                '许可绑定阶段与接收段，准备、计划和连接不注入、不续期。物质、接口、密封与姿态全部正常。'
                '可选子集真正并行、同刻启动各自完整持续，不按串行耗时，不少注，不等待或分两次启动。'
                '所有当前合法段均待补给，应完成全部可用量；若含任一非法段，或旧Q15、清单外D，整次不能验收；无合法段应隔离待命。'
                '有效/无效提交合计3次，首个有效选择完整执行后结束，end是放弃，不能预检后重试。'
                '当前观测保留决策时刻快照，终局只返回记录存档；推理和记忆检索不推进故事时钟。',
                event='supply_protocol',cycle='Q16',quantities=QUANTITIES)

    def permit(at,cycle,segment,kind,start,end,duration=None):
        facts = {'event':'supply_permission','cycle':cycle,'segment':segment,'kind':kind,
                 'start_s':start,'end_s':end,'start_at':story_timestamp(start),'end_at':story_timestamp(end)}
        suffix = ''
        if duration is not None:
            facts['duration_s'] = duration
            suffix = f'完整段耗时{duration}秒。'
        history.add(at,f'{cycle}接收段{segment}，{kind}型许可{story_timestamp(start)}至{story_timestamp(end)}，起点含、终点不含。'+suffix,**facts)

    if index == 12:
        permit(3,'Q15','B','S',clock('14:10'),clock('14:40'))
    elif index == 13:
        permit(3,'Q15','A','S',clock('15:00'),clock('15:30'))
    elif index >= 14:
        for segment in 'ABC':
            permit(3,'Q15',segment,'S',now-86400-600,now-86400+600,120)
    permissions = {}
    for segment,(kind,start,end,duration),at in zip('ABC',config,rounds,strict=True):
        start,end = clock(start),clock(end)
        permit(at,'Q16',segment,kind,start,end,duration)
        permissions[segment] = {'kind':kind,'start_s':start,'end_s':end,'duration_s':duration}
    history.add(28,'准备任务曾按预估时刻安排；转位与计算耗时后，当前作业计划才生成，尚未执行。',event='planning_status')
    if status:
        history.add(30,'连接与泵组正常。',event='pump_status')
    group = f'FM-T1-O3-fixed-{index+1:02d}' if index in FIXED_MENUS else f'FM-T1-O3-{now}'
    entries = [{'operation':_operation(s),'description':f'同时向Q16接收段{s}注入完整段。' if s else '保持隔离待命。'}
               for s in ('','A','B','C','AB','AC','BC','ABC')]
    entries += [{'operation':_operation('ABC','Q15'),'description':'按旧阶段Q15向ABC注入。'},
                {'operation':_operation('D'),'description':'向本次清单外D注入。'}]
    if index in FIXED_MENUS:
        by_code = {''.join(row['operation']['segments']) if row['operation']['cycle'] == 'Q16' else 'Q15':row for row in entries}
        actions = fixed_options([by_code[code] for code in FIXED_MENUS[index]])
    else:
        actions = ordered_options(entries,group)
    task = task_shell('FM-T1-O3',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q16','segments':list('ABC'),'max_steps':3,'state_fields':[],
                   'instruction':f'{story_timestamp(now)}，对接阶段Q16，接收段A/B/C独立泵组均就绪。准备完成，请选择现在执行的作业。',
                   'actions':actions}
    task.initial = {'time_s':now,'supply':dict(QUANTITIES),'received':{s:0 for s in QUANTITIES},'transfers':[]}
    task.world = {'permissions':permissions,'valid_segments':list(valid),'denominator':sum(QUANTITIES[s] for s in valid)}
    task.rubric = {'score':'100*valid_selected_supply/all_available_supply; any illegal member zero; empty validity requires standby'}
    return history.finish(task)


def _score(operation,valid,quantities):
    selected = set(operation['segments'])
    if operation['cycle'] != 'Q16' or not selected <= set(valid):
        return 0
    if not valid:
        return 100 if not selected else 0
    return 100*sum(quantities[s] for s in selected)/sum(quantities[s] for s in valid)


class Runtime(DecisionRuntime):
    def observation(self):
        result = super().observation()
        # This template exposes the decision snapshot, never private pump durations.
        result.update(time_s=self.task.public['time_s'],current_time=story_timestamp(self.task.public['time_s']))
        return result

    def execute(self,operation):
        now = self.state['time_s']
        if operation['cycle'] == 'Q16':
            for segment in operation['segments']:
                if segment not in QUANTITIES:
                    continue
                quantity = QUANTITIES[segment]
                duration = self.task.world['permissions'][segment]['duration_s']
                self.state['supply'][segment] -= quantity
                self.state['received'][segment] += quantity
                self.state['transfers'].append({'segment':segment,'quantity':quantity,'started_s':now,'finished_s':now+duration})
            self.state['time_s'] = max((t['finished_s'] for t in self.state['transfers']),default=now)
        self.feedback = '操作已执行，记录已存档。'
        return _score(operation,self.task.world['valid_segments'],QUANTITIES)


def reconstruct(history,current):
    permissions,quantities = {},None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        supply = re.search(rf'{cycle}补给([A-Z/]+)有独立泵组和储罐，每段不可拆分；供给端各初有([\d/]+)个等值补给单位',text)
        if supply:
            quantities = dict(zip(supply[1].split('/'),map(int,supply[2].split('/')),strict=True))
        permit = re.search(rf'{cycle}接收段([A-Z])，([SF])型许可({STORY_STAMP})至({STORY_STAMP})，起点含、终点不含。完整段耗时(\d+)秒。',text)
        if permit:
            permissions[permit[1]] = {'kind':permit[2],'start_s':seconds(permit[3]),
                                     'end_s':seconds(permit[4]),'duration_s':int(permit[5])}
    if set(permissions) != set(current['segments']) or quantities is None:
        raise ValueError('Missing full current supply permissions or quantities')
    now = current['time_s']
    valid = [s for s in current['segments'] if permissions[s]['start_s'] <= now < permissions[s]['end_s']
             and (permissions[s]['kind'] == 'S' or now+permissions[s]['duration_s'] <= permissions[s]['end_s'])]
    return {'permissions':permissions,'quantities':quantities,'valid_segments':valid}


def next_action(facts,current):
    return decision_command(current,_operation(facts['valid_segments']))


def check_world(task,facts):
    if facts['permissions'] != task.world['permissions'] or facts['valid_segments'] != task.world['valid_segments']:
        raise ValueError('Supply legality differs from start-only versus full-segment permissions')
    if sum(facts['quantities'][s] for s in facts['valid_segments']) != task.world['denominator']:
        raise ValueError('Supply denominator differs from available quantity')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['valid_segments'],facts['quantities']))
