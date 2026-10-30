"""FM-E1-D3: retrieve cumulative useful-byte curves without inventing intermediate rates."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

MIB = 1048576
CURVES = ((4,8,12),(3,9,15),(0,6,18))
# Four condition triplets and archive order. Triplet roles never enter public input.
BOOKS = (
    (((9,3,7),(5,2,11),(1,8,4),(12,6,10)),(3,1,4,2)),
    (((2,10,6),(8,1,12),(4,9,3),(7,11,5)),(2,4,1,3)),
    (((11,4,8),(2,7,10),(6,12,1),(9,5,3)),(4,2,3,1)),
    (((6,1,12),(10,3,8),(5,11,7),(4,2,9)),(1,3,2,4)),
    (((3,8,5),(12,6,2),(9,4,10),(1,7,11)),(2,1,4,3)),
    (((10,5,2),(4,12,7),(8,3,11),(6,9,1)),(4,3,1,2)),
    (((7,11,4),(1,9,6),(12,2,8),(3,10,5)),(3,4,2,1)),
    (((5,2,9),(11,8,3),(7,1,6),(10,4,12)),(1,2,4,3)),
)
CONDITIONS = (('E','I'),('E','S'),('B','I'),('B','S'))
# Book, actual environment/product, minutes, demanded MiB, frequent/latest program, actual three deliveries.
CONFIGS = (
    (1,'E','I',2,4,9,9,(4,3,0)),(1,'E','I',6,18,3,5,(12,15,18)),
    (1,'B','S',2,3,11,6,(3,3,0)),(2,'B','I',6,15,9,3,(12,15,15)),
    (2,'E','S',4,8,12,10,(8,8,6)),(3,'E','I',6,12,11,4,(12,12,12)),
    (4,'B','S',4,9,2,2,(8,9,6)),(4,'B','I',2,3,5,11,(3,3,0)),
    (4,'E','I',6,18,2,12,(12,15,18)),(5,'E','I',4,8,3,8,(8,8,6)),
    (5,'B','S',2,4,1,7,(4,3,0)),(6,'B','I',6,12,8,11,(12,12,12)),
    (7,'B','S',6,18,10,4,(12,15,18)),(7,'E','I',4,9,11,7,(8,9,6)),
    (7,'B','I',6,15,3,8,(12,15,15)),(8,'B','S',4,8,12,7,(8,8,6)),
)


def _program(number):
    return f'P{number:02d}'


def _condition(environment,product):
    return {'environment':{'E':'均匀弱闪烁','B':'成簇闪烁'}[environment],'product_type':{'I':'图像','S':'谱列'}[product]}


def _key(condition):
    return condition['environment'],condition['product_type']


def build(index):
    book,environment,product,minutes,demand,frequent,recent,deliveries = CONFIGS[index]
    programs,archive = BOOKS[book-1]
    history = History()
    history.add(1,'链路环境由传感器判为均匀弱闪烁或成簇闪烁，产品由预处理标为图像或谱列；本次联系内工况保持不变。'
                '设备和接收站固定健康，缓存、能源、指向和初始化充分。P01—P12为已存储完整回传程序，编号无优劣含义。'
                '相同完整工况和程序从重置开始的累计有效接收曲线稳定，2/4/6分钟点都已实测，不外推其他时长，不相加累计点。'
                '历史源产品24MiB，不因提前完成截断。1MiB=1048576字节，只计唯一有效载荷，不计头部、冗余或重发。'
                '当前达到目标D后不再新增接收，余时空闲，联系结束才终止题目；源完整副本始终保留，不删除、不拼接或改选程序。'
                '所有十二程序可执行，错误也实际尝试；有效无效共3次，首合法选择固定全程，end放弃。推理与记忆检索不消耗动作或故事时间。',
                event='downlink_experience_protocol')
    history.add(2,'接收站固定为G，标准试传产品载荷为24MiB，每次重新初始化发送程序、接收累计计数与标准产品。',
                event='downlink_trial_setup',station='G',source_payload_mib=24)
    tables = []
    layout = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'
    for at,number,job in zip((5,10,15,20),archive,('Z18','Z05','Z27','Z11'),strict=True):
        slot = number-1
        condition = _condition(*CONDITIONS[slot])
        mapping = dict(zip(programs[slot],CURVES,strict=True))
        results = [{'program':_program(p),'cumulative_mib':list(mapping.get(p,(0,0,0)))} for p in range(1,13)]
        tables.append({'condition':condition,'results':results})
        start = clock('06:00',119)+slot*72*60
        finish = start+72*60
        first = {'job':job,'condition':condition,'batch_started_s':start}
        result = {'job':job,'minutes':[2,4,6],'results':results,'source_payload_mib':24,
                  'batch_started_s':start,'batch_finished_s':finish,'trial_seconds':360,'order':'按P01—P12依次独立重置并运行六分钟，三点为起点+2/+4/+6分钟累计量'}
        measured = '；'.join(f'{row["program"]}：'+ '、'.join(str(v) for v in row['cumulative_mib']) for row in results)
        text = f'{job}：十二程序在2、4、6分钟的实测累计有效量依次为（MiB，包含三点全0）：{measured}。'
        text += f'各程序以24MiB产品独立重置、六分钟一项，{story_timestamp(start)}开始至{story_timestamp(finish)}完成，'
        text += '按P01—P12顺序，不能把累计点相加。'
        if layout == 'combined':
            history.add(at,'、'.join(condition.values())+'；'+text,occurred=finish,event='downlink_trial_batch',
                        **first,**{k:v for k,v in result.items() if k not in first})
        else:
            history.add(at-1 if layout == 'previous_round' else at,f'{job}：已完成试验的工况为'+ '、'.join(condition.values())+'。',
                        occurred=start,event='downlink_batch_condition',**first)
            history.add(at,text,occurred=finish,event='downlink_batch_results',**result)
    for position,(at,preset,job) in enumerate(zip((22,24,26,29),(frequent,frequent,frequent,recent),('J41','J36','J43','J38'),strict=True)):
        slot,role = next((s,r) for s,row in enumerate(programs) for r,p in enumerate(row) if p == preset)
        condition = _condition(*CONDITIONS[slot])
        start = clock('12:00',119)+position*720
        curve = list(CURVES[role])
        history.add(at,f'{job}：'+ '、'.join(condition.values())+f'，{_program(preset)}以24MiB产品独立重置试传，'
                    f'{story_timestamp(start)}开始至{story_timestamp(start+360)}结束；2/4/6分钟累计量分别'+ '、'.join(map(str,curve))+'MiB。',
                    occurred=start+360,event='downlink_trial',job=job,condition=condition,program=_program(preset),source_payload_mib=24,
                    minutes=[2,4,6],cumulative_mib=curve,started_s=start,finished_s=start+360)
    history.add(30,'本次待传产品已完整进入星上缓存，等待联系开始后执行回传。',event='downlink_product_ready')
    current = _condition(environment,product)
    selected = next(row['results'] for row in tables if row['condition'] == current)
    current_curves = {r['program']:r['cumulative_mib'] for r in selected}
    slot = CONDITIONS.index((environment,product))
    amounts = {_program(p):0 for p in range(1,13)}
    amounts.update({_program(p):amount*MIB for p,amount in zip(programs[slot],deliveries,strict=True)})
    task = task_shell('FM-E1-D3',index)
    task.public = {'time_s':clock('09:00'),'station':'G','condition':current,'contact_minutes':minutes,'requested_mib':demand,
                   'source_copy_complete':True,'receiver_unique_bytes':0,'equipment_ready':True,'max_steps':3,'state_fields':[],
                   'instruction':'第120日09:00，当前'+ '、'.join(current.values())+f'，本次联系已生效，可用{minutes}分钟；'
                   f'须向G回传{demand}MiB有效载荷，星上完整副本尚在，接收端本次已验收0。完成本次数据回传。',
                   'actions':fixed_options([{'operation':{'program':_program(p)},'description':f'用{_program(p)}回传当前产品，持续本次{minutes}分钟或直到目标完成，随后空闲至联系结束。'} for p in range(1,13)])}
    task.initial = {'time_s':clock('09:00'),'source_copy_bytes':demand*MIB,'receiver_unique_bytes':0,'transmissions':[]}
    task.world = {'tables':sorted(tables,key=lambda r:_key(r['condition'])),'curves':current_curves,'delivered_bytes':amounts}
    task.rubric = {'score':'100 times unique useful bytes received, capped at the current product size, divided by the fixed demanded bytes'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        program,start = operation['program'],self.state['time_s']
        target = self.task.public['requested_mib']*MIB
        checkpoints = []
        for minutes,amount in zip((2,4,6),self.task.world['curves'][program],strict=True):
            if minutes <= self.task.public['contact_minutes']:
                self.state['receiver_unique_bytes'] = min(target,amount*MIB)
                checkpoints.append({'time_s':start+minutes*60,'cumulative_unique_bytes':self.state['receiver_unique_bytes']})
        self.state['time_s'] += self.task.public['contact_minutes']*60
        self.state['transmissions'].append({'program':program,'started_s':start,'finished_s':self.state['time_s'],
                                           'checkpoints':checkpoints,'target_reached':self.state['receiver_unique_bytes'] == target})
        self.feedback = '操作已执行，记录已存档。'
        return 100*self.state['receiver_unique_bytes']/target


def reconstruct(history,current):
    conditions,results,repeats = {},{},[]
    for text in paragraphs(history):
        batch = re.search(r'(Z\d+)：',text)
        if batch:
            job = batch[1]
            condition = re.search(r'(均匀弱闪烁|成簇闪烁)、(图像|谱列)',text)
            if condition:
                conditions[job] = {'environment':condition[1],'product_type':condition[2]}
            measured = re.search(r'十二程序在([\d、]+)分钟的实测累计有效量依次为（MiB，包含三点全0）：(.+?)。各程序以(\d+)MiB产品独立重置',text)
            if measured:
                rows = []
                for entry in measured[2].split('；'):
                    program,values = entry.split('：')
                    rows.append({'program':program,'cumulative_mib':list(map(int,values.split('、')))})
                if [r['program'] for r in rows] != [_program(p) for p in range(1,13)]:
                    raise ValueError('Downlink prose must contain each measured program including zero outcomes')
                results[job] = {'minutes':list(map(int,measured[1].split('、'))),'source_payload_mib':int(measured[3]),'results':rows}
        repeat = re.fullmatch(rf'J\d+：(均匀弱闪烁|成簇闪烁)、(图像|谱列)，(P\d+)以24MiB产品独立重置试传，'
                              rf'{STORY_STAMP}开始至{STORY_STAMP}结束；2/4/6分钟累计量分别([\d、]+)MiB。',text)
        if repeat:
            repeats.append({'condition':{'environment':repeat[1],'product_type':repeat[2]},'program':repeat[3],
                            'cumulative_mib':list(map(int,repeat[4].split('、')))})
    if conditions.keys() != results.keys():
        raise ValueError('Downlink jobs must join complete link/product conditions and cumulative trial results')
    tables,lookup = [],{}
    for job,result in results.items():
        if result['minutes'] != [2,4,6] or result['source_payload_mib'] != 24:
            raise ValueError('Curves must contain actual independent-trial cumulative 2/4/6-minute observations')
        tables.append({'condition':conditions[job],'results':result['results']})
        for row in result['results']:
            curve = row['cumulative_mib']
            if curve != sorted(curve) or not 0 <= curve[0] <= curve[-1] <= 24:
                raise ValueError('Useful cumulative reception cannot decrease or exceed the standard product')
            lookup[(*_key(conditions[job]),row['program'])] = curve
    for r in repeats:
        if lookup[(*_key(r['condition']),r['program'])] != r['cumulative_mib']:
            raise ValueError('Repeated fixed-condition trial changed its stable cumulative curve')
    curves = {_program(p):lookup[(*_key(current['condition']),_program(p))] for p in range(1,13)}
    at = (2,4,6).index(current['contact_minutes'])
    amounts = {p:min(current['requested_mib'],curve[at])*MIB for p,curve in curves.items()}
    return {'tables':sorted(tables,key=lambda r:_key(r['condition'])),'curves':curves,'delivered_bytes':amounts}


def next_action(facts,current):
    program = next(p for p,amount in facts['delivered_bytes'].items() if amount == current['requested_mib']*MIB)
    return decision_command(current,{'program':program})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Downlink selection must use the correct measured time point capped at the current target')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*facts['delivered_bytes'][op['program']]/(task.public['requested_mib']*MIB))
