"""FM-R1-D3: real framed batches, padded blocks, and complete receiver receipts."""
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, task_shell
from ..prose import paragraphs

PARTITIONS = ('ABC','AB|C','AC|B','BC|A','A|B|C')
COEFFICIENTS = (((2,2),(12,6)),((14,4),(1,3)),((1,12),(21,1)),((18,1),(1,11)))
CONFIGS = (
    (0,(1,1,2)),(2,(4,1,2)),(0,(4,4,1)),(0,(6,4,1)),(1,(4,6,1)),(3,(4,1,6)),
    (1,(2,7,2)),(3,(5,5,3)),(1,(5,3,5)),(2,(6,2,6)),(2,(6,3,6)),(3,(6,6,3)),
    (3,(5,5,6)),(0,(3,7,6)),(1,(8,1,1)),(2,(1,8,1)),
)
PROTOCOL = (
    '三份报文均已就绪、尚未发送，目标是完整交付并合理用电。两种模式X/Y同样无损可靠，保留全部内容和边界；'
    '链路稳定、当前许可有效，整个作业无重传随机性，也无旧确认、清理或唯一副本删除要求。'
    '1KiB=1024字节，每组最多8KiB净载荷，每块容纳4KiB，尾块填充至4KiB，块数q=ceil(组内净KiB/4)。'
    '每组单独封装、发射并等待完整确认，实际费用为a_mode+b_mode×q，a/b为同设备稳定正值。'
    'a包含该帧前导码、头部和确认等固定开销，不额外重复计首包；每帧完成后自动关机回待机，保持供电也不能免去下一帧固定开销。'
    '分组串仅可为ABC、AB|C、AC|B、BC|A或A|B|C；组内按字母封装，组间按最小报文字母排序，BC|A实际先A后BC，AC|B先AC后B。'
    'send(mode,partition)执行完整整单，全部十程序始终可选。开始前检查整单容量，任一组超过8KiB则整单拒绝、不扣电，且本次业务结束。'
    '容量合法时逐组扣费，足额才发送并完整确认后进入下一组；等额可完成并确认，不足耗尽到0、该组未完整确认，保留此前确认并结束。'
    '只有三份全部确认才完成本任务；不能免费试传、补能、补选、撤销或重试。'
    '严格使用actions参数，另有end退出；合法、非法和end合计最多3次调用，格式错误不改变物理状态，首个有效整单或end即结束。'
)


def partition_groups(partition,messages):
    groups = []
    for identifiers in sorted(partition.split('|')):
        net = sum(messages[identifier] for identifier in identifiers)
        groups.append({'messages':list(identifiers),'net_kib':net,'blocks':(net+3)//4})
    return groups


def program_costs(messages,coefficients):
    costs = {mode:{} for mode in 'XY'}
    for partition in PARTITIONS:
        groups = partition_groups(partition,messages)
        if any(g['net_kib'] > 8 for g in groups):
            continue
        for mode,c in coefficients.items():
            costs[mode][partition] = sum(c['fixed']+c['per_block']*g['blocks'] for g in groups)
    return costs


def build(index):
    group,lengths = CONFIGS[index]
    coefficients = {mode:{'fixed':a,'per_block':b} for mode,(a,b) in zip('XY',COEFFICIENTS[group],strict=True)}
    messages = dict(zip('ABC',lengths,strict=True))
    history = History()
    history.add(1,'完整交付三份报文并合理用电。'+PROTOCOL,event='batch_send_protocol',
        partitions=list(PARTITIONS),modes=['X','Y'],buffer_kib=8,block_kib=4,max_actions=3)
    history.add(2,'历史连续标定从电量500开始，容量600，每次单独发一组；每组完整确认后实际关机，下次从关机状态启动。'
        '电量连续接续上批结束读数。若有补能，在完整接收确认后执行，报告的结束电量含该次补能；下一启动接续补后电量。'
        '历史报文H01—H08独立归档，与当前A/B/C不同，历史确认不算当前交付；当前不可使用标定充电资源。',
        event='batch_send_calibration_start',battery=500,capacity=600,transmitter_on=False)
    trials = (('X',3),('X',5),('Y',4),('Y',8),('Y',6),('X',1),('X',7),('Y',2))
    battery = 500
    for j,(mode,net) in enumerate(trials,1):
        blocks = (net+3)//4
        c = coefficients[mode]
        cost = c['fixed']+c['per_block']*blocks
        before = battery
        recharge = (10 if j == 4 else 6 if j == 7 else 0) if index >= 12 else 0
        battery = before-cost+recharge
        info = {'journey':f'J{j:02d}','mode':mode,'message_id':f'H{j:02d}','net_kib':net,'blocks':blocks}
        if index >= 12:
            history.add(j+2,f'J{j:02d}：发射机此前已关机，当前电量{before}，启动模式{mode}，准备发H{j:02d}，净{net}KiB、填充{blocks}块。',
                event='batch_send_trial_start',**info,battery_before=before,transmitter_was_off=True)
        facts = {'energy_used':cost} if index < 6 else {'battery_after':battery,'recharge':recharge}
        if 6 <= index < 12:
            facts['battery_before'] = before
        text = f'J{j:02d}模式{mode}已实际发出H{j:02d}，净{net}KiB、填充{blocks}块；接收端完整确认，发射机已关机。'
        if index < 6:
            text += f'实际耗电{cost}。'
        else:
            if index < 12:
                text += f'启动电量{before}。'
            text += f'完整确认后补能{recharge}，结束读数{battery}。'
        history.add(j+2+int(index >= 12),text,event='batch_send_trial_receipt',**info,
            sent=True,fully_acknowledged=True,transmitter_on=False,**facts)
    history.add(30,'当前新批A/B/C均未发送，电量100，发射机关闭。',event='batch_send_new_batch',
        messages_kib=messages,battery=100,acknowledged={p:False for p in 'ABC'},transmitter_on=False)
    task = task_shell('FM-R1-D3',index,current_input_group='FM-R1-D3-'+','.join(map(str,lengths)))
    task.public = {'instruction':f'当前电量100，请将A({lengths[0]}KiB)、B({lengths[1]}KiB)、C({lengths[2]}KiB)三份报文完整交付接收端。',
        'time_s':clock('09:00'),'transmission_protocol':PROTOCOL,'messages_kib':messages,'buffer_kib':8,'block_kib':4,'max_steps':3,
        'state_fields':['battery','acknowledged','completed_groups','transmitter_on','delivery_complete'],
        'actions':[{'action':'send','mode':m,'partition':p} for m in 'XY' for p in PARTITIONS]+[{'action':'end','description':'结束本批回传。'}]}
    task.initial = {'battery':100,'acknowledged':{p:False for p in 'ABC'},'completed_groups':0,'transmitter_on':False,
        'delivery_complete':False,'executed_program':None,'operations':[]}
    task.world = {'coefficients':coefficients}
    task.rubric = {'score':'100*minimum_capacity_feasible_energy/actual_energy if all messages fully acknowledged; otherwise 0'}
    return history.finish(task)


class Runtime(TaskRuntime):
    action_contract = ActionContract(('action','mode','partition'))

    def actions(self):
        return [] if self.done else super().actions()

    def observation(self):
        result = super().observation()
        if self.done:
            confirmed = [p for p,v in self.state['acknowledged'].items() if v]
            result['instruction'] = f'本批回传已结束；当前电量{self.state["battery"]}，接收端已完整确认报文{confirmed}。'
        return result

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if (not isinstance(action,dict) or set(action) != {'action','mode','partition'} or action['action'] != 'send'
                or not isinstance(action['mode'],str) or action['mode'] not in ('X','Y')
                or not isinstance(action['partition'],str) or action['partition'] not in PARTITIONS):
            self.invalid()
            return
        mode,partition = action['mode'],action['partition']
        self.state['executed_program'] = {'mode':mode,'partition':partition}
        groups = partition_groups(partition,self.task.public['messages_kib'])
        overflow = [g for g in groups if g['net_kib'] > 8]
        if overflow:
            detail = '；'.join(f'{"".join(g["messages"])}组净{g["net_kib"]}KiB' for g in overflow)
            self.feedback = f'整单容量检查拒绝：{detail}超过8KiB缓冲；尚未发射，电量{self.state["battery"]}，没有新增确认。'
            self.end('capacity_rejected',score=0,full_credit=False)
            return
        c = self.task.world['coefficients'][mode]
        for group in groups:
            self.state['transmitter_on'] = True
            cost = c['fixed']+c['per_block']*group['blocks']
            completed = cost <= self.state['battery']
            used = min(cost,self.state['battery'])
            self.state['battery'] -= used
            if completed:
                for p in group['messages']:
                    self.state['acknowledged'][p] = True
                self.state['completed_groups'] += 1
            self.state['transmitter_on'] = False
            self.state['operations'].append({'mode':mode,**group,'fully_acknowledged':completed,'energy_used':used,
                'battery_after':self.state['battery'],'transmitter_on':False})
            status = '已发送，接收端完整确认' if completed else '能源耗尽，未取得完整确认'
            self.feedback += (f'模式{mode}，报文{"".join(group["messages"])}组，净{group["net_kib"]}KiB、填充{group["blocks"]}块，'
                f'{status}；电量{self.state["battery"]}，发射机关闭。')
            if not completed:
                self.end('insufficient_energy',score=0,full_credit=False)
                return
        self.state['delivery_complete'] = True
        energy = 100-self.state['battery']
        costs = program_costs(self.task.public['messages_kib'],self.task.world['coefficients'])
        minimum = min(cost for programs in costs.values() for cost in programs.values())
        self.facts = {'mode':mode,'partition':partition,'actual_energy':energy,'minimum_safe_energy':minimum}
        self.end('completed',score=100*minimum/energy,full_credit=minimum == energy)


def reconstruct(history,current):
    starts,measurements = {},{(m,q):[] for m in 'XY' for q in (1,2)}
    for text in paragraphs(history):
        start = re.fullmatch(r'(J\d+)：发射机此前已关机，当前电量(\d+)，启动模式([XY])，准备发(H\d+)，净(\d+)KiB、填充(\d+)块。',text)
        if start:
            starts[start[1]] = ((start[3],start[4],int(start[5]),int(start[6])),int(start[2]))
            continue
        receipt = re.fullmatch(r'(J\d+)模式([XY])已实际发出(H\d+)，净(\d+)KiB、填充(\d+)块；'
                               r'接收端完整确认，发射机已关机。(.+)',text)
        if not receipt:
            continue
        journey,mode,message,printed_net,printed_blocks,reading = receipt.groups()
        net,blocks = int(printed_net),int(printed_blocks)
        if not 0 < net <= current['buffer_kib'] or blocks != (net+current['block_kib']-1)//current['block_kib']:
            raise ValueError('Historical frame blocks must follow actual net length and the public padding rule')
        direct = re.fullmatch(r'实际耗电(\d+)。',reading)
        difference = re.fullmatch(r'(?:启动电量(\d+)。)?完整确认后补能(\d+)，结束读数(\d+)。',reading)
        if direct:
            cost = int(direct[1])
        elif difference:
            if difference[1] is None:
                identity,before = starts[journey]
                if identity != (mode,message,net,blocks):
                    raise ValueError('Frame receipts must match their own historical send')
            else:
                before = int(difference[1])
            cost = before-int(difference[3])+int(difference[2])
        else:
            raise ValueError('Acknowledged frame calibration requires an actual energy reading')
        measurements[mode,blocks].append(cost)
    if any(len(values) != 2 or len(set(values)) != 1 for values in measurements.values()):
        raise ValueError('Each mode and block count requires two consistent measurements')
    coefficients = {}
    for mode in 'XY':
        first,second = measurements[(mode,1)][0],measurements[(mode,2)][0]
        coefficients[mode] = {'fixed':2*first-second,'per_block':second-first}
        if min(coefficients[mode].values()) <= 0:
            raise ValueError('Fixed frame and per-block energy must be positive')
    costs = program_costs(current['messages_kib'],coefficients)
    return {'coefficients':coefficients,'costs':costs,'minimum_safe_energy':min(c for programs in costs.values() for c in programs.values())}


def next_action(facts,current):
    mode,partition = min(((m,p) for m in facts['costs'] for p in facts['costs'][m]),key=lambda pair:facts['costs'][pair[0]][pair[1]])
    return {'action':'send','mode':mode,'partition':partition}


def check_world(task,facts):
    if task.world['coefficients'] != facts['coefficients']:
        raise ValueError('Frame costs must follow the continuous historical measurements')


def audit_cases(task,facts,solution):
    cases = [([{'action':'send','mode':m,'partition':p}],100*facts['minimum_safe_energy']/facts['costs'][m][p]
              if p in facts['costs'][m] else 0) for m in 'XY' for p in PARTITIONS]
    return cases+[([{}]*3,0),([{},{}]+solution,100)]
