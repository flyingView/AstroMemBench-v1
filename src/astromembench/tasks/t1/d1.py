"""FM-T1-D1: guarantee a closed trigger envelope fits a half-open permission."""
from decimal import Decimal
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, microseconds, paragraphs
from ...schema import story_timestamp

# Permission offsets are exact integer microseconds, including 0.1 ms cases.
CONFIGS = (
    ((40,140,340),-10000,10000,('X0',)),((140,40,340),10000,30000,('Y20',)),
    ((140,340,40),30000,50000,('Z40',)),((140,240,340),-10000,10000,()),
    ((40,140,340),-40000,60000,('X0','X20','X40','Y0','Y20','Y40','Z0','Z20')),
    ((40,140,340),-50000,100000,('X0','X20','X40','Y0','Y20','Y40','Z0','Z20','Z40')),
    ((90,190,390),-10000,11000,('X0',)),((90,190,390),-10000,10000,()),
    ((190,90,290),-20000,40000,('X0','Y0','Y20')),((190,90,290),0,60000,('X20','Y20','Y40')),
    ((390,340,290),-40000,41000,('X0','Y0','Z0')),((390,340,290),-40000,40000,('Y0','Z0')),
    ((90,89,91),-10000,10000,('Y0',)),((90,89,91),-10000,10100,('X0','Y0')),
    ((40,90,140),25000,55000,('X40','Y40')),((40,90,140),25000,55100,('X40','Y40','Z40')),
)


def _stamp(microseconds):
    seconds,remainder = divmod(microseconds,1_000_000)
    fraction = f'{remainder:06d}'.rstrip('0').ljust(3,'0')
    return f'{story_timestamp(seconds)}.{fraction}'


def _operation(timer=None,delay=None):
    return {'timer':timer,'delay_ms':delay}


def build(index):
    ages,start,end,valid = CONFIGS[index]
    now = clock('12:00')
    base_us = (now+1)*1_000_000
    calibration = {timer:now-age for timer,age in zip('XYZ',ages,strict=True)}
    permission = {'start_us':base_us+start,'end_us':base_us+end}
    history = ArchiveHistory(now)
    history.add(1,'Q8导航测距，主钟准确，X/Y/Z三个独立定时器均正常，波束已对准，无需修复。'
                '距该通道最后一次实际相位校准完成a秒后，本次触发误差界u=1+0.1a毫秒；可在闭区间[-u,+u]任意取值。'
                '此包络已涵盖从当前主钟T起2秒内全部漂移，不按将来触发时刻递归老化，不抽样误差，也不赌一次偶然命中。'
                '要求任意允许误差下，极短测距脉冲起始瞬间都在本轮许可中，许可含起点不含终点，后续接收已预留。'
                '当前冻结T下发一次预约，基准B=T后1秒，各通道可选名义B+0/20/40毫秒；所有可能触发均在决策后。'
                '可保证落窗的任一方案等价，没有指定最新定时器或最早延迟；没有任何保证方案就保持发射待机。'
                '计划、寄存器写入、校准申请都不等于实际校准完成，旧Q7不更新Q8。'
                '有效/无效提交总计3次，首个有效选择终止，end是放弃；推理和记忆检索不推进故事时间，不可自行等待改选。'
                '误差模型是题内假设，不是真实导航时钟指标。',
                event='trigger_protocol',cycle='Q8',base_uncertainty_us=1000,aging_us_per_s=100,delays_ms=[0,20,40])
    for position,(timer,stamp) in enumerate(calibration.items()):
        history.add(4 if index < 6 else (4,14,24)[position],f'{story_timestamp(stamp)}，Q8定时器{timer}实际相位校准完成。',
                    occurred=stamp,event='phase_calibrated',cycle='Q8',timer=timer,calibrated_s=stamp,calibrated_at=story_timestamp(stamp))
        if index >= 12:
            old = clock('11:59:20',119)
            history.add(6,f'{story_timestamp(old)}，旧Q7定时器{timer}实际相位校准完成。',occurred=old,
                        event='phase_calibrated',cycle='Q7',timer=timer,calibrated_s=old,calibrated_at=story_timestamp(old))
    history.add(12 if index < 6 else 8,f'Q8测距触发许可：{_stamp(permission["start_us"])}至{_stamp(permission["end_us"])}，含起点、不含终点。',
                event='trigger_permission',cycle='Q8',**permission,start_at=_stamp(permission['start_us']),end_at=_stamp(permission['end_us']))
    if index >= 12:
        history.add(20,'第120日11:59:05相位再校准申请已提交，尚未执行。',occurred=clock('11:59:05'),event='calibration_requested')
        history.add(27,'导航计划写入寄存器完成，无相位校准操作。',event='register_written')
    history.add(30,'发射器待机、当前导航计划已就绪。',event='trigger_ready')
    group = 'FM-T1-D1'
    entries = [{'operation':_operation(timer,delay),'description':f'下发定时器{timer}，名义触发为B+{delay}毫秒（{_stamp(base_us+delay*1000)}）。',
                'nominal_at':_stamp(base_us+delay*1000)} for timer in 'XYZ' for delay in (0,20,40)]
    entries.append({'operation':_operation(),'description':'保持测距发射待机。'})
    task = task_shell(group,index,current_input_group=group)
    task.public = {'time_s':now,'master_time_at':_stamp(now*1_000_000),'base_us':base_us,'base_at':_stamp(base_us),
                   'cycle':'Q8','timers':list('XYZ'),'max_steps':3,'state_fields':[],
                   'instruction':'第120日12:00:00.000，Q8测距任务，预定基准B为12:00:01.000，三套定时器在线，请下发本次触发或保持待机。',
                   'actions':ordered_options(entries,group)}
    task.initial = {'time_s':now,'scheduled_trigger':None}
    task.world = {'calibrated_s':calibration,'permission':permission,
                  'valid_operations':[_operation(code[0],int(code[1:])) for code in valid]}
    task.rubric = {'score':'100 iff every allowed error is inside permission; all guaranteeing schedules accepted; no valid schedule requires standby'}
    return history.finish(task)


def _score(operation,valid):
    return 100 if operation in valid or (not valid and operation['timer'] is None) else 0


class Runtime(DecisionRuntime):
    def execute(self,operation):
        timer,delay = operation['timer'],operation['delay_ms']
        if timer is None:
            self.feedback = '测距发射保持待机，未下发触发。'
        else:
            nominal = self.task.public['base_us']+delay*1000
            self.state['scheduled_trigger'] = {'timer':timer,'nominal_us':nominal,'issued_s':self.state['time_s']}
            self.feedback = f'已下发定时器{timer}，名义触发时刻{_stamp(nominal)}。'
        return _score(operation,self.task.world['valid_operations'])


def reconstruct(history,current):
    calibrated,permission,protocol = {},None,None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        calibration = re.fullmatch(rf'({STORY_STAMP})，{cycle}定时器([XYZ])实际相位校准完成。', text)
        window = re.fullmatch(rf'{cycle}测距触发许可：({STORY_STAMP})至({STORY_STAMP})，含起点、不含终点。', text)
        if calibration:
            calibrated[calibration[2]] = microseconds(calibration[1]) // 1_000_000
        elif window:
            permission = {'start_us':microseconds(window[1]), 'end_us':microseconds(window[2])}
        elif text.startswith(current['cycle'] + '导航测距，'):
            uncertainty = re.search(r'触发误差界u=([\d.]+)\+([\d.]+)a毫秒', text)
            delays = re.search(r'名义B\+(\d+(?:/\d+)*)毫秒', text)
            if uncertainty and delays:
                protocol = {'base_uncertainty_us':int(Decimal(uncertainty[1]) * 1000),
                            'aging_us_per_s':int(Decimal(uncertainty[2]) * 1000),
                            'delays_ms':list(map(int, delays[1].split('/')))}
    if set(calibrated) != set(current['timers']) or permission is None or protocol is None:
        raise ValueError('Missing actual channel calibration, exact permission or uncertainty model')
    valid = []
    for timer in current['timers']:
        uncertainty = protocol['base_uncertainty_us']+protocol['aging_us_per_s']*(current['time_s']-calibrated[timer])
        for delay in protocol['delays_ms']:
            nominal = current['base_us']+delay*1000
            if nominal-uncertainty >= permission['start_us'] and nominal+uncertainty < permission['end_us']:
                valid.append(_operation(timer,delay))
    return {'calibrated_s':calibrated,'permission':permission,'valid_operations':valid}


def next_action(facts,current):
    return decision_command(current,facts['valid_operations'][0] if facts['valid_operations'] else _operation())


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('calibrated_s','permission','valid_operations')):
        raise ValueError('Trigger guarantee differs from exact closed envelope and half-open permission')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['valid_operations']))
