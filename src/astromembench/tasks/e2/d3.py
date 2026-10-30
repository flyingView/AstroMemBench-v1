"""FM-E2-D3: external SNR revisions and actual useful ten-second payload delivery."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

PROGRAMS = (
    {'program':'X1','band':'X','threshold_db':2,'rate_mbit_s':1},
    {'program':'X2','band':'X','threshold_db':4,'rate_mbit_s':2},
    {'program':'X3','band':'X','threshold_db':6,'rate_mbit_s':4},
    {'program':'X4','band':'X','threshold_db':8,'rate_mbit_s':6},
    {'program':'X5','band':'X','threshold_db':10,'rate_mbit_s':8},
    {'program':'Y1','band':'Y','threshold_db':1,'rate_mbit_s':1},
    {'program':'Y2','band':'Y','threshold_db':3,'rate_mbit_s':3},
    {'program':'Y3','band':'Y','threshold_db':5,'rate_mbit_s':5},
    {'program':'Y4','band':'Y','threshold_db':7,'rate_mbit_s':7},
    {'program':'Y5','band':'Y','threshold_db':9,'rate_mbit_s':9},
)
# Initial X/Y, old program, actual U/V, final X/Y.
CONFIGS = (
    ((4,6),'Y3',(('Y',2),),(('Y',6),),(4,6)),
    ((2,8),'Y4',(('X',10),),(('Y',4),),(10,4)),
    ((9,1),'X4',(('X',3),),(('Y',3),),(3,3)),
    ((3,5),'Y3',(('Y',1),),(('X',2),),(2,1)),
    ((10,8),'X5',(('X',9),),(('Y',7),),(9,7)),
    ((5,3),'Y2',(('X',6),),(('Y',4),),(6,4)),
    ((6,7),'Y4',(('X',10),('Y',8)),(('Y',6),),(10,6)),
    ((3,9),'Y5',(('Y',4),('X',4)),(('Y',9),),(4,9)),
    ((4,5),'Y3',(('X',8),('Y',7)),(('Y',8),),(8,8)),
    ((9,3),'X4',(('X',10),('Y',5)),(('Y',9),),(10,9)),
    ((2,7),'Y4',(('X',0),('Y',1)),(('X',2),),(2,1)),
    ((7,5),'Y3',(('X',8),('Y',4)),(('Y',6),),(8,6)),
    ((4,9),'Y5',(('X',9),('Y',4)),(('X',4),('Y',9)),(4,9)),
    ((6,5),'Y3',(('X',10),('Y',8)),(('X',9),('Y',8)),(9,8)),
    ((2,1),'X1',(('X',7),('Y',3)),(('X',6),('Y',5)),(6,5)),
    ((1,5),'Y3',(('X',4),('Y',8)),(('X',3),('Y',2)),(3,2)),
)
MODEL = {'duration_s':10,'new_product_mbit':90,'threshold_inclusive':True,'below_threshold_payload_mbit':0,
         'objective':'maximize useful payload delivered relative to the best currently attainable program'}


def build(index):
    initial,old,updates,final_updates,final = CONFIGS[index]
    history,snr = History(),{}

    def add(at,text,**facts):
        history.add(at,text,record_id=f'H-R{at:02d}-{len(history.events[at-1].records)+1:02d}',**facts)

    add(1,'向接收站K回传，X/Y传播路径受外部等离子体扰动影响；J为另一方向，其同名频段互不共享传播条件。'
        '发射机、功放、编解码器、天线与接收站能力固定正常；接收信标实测SNR直接按dB与表列闭门限比较，无需计算对数。'
        '只更新被测方向的指定频段绝对值，未列保持；测量按发生次序同等可信，无未记录变化。'
        '每程序全程固定频段和编码档10秒；SNR≥门限时净有效载荷率为表值，否则有效量0，全部资源足够。'
        '当前90Mbit新产品，目标在本次10秒内尽量多地送达有效载荷，须结合当前信噪比和各程序门限选择。'
        '十程序加保持始终可选；有效/无效/end合计3次，首合法选择即运行完整10秒并终局，失败不重试。'
        '不准实时探测、试发握手、并用频段、分时换档；无删除缓存或补交确认动作，源副本保留。'
        '计划不改变传播场，推理与记忆检索不推进故事时间。',event='adaptive_downlink_protocol',programs=list(PROGRAMS),model=MODEL)
    add(2,'目标接收站K、设备正常。本轮新产品90Mbit全部未发，独立10秒机会已保证有效，旧任务数据不占本轮机会。',
        event='downlink_assignment',station='K',new_product_mbit=90,delivered_mbit=0,equipment_ready=True)

    def measure(at,station,band,value):
        key = (station,band)
        previous = snr.get(key)
        cause = '接收信标初始实测' if previous is None else ('外部等离子体扰动已改变后接收信标实际复测' if previous != value else '接收信标再次实测确认保持')
        add(at,f'{station}-{band}：{cause}，绝对SNR={value}dB。',event='snr_measured',station=station,band=band,
            previous_snr_db=previous,snr_db=value)
        snr[key] = value

    def old_downlink(at,product):
        finish = clock(f'08:{at:02d}')
        program = next(p for p in PROGRAMS if p['program'] == old)
        delivered = 10*program['rate_mbit_s']
        add(at,f'接收站K独立旧产品{product}共90Mbit，{story_timestamp(finish-10)}开始{old}，'
            f'{story_timestamp(finish)}完成10秒发送，接收站已完成有效接收{delivered}Mbit，'
            f'未发{90-delivered}Mbit不再属于后续任务；该旧任务已经结束。',occurred=finish,
            event='old_downlink_completed',station='K',product=product,program=old,started_s=finish-10,finished_s=finish,
            product_mbit=90,received_mbit=delivered,untransmitted_mbit=90-delivered,task_closed=True)

    measure(3,'K','X',initial[0])
    measure(3 if index < 6 else 7,'K','Y',initial[1])
    if index < 6:
        old_downlink(6,'H1')
        old_downlink(9,'H2')
        update_round,plan_round = 14,20
    elif index < 12:
        old_downlink(10,'H1')
        old_downlink(13,'H2')
        update_round,plan_round = 16,21
    else:
        old_downlink(9,'H1')
        for band in ('X','Y'):
            measure(11,'K',band,0)
        for band,value in zip(('X','Y'),initial,strict=True):
            measure(13,'K',band,value)
        old_downlink(15,'H2')
        update_round,plan_round = 18,22
    for band,value in updates:
        measure(update_round,'K',band,value)
    add(plan_round,f'拟请求外部中继调位，使K-X/Y的SNR恢复至{initial[0]}/{initial[1]}dB，尚未执行，未产生传播场复测结果。',
        event='relay_reposition_plan',station='K',planned_snr_db=dict(zip(('X','Y'),initial,strict=True)),implemented=False)
    for band,value in final_updates:
        measure(24,'K',band,value)
    for band,value in zip(('X','Y'),initial,strict=True):
        measure(28,'J',band,value)
    add(30,'接收站K本轮新产品90Mbit与发射程序就绪，等待一次回传。',event='downlink_ready',station='K',new_product_mbit=90)
    task = task_shell('FM-E2-D3',index)
    task.public = {'time_s':clock('09:00'),'station':'K','new_product_mbit':90,'programs':list(PROGRAMS),'downlink_model':MODEL,
        'max_steps':3,'state_fields':[],'instruction':'任务第120日09:00；目标接收站K；新产品90Mbit；10秒回传机会就绪。请执行回传。',
        'actions':fixed_options([{'operation':{'kind':'transmit','program':p['program']},
            'description':f'{p["program"]}：{p["band"]}频段，门限{p["threshold_db"]}dB，达标净载荷率{p["rate_mbit_s"]}Mbit/s，固定10秒。'} for p in PROGRAMS]+
            [{'operation':{'kind':'hold'},'description':'保持，不回传。'}])}
    task.initial = {'time_s':clock('09:00'),'source_copy_mbit':90,'received_mbit':0,'pending_mbit':90,'opportunity_used':False,'attempts':[]}
    task.world = {'snr_db':dict(zip(('X','Y'),final,strict=True))}
    task.rubric = {'score':'100 times actual useful payload divided by the greatest attainable payload in the current ten-second opportunity'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        if operation['kind'] == 'hold':
            self.feedback = '已保持，不回传，操作结束。'
            return 0
        program = next(p for p in self.task.public['programs'] if p['program'] == operation['program'])
        snr = self.task.world['snr_db']
        decoded = snr[program['band']] >= program['threshold_db']
        delivered = 10*program['rate_mbit_s'] if decoded else 0
        best = max(10*p['rate_mbit_s'] for p in self.task.public['programs'] if snr[p['band']] >= p['threshold_db'])
        start = self.state['time_s']
        self.state['attempts'].append({'program':program['program'],'started_s':start,'finished_s':start+10,
            'transmitted_payload_mbit':10*program['rate_mbit_s'],'decodable':decoded,'received_mbit':delivered})
        self.state.update(time_s=start+10,received_mbit=delivered,pending_mbit=90-delivered,opportunity_used=True)
        self.feedback = '已完成所选程序的10秒回传，链路日志已归档。'
        return 100*delivered/best


def reconstruct(history,current):
    snr = {}
    for text in paragraphs(history):
        measurement = re.fullmatch(r'([KJ])-([XY])：(接收信标初始实测|外部等离子体扰动已改变后接收信标实际复测|接收信标再次实测确认保持)，'
                                   r'绝对SNR=(\d+)dB。',text)
        if measurement and measurement[1] == current['station']:
            _,band,cause,printed = measurement.groups()
            value,previous = int(printed),snr.get(band)
            if ((cause == '接收信标初始实测' and previous is not None)
                    or (cause == '接收信标再次实测确认保持' and previous != value)
                    or (cause == '外部等离子体扰动已改变后接收信标实际复测' and (previous is None or previous == value))):
                raise ValueError('SNR updates must preserve the preceding actual value for the same band')
            snr[band] = value
        downlink = re.fullmatch(rf'接收站([KJ])独立旧产品H\d+共90Mbit，{STORY_STAMP}开始([XY][1-5])，'
                                rf'{STORY_STAMP}完成10秒发送，接收站已完成有效接收(\d+)Mbit，'
                                r'未发(\d+)Mbit不再属于后续任务；该旧任务已经结束。',text)
        if downlink and downlink[1] == current['station']:
            program = next(p for p in current['programs'] if p['program'] == downlink[2])
            best = max(p['rate_mbit_s'] for p in current['programs'] if snr[p['band']] >= p['threshold_db'])
            received,remaining = int(downlink[3]),int(downlink[4])
            if (snr[program['band']] < program['threshold_db'] or program['rate_mbit_s'] != best
                    or received != 10*best or remaining != 90-received):
                raise ValueError('Old delivered payload must be attainable and maximal under the then-current measured SNR')
    return {'snr_db':snr}


def next_action(facts,current):
    p = max((p for p in current['programs'] if facts['snr_db'][p['band']] >= p['threshold_db']),key=lambda p:p['rate_mbit_s'])
    return decision_command(current,{'kind':'transmit','program':p['program']})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Current propagation SNR differs from actual local measurements')


def audit_cases(task,facts,solution):
    usable = {p['program']:p['rate_mbit_s'] for p in task.public['programs'] if facts['snr_db'][p['band']] >= p['threshold_db']}
    def score(operation):
        return 0 if operation['kind'] == 'hold' else 100*usable.get(operation['program'],0)/max(usable.values())
    return decision_cases(task,solution,score)
