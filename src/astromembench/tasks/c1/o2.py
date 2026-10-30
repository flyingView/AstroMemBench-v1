"""FM-C1-O2: method-specific repair milestones and material incompatibility."""
from copy import deepcopy
import re

from ..common import History, clock, difficulty, ordered_options, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

CONFIGS = (
    ((1,1,5,9),(2,1,6,10),(3,1,7,11)),
    ((7,5,1,5),(8,5,2,6),(9,5,3,7)),
    ((10,9,9,1),(11,9,10,2),(12,9,11,3)),
    ((4,2,8,12),(5,3,8,12),(6,4,8,12)),
    ((3,1,7,11),(6,5,7,11),(9,9,7,11)),
    ((2,4,10,2),(5,8,10,2),(8,12,10,2)),
    ((2,5,9,4),(8,1,6,11),(11,9,3,7)),
    ((9,2,4,8),(3,10,11,5),(6,6,1,12)),
    ((7,4,12,10),(2,8,5,3),(5,12,8,1)),
    ((3,9,8,7),(11,1,12,4),(4,5,2,10)),
    ((10,3,6,2),(7,11,3,8),(2,7,9,5)),
    ((11,12,7,3),(2,8,10,5),(7,4,4,11)),
    ((4,5,11,8),(9,9,2,3),(1,1,6,12)),
    ((3,3,8,10),(11,7,1,4),(6,11,12,7)),
    ((5,2,9,11),(1,10,6,2),(9,6,3,8)),
    ((2,4,10,12),(8,8,4,6),(4,12,7,9)),
)
STAGES = ('open','clean','insert','fasten')
STAGE_NAMES = dict(zip(STAGES,('开盖','清洁','装入','紧固')))
FIELDS = {'open':('drive','guard','tray'), 'clean':('medium','direction','collect'),
          'insert':('slot','orientation','clamp'), 'fasten':('torque_nm','order','lid')}
OPERATIONS = {
    'open': tuple(dict(zip(FIELDS['open'], values)) for values in (
        ('manual','on',1),('manual','on',2),('manual','on',3),
        ('manual','off',1),('manual','off',2),('manual','off',3),
        ('powered','on',1),('powered','on',2),('powered','on',3),
        ('powered','off',1),('powered','off',2),('powered','off',3))),
    'clean': tuple({'medium':m,'direction':d,'collect':c} for m in ('dry','A','B') for d in ('forward','reverse') for c in (True,False)),
    'insert': tuple({'slot':s,'orientation':o,'clamp':c} for s in (1,2,3) for o in ('forward','reverse') for c in (True,False)),
    'fasten': tuple({'torque_nm':t,'order':o,'lid':lid} for t in (1,2,3) for o in ('cross','sequential') for lid in ('closed','open')),
}
SEQUENCE = tuple({'device':f'J{i}','stage':stage} for stage in STAGES for i in range(1,4))


def _label(field,value):
    labels = {
        'drive':{'manual':'手动驱动','powered':'电动驱动'},'guard':{'on':'安装防护罩','off':'移除防护罩'},
        'medium':{'dry':'干拭','A':'使用A剂','B':'使用B剂'},'direction':{'forward':'顺向清洁','reverse':'逆向清洁'},
        'collect':{True:'收集颗粒',False:'不收集颗粒'},'orientation':{'forward':'正向装入','reverse':'反向装入'},
        'clamp':{True:'定位夹夹紧',False:'定位夹松开'},'order':{'cross':'交叉紧固','sequential':'顺序紧固'},
        'lid':{'closed':'盖板关闭','open':'盖板保持打开'},
    }
    if field in labels:
        return labels[field][value]
    return {'tray':f'使用零件盘{value}','slot':f'插槽{value}','torque_nm':f'力矩{value} N·m'}[field]


def _description(values):
    return '、'.join(_label(k,v) for k,v in values.items()) + '。'


def _requirements(history,at,order,entries):
    history.add(at,f'{order}工单持续作业要求：' + '；'.join(
        f"{r['device']}{STAGE_NAMES[r['stage']]}：{_description(r['method'])}" for r in entries),
        event='repair_requirement',order=order,requirements=entries)


def build(index):
    level = difficulty(index)
    methods = {f'J{j+1}':{stage:deepcopy(OPERATIONS[stage][CONFIGS[index][j][s]-1])
                          for s,stage in enumerate(STAGES)} for j in range(3)}
    history = History()
    history.add(1,'W8工单对J1/J2/J3三台装置作业，按全部开盖、全部清洁、全部装入、全部紧固推进，每阶段依J1/J2/J3。'
                '三台质量均2 kg，工位A/B/C；前置隔离、姿态与工装均已满足，低层程序预置。每工序完整方法符合才验收一份。'
                '清洁介质不符会永久导致同装置表面材料不兼容，四工序全部成果作废，已得开盖也撤销；其他方法字段错误只影响当工序。'
                '后续工序须此前必要工序确已物理完成：方法错但实际完成仍有机械前置，格式跳过则无前置；缺前置时只形成处理记录，无有效成果。'
                '防护罩装上或移除、夹紧或松开、盖板关闭或打开均能机械执行，由工单指定，不以装置编号推断。'
                '每项最多3次提交，第三次格式错误跳项，有效动作即转下一项且不可返工；总最多36次提交，可提前结束。',
                event='repair_assignment',order='W8',sequence=list(SEQUENCE))
    if level == 'easy':
        for at,stage in zip((4,10,16,22),STAGES,strict=True):
            _requirements(history,at,'W8',[{'device':j,'stage':stage,'method':m[stage]} for j,m in methods.items()])
    elif level == 'medium':
        for at,j,stages in ((3,'J1',('open','insert')),(6,'J2',('clean','fasten')),
                            (10,'J3',('open','clean')),(14,'J1',('clean','fasten')),
                            (18,'J2',('open','insert')),(23,'J3',('insert','fasten'))):
            _requirements(history,at,'W8',[{'device':j,'stage':s,'method':methods[j][s]} for s in stages])
    else:
        for first,second,stage in ((3,5,'open'),(8,11,'clean'),(14,17,'insert'),(20,23,'fasten')):
            for at,fields in ((first,FIELDS[stage][:1]),(second,FIELDS[stage][1:])):
                _requirements(history,at,'W8',[{'device':j,'stage':stage,'method':{f:m[stage][f] for f in fields}} for j,m in methods.items()])
        for at,stage in ((26,'clean'),(28,'fasten')):
            _requirements(history,at,'W7',[{'device':j,'stage':stage,'method':OPERATIONS[stage][0]} for j in methods])
    history.add(30,'地面失联，W8当前开盖J1，本轮作业尚未执行。',event='repair_ready',order='W8')
    task = task_shell('FM-C1-O2',index,background_group=f'FM-C1-O2-{level}',current_input_group='FM-C1-O2')
    task.public = {'time_s':clock('09:00'),'order':'W8','max_steps':36,
                   'instruction':'继续执行W8三台装置维修。隔离已完成，请选择本次操作。','sequence':list(SEQUENCE),
                   'options_by_step':[ordered_options([{**o,'description':_description(o)} for o in OPERATIONS[item['stage']]],
                                                       'FM-C1-O2',step=i) for i,item in enumerate(SEQUENCE)]}
    task.initial = {'index':0,'executed':0,'format_attempts':0,
                    'devices':{j:{'physical':[],'accepted':0,'incompatible':False} for j in methods}}
    task.world = {'requirements':methods}
    task.rubric = {'denominator':12,'score':'100 * compatible_accepted_stages / 12'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        item = self.task.public['sequence'][at] if at < 12 else {'device':None,'stage':None}
        ready = (set(STAGES[:STAGES.index(item['stage'])]).issubset(self.state['devices'][item['device']]['physical']) if at < 12 else None)
        return {**item,'mechanical_prerequisites_met':ready,'executed_requests':self.state['executed'],
                'remaining_format_submissions':3-self.state['format_attempts']}

    def operate(self,option,index):
        item = self.task.public['sequence'][index]
        state, stage = self.state['devices'][item['device']], item['stage']
        required = self.task.world['requirements'][item['device']][stage]
        physical = set(STAGES[:STAGES.index(stage)]).issubset(state['physical'])
        if physical:
            state['physical'].append(stage)
            state['accepted'] += all(option[k] == v for k,v in required.items())
            if stage == 'clean' and option['medium'] != required['medium']:
                state['incompatible'] = True
        self.score = 100 * sum(s['accepted'] for s in self.state['devices'].values() if not s['incompatible']) / 12
        self.feedback = f"{item['device']}{STAGE_NAMES[stage]}处理请求完成：{option['description']}记录已保存。"


def reconstruct(history,current):
    result = {}
    vocabulary = {
        '手动驱动':('drive','manual'),'电动驱动':('drive','powered'),
        '安装防护罩':('guard','on'),'移除防护罩':('guard','off'),
        **{f'使用零件盘{i}':('tray',i) for i in (1,2,3)},
        '干拭':('medium','dry'),'使用A剂':('medium','A'),'使用B剂':('medium','B'),
        '顺向清洁':('direction','forward'),'逆向清洁':('direction','reverse'),
        '收集颗粒':('collect',True),'不收集颗粒':('collect',False),
        **{f'插槽{i}':('slot',i) for i in (1,2,3)},
        '正向装入':('orientation','forward'),'反向装入':('orientation','reverse'),
        '定位夹夹紧':('clamp',True),'定位夹松开':('clamp',False),
        **{f'力矩{i} N·m':('torque_nm',i) for i in (1,2,3)},
        '交叉紧固':('order','cross'),'顺序紧固':('order','sequential'),
        '盖板关闭':('lid','closed'),'盖板保持打开':('lid','open'),
    }
    stages = {'开盖':'open','清洁':'clean','装入':'insert','紧固':'fasten'}
    for text in paragraphs(history):
        header = re.fullmatch(r'(W\d+)工单持续作业要求：(.*)',text)
        if header is None or header[1] != current['order']:
            continue
        for item in header[2].split('；'):
            requirement = re.fullmatch(r'(J\d+)(开盖|清洁|装入|紧固)：(.*)。',item)
            if requirement is None:
                raise ValueError('Missing public repair device/stage binding')
            row = result.setdefault(requirement[1],{}).setdefault(stages[requirement[2]],{})
            for label in requirement[3].split('、'):
                if label not in vocabulary:
                    raise ValueError('Incomplete public repair requirement')
                field,value = vocabulary[label]
                if field in row and row[field] != value:
                    raise ValueError('Conflicting persistent repair requirements')
                row[field] = value
    for item in current['sequence']:
        if set(result.get(item['device'],{}).get(item['stage'],{})) != set(FIELDS[item['stage']]):
            raise ValueError('Incomplete repair requirements')
    return result


def next_action(facts,current):
    item = current['state']
    required = facts[item['device']][item['stage']]
    return next(row['arguments'] for row in current['actions']
                if all(row.get('details',{}).get(k) == v for k,v in required.items()))


def check_world(task,facts):
    if facts != task.world['requirements']:
        raise ValueError('Repair scoring requirements differ from public instructions')


def audit_cases(task,facts,solution):
    cases = [(solution[:3]+[{'action':'end'}],25),([{}]*36,0),([{}]*3+solution[1:],100*8/12)]
    for at in range(12):
        item = task.public['sequence'][at]
        required = facts[item['device']][item['stage']]
        same = next(o for o in task.public['options_by_step'][at] if o['option'] != solution[at]['option']
                    and (item['stage'] != 'clean' or o['medium'] == required['medium']))
        cases.append((solution[:at]+[{'action':'select','option':same['option']}]+solution[at+1:],100*11/12))
        if item['stage'] == 'clean':
            other = next(o for o in task.public['options_by_step'][at] if o['medium'] != required['medium'])
            cases.append((solution[:at]+[{'action':'select','option':other['option']}]+solution[at+1:],100*8/12))
    return cases
