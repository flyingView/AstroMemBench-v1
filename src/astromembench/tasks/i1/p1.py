"""FM-I1-P1: detach a requested sensor while preserving its nested carrier deployment."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

# Target head, explicit left menu rotation, native history events.
CONFIGS = (
    ('H1',4,((8,'M1C'),(18,'M1A'),(25,'P:M1C'))),
    ('H2',9,((8,'M1C'),(25,'P:M2A'))),
    ('H1',11,((12,'X'),(26,'P:X'))),
    ('H2',3,((12,'X'),(26,'P:M1C'))),
    ('H1',8,((7,'M1C'),(17,'M2A'),(27,'P:M1B'))),
    ('H2',2,((8,'M2C'),(18,'M1B'),(26,'P:X'))),
    ('H2',8,((6,'M1C'),(15,'X'),(22,'M1A'),(26,'P:X'))),
    ('H1',5,((6,'X'),(16,'M2C'),(22,'M2B'),(27,'P:M2C'))),
    ('H1',3,((5,'X'),(13,'M1C'),(22,'X'),(27,'P:M2A'))),
    ('H2',9,((5,'X'),(13,'M2C'),(22,'X'),(27,'P:M1B'))),
    ('H1',1,((5,'M1C'),(11,'M2A'),(18,'X'),(25,'M1B'))),
    ('H2',6,((5,'M2C'),(11,'M1B'),(18,'X'),(25,'M2A'))),
    ('H2',1,((5,'M1C'),(13,'F:M2C'),(23,'X'))),
    ('H1',9,((5,'M2C'),(12,'F:X'),(23,'M1B'))),
    ('H1',0,((5,'X'),(13,'W:M2C'),(18,'M1B'),(21,'M2A'),(24,'F:X'))),
    ('H2',6,((5,'M1C'),(10,'F:X'),(17,'X'),(25,'M2A'))),
)


def build(index):
    target,rotation,events = CONFIGS[index]
    history = History()
    carriers,heads = {'S1':'A','S2':'B'},{'H1':'S1','H2':'S2'}
    history.add(1,'勘察测头H1/H2各重1个标准载荷单位，载架S1/S2各装一个测头，基座A/B/C各最多停一个载架。'
        '每个头只装一个架；移动载架时它当前装着的测头随架移动，不留在旧座，目的座须空。'
        '双夹持交换同时抓住两头，再解除、交换、重新锁紧；成功互换两头的载架，基座不变；失败则两头保持原架，无半完成。'
        '失败、被占拒绝及未执行计划不改变关系；带警告但已实际到位的移动仍改变架位。'
        '当前只在基座处取下指定测头，保留另一头及两个载架部署；取下会由公共夹持托位承接测头并解除头—架连接。'
        '错座时按对象身份拒绝，不误抓另一头。整体收架会把架及其装接测头一起移入回收舱，头仍装架，不等于取下头。'
        '低层抓持、锁紧、转移均已校准，三个基座可达，不比较路程和能耗；本次不需回收整架。'
        '所有12项选择保持可选；有效、无效及end总计最多3次，首个有效选择立即执行并终止，不能试错后重选。'
        '按select/字符串option提交，end放弃；其他字段或数值型/范围外编号无效且不动设备。',event='nested_recovery_protocol')
    history.add(2,'初始装接：H1装在S1，H2装在S2；S1停A，S2停B，C空。',event='nested_initial',
                carrier_locations=carriers,head_mounts=heads)
    for at,code in events:
        status,operation = code.split(':',1) if ':' in code else ('success',code)
        if status == 'P':
            plan = {'kind':'swap_heads'} if operation == 'X' else {'kind':'move_carrier','carrier':'S'+operation[1],'to_base':operation[2]}
            description = '双夹持互换两测头' if operation == 'X' else f'把{plan["carrier"]}移到{plan["to_base"]}'
            history.add(at,'提出'+description+'的计划，尚未执行，没有关系变化。',event='nested_plan',planned_operation=plan,executed=False)
        elif operation == 'X':
            if status == 'F':
                history.add(at,'双夹持交换尝试失败，夹持交换未启动，两测头均未交换、仍保持各自原载架，两个架也未动。',
                            event='head_swap',success=False,unchanged=True,reason='gripping_not_started')
            else:
                heads['H1'],heads['H2'] = heads['H2'],heads['H1']
                history.add(at,f'双夹持交换实际成功，已重新锁紧：H1现在装{heads["H1"]}，H2现在装{heads["H2"]}；两个载架基座不变。',
                            event='head_swap',success=True,head_mounts=heads)
        else:
            carrier,destination = 'S'+operation[1],operation[2]
            origin = carriers[carrier]
            occupant = next((s for s,base in carriers.items() if base == destination),None)
            if status == 'F':
                if occupant is None:
                    raise ValueError('Reviewed blocked move requires an actually occupied base')
                history.add(at,f'{carrier}向{destination}移动被拒绝：{destination}被{occupant}占用；{carrier}仍在{origin}，相关架位与装接全部不变。',
                    event='carrier_move',carrier=carrier,from_base=origin,to_base=destination,success=False,
                    unchanged=True,reason='destination_occupied',occupant=occupant)
            else:
                if occupant is not None:
                    raise ValueError('Actual carrier transfer requires an empty destination')
                carriers[carrier] = destination
                warning = status == 'W'
                history.add(at,f'{carrier}'+('移动出现警告，但实际回执确认已完成：' if warning else '移动实际完成：')+
                    f'原基座{origin}已空，{carrier}现停{destination}，它当前装接的测头随架一起到位。',
                    event='carrier_move',carrier=carrier,from_base=origin,to_base=destination,success=True,
                    warning=warning,old_base_empty=True,current_attachment_carried=True)
    history.add(30,'勘察采集已经停止，测头电源关闭，抓取准备满足。',event='head_recovery_ready')
    entries = [{'operation':{'kind':'detach_head','head':head,'base':base},'description':f'在{base}取下{head}。'} for head in ('H1','H2') for base in 'ABC']
    entries += [{'operation':{'kind':'recover_carrier','carrier':carrier,'base':base},'description':f'从{base}整体收回{carrier}。'} for carrier in ('S1','S2') for base in 'ABC']
    task = task_shell('FM-I1-P1',index)
    task.public = {'time_s':clock('09:00'),'target':target,'max_steps':3,'state_fields':[],
        'instruction':f'请在基座处取下测头{target}，保留两个载架及另一测头的部署。',
        'actions':fixed_options(entries[rotation:]+entries[:rotation])}
    task.initial = {'time_s':clock('09:00'),'carrier_locations':carriers,'head_mounts':heads,'gripper_heads':[]}
    task.world = {'carrier_locations':carriers,'head_mounts':heads}
    task.rubric = {'score':'100 only for detaching the specified head at its actual base while preserving deployed carriers and the other head'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        base = operation['base']
        carriers,heads = self.state['carrier_locations'],self.state['head_mounts']
        if operation['kind'] == 'detach_head':
            head = operation['head']
            found = carriers[heads[head]] == base
            if found:
                heads[head] = None
                self.state['gripper_heads'].append(head)
            correct = found and head == self.task.public['target']
        else:
            carrier = operation['carrier']
            found = carriers[carrier] == base
            if found:
                carriers[carrier] = 'recovery_bay'
            correct = False
        self.facts['operation_completed'] = found
        self.feedback = '所选抓取/回收请求已执行并归档。' if found else '指定对象不在所选基座，抓取/回收未发生。'
        return 100 if correct else 0


def reconstruct(history,current):
    carriers,heads = {},{}
    for text in paragraphs(history):
        match = re.fullmatch(r'初始装接：H1装在(S[12])，H2装在(S[12])；S1停([ABC])，S2停([ABC])，([ABC])空。',text)
        if match:
            h1,h2,s1,s2,empty = match.groups()
            carriers,heads = {'S1':s1,'S2':s2},{'H1':h1,'H2':h2}
            if empty in carriers.values():
                raise ValueError('An initially empty base cannot hold a carrier')
            continue
        match = re.fullmatch(r'(S[12])(?:移动实际完成：|移动出现警告，但实际回执确认已完成：)'
            r'原基座([ABC])已空，(S[12])现停([ABC])，它当前装接的测头随架一起到位。',text)
        if match:
            carrier,origin,arrived,destination = match.groups()
            if carriers[carrier] != origin:
                raise ValueError('Movement receipt must depart the actual current base')
            if carrier != arrived or destination in carriers.values():
                raise ValueError('Successful carrier transfer must preserve attachment and base exclusion')
            carriers[carrier] = destination
            continue
        match = re.fullmatch(r'(S[12])向([ABC])移动被拒绝：([ABC])被(S[12])占用；'
            r'(S[12])仍在([ABC])，相关架位与装接全部不变。',text)
        if match:
            carrier,destination,occupied,occupant,unchanged,origin = match.groups()
            if carrier != unchanged or carriers[carrier] != origin:
                raise ValueError('Movement receipt must depart the actual current base')
            if destination != occupied or carriers.get(occupant) != destination:
                raise ValueError('Rejected transfer must preserve the actually occupied destination')
            continue
        match = re.fullmatch(r'双夹持交换实际成功，已重新锁紧：H1现在装(S[12])，H2现在装(S[12])；两个载架基座不变。',text)
        if match:
            reported = {'H1':match[1],'H2':match[2]}
            if reported != {'H1':heads['H2'],'H2':heads['H1']}:
                raise ValueError('Successful swap must exchange exactly both head attachments')
            heads = reported
    if set(carriers) != {'S1','S2'} or len(set(carriers.values())) != 2 or set(heads.values()) != {'S1','S2'}:
        raise ValueError('Historical deployment must have two distinct bases and exactly one head per carrier')
    return {'carrier_locations':carriers,'head_mounts':heads}


def next_action(facts,current):
    head = current['target']
    base = facts['carrier_locations'][facts['head_mounts'][head]]
    return decision_command(current,{'kind':'detach_head','head':head,'base':base})


def check_world(task,facts):
    if facts != task.world or any(task.initial[key] != value for key,value in facts.items()):
        raise ValueError('Actual nested deployment differs from the received physical receipts')


def audit_cases(task,facts,solution):
    target = task.public['target']
    correct = {'kind':'detach_head','head':target,'base':facts['carrier_locations'][facts['head_mounts'][target]]}
    return decision_cases(task,solution,lambda op:100 if op == correct else 0)
