"""FM-C1-D2: paired science exposures and dependent reference calibration."""
import re

from ..common import History, clock, difficulty, ordered_options, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

# Four explicit science/reference/band triples in G1..G4 order per instance.
CONFIGS = (
    'AB1 BC1 CD1 DA1', 'AC2 BD2 CA2 DB2',
    'DB1 CA1 BD2 AC2', 'BC3 DA3 CB1 AD1',
    'AB1 AC2 AD3 BA1', 'BD2 CD3 AD1 DB2',
    'AC1 DB3 BA2 CD1', 'CA2 BD1 AB3 DC2',
    'DC1 CB3 BA2 AD1', 'DB2 AC3 DA1 CB2',
    'CA3 BD2 CB1 DA3', 'DA1 AC2 BD3 CB1',
    'AD2 CB1 BC3 DA2', 'CD1 DA3 AB2 BC1',
    'BA3 CD2 AC1 DB3', 'DC2 AB1 CA3 BD2',
)
BANDS = {1:450,2:650,3:850}
SEQUENCE = tuple({'group':f'G{i}','exposure':exposure} for i in range(1,5) for exposure in (1,2,3))
OPERATIONS = tuple({'field':field,'band':band,'wavelength_nm':wavelength,
                    'description':f'指向视场{field}，以波段{band}（{wavelength} nm）曝光100 ms。'}
                   for field in 'ABCD' for band,wavelength in BANDS.items())


def _label(field,value):
    if field == 'band':
        return f'波段{value}（{BANDS[value]} nm）'
    return ('科学视场' if field == 'science' else '参考视场') + value


def _requirements(history,at,payload,batch,entries):
    history.add(at,f'载荷{payload}批次{batch}观测分组单：' + '；'.join(
        group + '：' + '、'.join(_label(field,value) for field,value in values.items()) for group,values in entries.items()),
        event='science_requirement',payload=payload,batch=batch,requirements=entries)


def build(index):
    level = difficulty(index)
    requirements = {f'G{i+1}':{'science':value[0],'reference':value[1],'band':int(value[2])} for i,value in enumerate(CONFIGS[index].split())}
    history = History()
    history.add(1,'本载荷P的Q8批次依G1—G4观测，每组按科学、参考、科学曝光三次，同组均用指定波段。'
                '每组指定科学与参考视场不同，A/B/C/D均可在不同组充当不同角色，不由字母推断。'
                '两张正确科学帧共同形成重复性产品；此科学对加正确参考形成完整定标产品。'
                '孤立一张科学或参考都不能成产品，四组等权且每组均需完成。各次曝光100 ms，指向、遮挡、轨道和时间条件已满足。'
                '当前进度由调度显示，错误操作不重拍；每槽最多3次提交，第三次格式错误跳槽，总最多36次提交，可提前结束。',
                event='science_assignment',payload='P',batch='Q8',sequence=list(SEQUENCE),operations=list(OPERATIONS))
    if level == 'easy':
        layout = ((4,'12',('science','reference','band')),(16,'34',('science','reference','band')))
    elif level == 'medium':
        layout = ((3,'13',('science',)),(7,'24',('reference',)),(11,'12',('band',)),
                  (15,'24',('science',)),(19,'13',('reference',)),(23,'34',('band',)))
    else:
        layout = ((3,'2',('science',)),(3,'4',('band',)),(7,'1',('reference',)),(7,'3',('science',)),
                  (11,'2',('band',)),(11,'4',('reference',)),(15,'1',('science',)),(15,'3',('reference',)),
                  (19,'2',('reference',)),(19,'4',('science',)),(23,'13',('band',)))
    for at,groups,fields in layout:
        _requirements(history,at,'P','Q8',{f'G{i}':{f:requirements[f'G{i}'][f] for f in fields} for i in groups})
    if level == 'hard':
        _requirements(history,26,'P','Q7',{f'G{i}':{'science':'A' if i%2 else 'C','reference':'B' if i%2 else 'D',
                                                 'band':1 if i%2 else 2} for i in range(1,5)})
        _requirements(history,28,'Q','Q8',{f'G{i}':{'science':'D','reference':'A','band':3} for i in range(1,5)})
    history.add(30,'本载荷P的Q8四组均尚未开始，指示链路不可用，载荷正常。',event='science_ready',payload='P',batch='Q8')
    task = task_shell('FM-C1-D2',index,background_group=f'FM-C1-D2-{level}',current_input_group='FM-C1-D2')
    task.public = {'time_s':clock('09:00'),'payload':'P','batch':'Q8','max_steps':36,
                   'instruction':'继续完成Q8四组科学观测。载荷已就位，请选择采集操作。','sequence':list(SEQUENCE),
                   'options_by_step':[ordered_options(OPERATIONS,'FM-C1-D2',step=i) for i in range(12)]}
    task.initial = {'index':0,'executed':0,'format_attempts':0,'accepted_frames':{group:[False]*3 for group in requirements}}
    task.world = {'requirements':requirements}
    task.rubric = {'denominator':40,'score':'100 * sum(3 * science_pair + 7 * science_pair * reference) / 40'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        return {**(self.task.public['sequence'][at] if at < 12 else {'group':None,'exposure':None}),
                'archived_frames':self.state['executed'],'remaining_format_submissions':3-self.state['format_attempts']}

    def operate(self,option,index):
        item = self.task.public['sequence'][index]
        required = self.task.world['requirements'][item['group']]
        role = 'reference' if item['exposure'] == 2 else 'science'
        self.state['accepted_frames'][item['group']][item['exposure']-1] = option['field'] == required[role] and option['band'] == required['band']
        self.score = 100 * sum((3 + 7*r[1]) if r[0] and r[2] else 0 for r in self.state['accepted_frames'].values()) / 40
        self.feedback = f"对视场{option['field']}以{option['wavelength_nm']} nm完成100 ms曝光，文件已归档。"


def reconstruct(history,current):
    result = {}
    vocabulary = {**{f'科学视场{f}':('science',f) for f in 'ABCD'},
                  **{f'参考视场{f}':('reference',f) for f in 'ABCD'},
                  '波段1（450 nm）':('band',1),'波段2（650 nm）':('band',2),'波段3（850 nm）':('band',3)}
    for text in paragraphs(history):
        header = re.fullmatch(r'载荷([A-Z])批次(Q\d+)观测分组单：(.*)',text)
        if header is None or (header[1],header[2]) != (current['payload'],current['batch']):
            continue
        for item in header[3].split('；'):
            requirement = re.fullmatch(r'(G\d+)：(.*)',item)
            if requirement is None:
                raise ValueError('Missing public science group identity')
            row = result.setdefault(requirement[1],{})
            for label in requirement[2].split('、'):
                if label not in vocabulary:
                    raise ValueError('Incomplete public science requirement')
                field,value = vocabulary[label]
                if field in row and row[field] != value:
                    raise ValueError('Conflicting persistent science requirements')
                row[field] = value
    if any(set(result.get(row['group'],{})) != {'science','reference','band'} for row in current['sequence']):
        raise ValueError('Incomplete science requirements')
    return result


def next_action(facts,current):
    item = current['state']
    required = facts[item['group']]
    field = required['reference' if item['exposure'] == 2 else 'science']
    return next(row['arguments'] for row in current['actions']
                if row.get('details',{}).get('field') == field and row['details']['band'] == required['band'])


def check_world(task,facts):
    if facts != task.world['requirements']:
        raise ValueError('Science scoring requirements differ from public instructions')


def audit_cases(task,facts,solution):
    cases = [(solution[:3]+[{'action':'end'}],25),([{}]*36,0),([{}]*3+solution[1:],75)]
    for at,item in enumerate(task.public['sequence']):
        required = facts[item['group']]
        field = required['reference' if item['exposure'] == 2 else 'science']
        wrong_band = next(o for o in task.public['options_by_step'][at] if o['field'] == field and o['band'] != required['band'])
        cases.append((solution[:at]+[{'action':'select','option':wrong_band['option']}]+solution[at+1:],
                      82.5 if item['exposure'] == 2 else 75))
    return cases
