"""FM-C1-O3: persistent per-segment quantity and gas-handling permissions."""
import re

from ..common import History, clock, difficulty, ordered_options, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

CONFIGS = (
    ((2,2,2,2),'KVVK',24), ((7,7,7,7),'VKKV',72),
    ((1,2,3,4),'KKKK',30), ((8,7,6,5),'VVVV',67),
    ((1,8,1,8),'KVVK',44), ((8,1,8,1),'VKKV',44),
    ((2,5,7,4),'KVKV',50), ((7,4,2,5),'VKVK',50),
    ((4,8,2,6),'KVVK',53), ((2,6,4,8),'VKKV',53),
    ((6,1,4,7),'KVKK',49), ((4,7,6,1),'VKVV',49),
    ((2,8,5,1),'KVVK',42), ((5,1,2,8),'VKKV',42),
    ((1,5,8,2),'KKKV',42), ((8,2,1,5),'VVVK',42),
)
SEQUENCE = tuple({'receiver':f'R{i}','segment':segment,'request_l':quantity}
                 for segment,quantity in (('A',9),('B',4),('C',7)) for i in range(1,5))
GAS_NAMES = {'K':'闭路回收','V':'送到许可的外部收集罐'}
OPERATIONS = tuple({'volume_l':quantity,'gas':gas,
                    'description':f'注入{quantity} L，气体{GAS_NAMES[gas]}。' if quantity else
                                  f'不注入（0 L），保留气体{GAS_NAMES[gas]}选项但不产生气流。'}
                   for quantity in range(10) for gas in ('K','V'))


def _requirements(history,at,target,batch,entries):
    def label(values):
        return '、'.join(f'单段许可上限{v} L' if k == 'limit_l' else f'气体{GAS_NAMES[v]}' for k,v in values.items())
    history.add(at,f'目标{target}批次{batch}本批持续许可：' + '；'.join(f'{r}：{label(v)}' for r,v in entries.items()),
                event='supply_permission',target=target,batch=batch,requirements=entries)


def build(index):
    caps,gases,denominator = CONFIGS[index]
    level = difficulty(index)
    requirements = {f'R{i+1}':{'limit_l':caps[i],'gas':gases[i]} for i in range(4)}
    history = History()
    history.add(1,'目标T8的B8批次按R1—R4处理A段，再同序B段、C段，段请求量依次9/4/7 L。'
                '每单元的单段批准上限和气体方式本批始终有效，不是累计容量；调度需量不扩大许可。'
                '在不超过单段批准上限且不超过当前请求量的条件下尽量供给，正确气体方式下按实际有效体积验收；'
                '过量或错误气体方式则该段无验收量，不影响其他段。每段独立验收，未完成无收益。'
                '液路流量预置，整数升；0 L不注入、不产生气流或收益但仍推进。每段最多3次提交，第三次格式错误跳段，'
                '有效动作即推进且不能返工；总最多36次提交，可提前结束。',
                event='supply_assignment',target='T8',batch='B8',sequence=list(SEQUENCE))
    history.add(2,'四接口对接与隔离检查完成，每单元容量40 L、初始为空；供给罐有120 L，每段注入0—9 L。'
                '所有实际注入等量减少供给罐并进入当前接收单元；每段后预置均压，容量保证每次不少于9 L空间。'
                'K为闭路回收，V为送到许可的外部收集罐，两者设备均正常。',
                event='supply_equipment',source_l=120,receiver_capacity_l=40,operations=list(OPERATIONS))
    if level == 'easy':
        layout = ((4,('limit_l',),'1234'),(17,('gas',),'1234'))
    elif level == 'medium':
        layout = ((3,('limit_l',),'13'),(9,('gas',),'24'),(15,('limit_l',),'24'),(22,('gas',),'13'))
    else:
        layout = ((3,('limit_l',),'2'),(3,('gas',),'4'),(7,('gas',),'1'),(7,('limit_l',),'3'),
                  (11,('limit_l',),'4'),(11,('gas',),'2'),(19,('limit_l',),'1'),(19,('gas',),'3'))
    for at,fields,receivers in layout:
        _requirements(history,at,'T8','B8',{f'R{i}':{field:requirements[f'R{i}'][field] for field in fields} for i in receivers})
    if level == 'hard':
        _requirements(history,25,'T8','B7',{f'R{i}':{'limit_l':9,'gas':'K'} for i in range(1,5)})
        _requirements(history,28,'X8','B8',{f'R{i}':{'limit_l':1,'gas':'V'} for i in range(1,5)})
    history.add(30,'四接口准备完成，地面链路中断，目标T8的B8批次本轮补给尚未开始。',
                event='supply_ready',target='T8',batch='B8')
    task = task_shell('FM-C1-O3',index,background_group=f'FM-C1-O3-{level}',current_input_group='FM-C1-O3')
    task.public = {'time_s':clock('09:00'),'target':'T8','batch':'B8','max_steps':36,
                   'instruction':'继续完成本目标B8补给。接口已就绪，请选择本段操作。','sequence':list(SEQUENCE),
                   'options_by_step':[ordered_options(OPERATIONS,'FM-C1-O3',step=i) for i in range(12)]}
    task.initial = {'index':0,'executed':0,'format_attempts':0,'source_l':120,
                    'receivers_l':{r:0 for r in requirements},'accepted_l':0}
    task.world = {'requirements':requirements}
    task.rubric = {'maximum_volume_l':denominator,'score':'100 * accepted_l / maximum_volume_l'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        item = self.task.public['sequence'][at] if at < 12 else {'receiver':None,'segment':None,'request_l':None}
        return {**item,'source_l':self.state['source_l'],'receivers_l':dict(self.state['receivers_l']),
                'receiver_free_l':40-self.state['receivers_l'][item['receiver']] if at < 12 else None,
                'remaining_format_submissions':3-self.state['format_attempts']}

    def operate(self,option,index):
        item = self.task.public['sequence'][index]
        r,quantity = item['receiver'], option['volume_l']
        required = self.task.world['requirements'][r]
        self.state['source_l'] -= quantity
        self.state['receivers_l'][r] += quantity
        if quantity <= min(item['request_l'],required['limit_l']) and option['gas'] == required['gas']:
            self.state['accepted_l'] += quantity
        self.score = 100 * self.state['accepted_l'] / self.task.rubric['maximum_volume_l']
        self.feedback = f"{r}第{item['segment']}段实际注入{quantity} L，" + (
            f"气体{GAS_NAMES[option['gas']]}。" if quantity else '未产生气流。') + '处理记录已保存。'


def reconstruct(history,current):
    requirements = {}
    for text in paragraphs(history):
        header = re.fullmatch(r'目标([A-Z]\d+)批次(B\d+)本批持续许可：(.*)',text)
        if header is None or (header[1],header[2]) != (current['target'],current['batch']):
            continue
        for item in header[3].split('；'):
            requirement = re.fullmatch(r'(R\d+)：(.*)',item)
            if requirement is None:
                raise ValueError('Missing public supply receiver identity')
            row = requirements.setdefault(requirement[1],{})
            for label in requirement[2].split('、'):
                limit = re.fullmatch(r'单段许可上限(\d+) L',label)
                if limit:
                    field,value = 'limit_l',int(limit[1])
                elif label in ('气体闭路回收','气体送到许可的外部收集罐'):
                    field,value = 'gas',{'气体闭路回收':'K','气体送到许可的外部收集罐':'V'}[label]
                else:
                    raise ValueError('Incomplete public supply permission')
                if field in row and row[field] != value:
                    raise ValueError('Conflicting persistent supply permissions')
                row[field] = value
    if any(set(requirements.get(row['receiver'],{})) != {'limit_l','gas'} for row in current['sequence']):
        raise ValueError('Incomplete supply permissions')
    maximum = sum(min(row['request_l'],requirements[row['receiver']]['limit_l']) for row in current['sequence'])
    return {'requirements':requirements,'maximum_volume_l':maximum}


def next_action(facts,current):
    item = current['state']
    required = facts['requirements'][item['receiver']]
    quantity = min(item['request_l'],required['limit_l'])
    return next(row['arguments'] for row in current['actions']
                if row.get('details',{}).get('volume_l') == quantity and row['details']['gas'] == required['gas'])


def check_world(task,facts):
    if facts['requirements'] != task.world['requirements'] or facts['maximum_volume_l'] != task.rubric['maximum_volume_l']:
        raise ValueError('Supply scoring requirements differ from public instructions')


def audit_cases(task,facts,solution):
    denominator = facts['maximum_volume_l']
    first_k = facts['requirements']['R1']['limit_l']
    cases = [([{}]*36,0),([{}]*3+solution[1:],100*(denominator-first_k)/denominator)]
    for at,item in enumerate(task.public['sequence']):
        required = facts['requirements'][item['receiver']]
        k = min(item['request_l'],required['limit_l'])
        for quantity,gas,loss in ((k-1,required['gas'],1),(k+1,required['gas'],k),
                                  (k,'V' if required['gas'] == 'K' else 'K',k)):
            chosen = next(o for o in task.public['options_by_step'][at] if o['volume_l'] == quantity and o['gas'] == gas)
            cases.append((solution[:at]+[{'action':'select','option':chosen['option']}]+solution[at+1:],
                          100*(denominator-loss)/denominator))
    return cases
