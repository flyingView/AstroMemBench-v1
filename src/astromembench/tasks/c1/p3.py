"""FM-C1-P3: distinct loading/delivery requirements and dependent milestones."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

CONFIGS = (
    ('A','1234','1234','1231','UUUU','AAAA','2312','UUUU','KKKK'),
    ('A','1234','1234','2312','FFFF','BBBB','3123','FFFF','OOOO'),
    ('A','1234','2143','1111','UFUF','ABAB','2222','FUFU','KOKO'),
    ('A','1234','4321','3333','UFFU','ABBA','1111','UFFU','KOOK'),
    ('A','1234','3142','2222','UUFF','AABB','1233','UFUF','KKKO'),
    ('A','3142','1234','3333','FFUU','BBAA','2311','FUFU','OOOK'),
    ('B','1234','2413','1323','UFUF','ABBA','2131','FFUU','KOKO'),
    ('B','1234','2413','2311','FUFU','BAAB','3212','UUFF','OKOK'),
    ('C','4321','2143','1123','UFUF','BAAB','2331','FUFU','KOKK'),
    ('C','4321','2143','2231','FUFU','ABBA','3112','UFUF','OKOO'),
    ('C','2413','1234','2321','UUFF','ABAB','3132','UFFU','KOOO'),
    ('C','2413','1234','3132','FFUU','BABA','1213','FUUF','OKKK'),
    ('D','1234','4321','1321','UFUF','ABBA','3213','FUFU','KOKO'),
    ('D','1234','4321','2312','FUFU','BAAB','1321','UFUF','OKOK'),
    ('E','4321','1234','1123','UFFU','BAAB','2331','FFUU','KKKO'),
    ('E','4321','1234','2231','FUUF','ABBA','3112','UUFF','OOOK'),
)
FIELDS = {'load':('grip','posture','frame'), 'deliver':('dock','posture','lid')}
LAYOUTS = {
    'A': ((4,'load',('grip',),'1234'),(8,'load',('posture','frame'),'1234'),
          (15,'deliver',('dock',),'1234'),(21,'deliver',('posture','lid'),'1234')),
    'B': ((3,'load',FIELDS['load'],'13'),(7,'deliver',FIELDS['deliver'],'24'),
          (12,'load',FIELDS['load'],'24'),(19,'deliver',FIELDS['deliver'],'13')),
    'C': ((3,'load',('grip',),'1234'),(8,'deliver',('posture',),'1234'),
          (13,'load',('posture','frame'),'1234'),(18,'deliver',('dock',),'14'),
          (18,'deliver',('lid',),'23'),(24,'deliver',('dock',),'23'),(24,'deliver',('lid',),'14')),
    'D': ((3,'load',('grip','posture'),'14'),(7,'deliver',('dock','lid'),'23'),
          (11,'load',('grip','posture'),'23'),(15,'load',('frame',),'1234'),
          (19,'deliver',('dock','lid'),'14'),(23,'deliver',('posture',),'1234')),
    'E': ((3,'deliver',('lid',),'1234'),(7,'load',('posture',),'12'),(7,'deliver',('posture',),'34'),
          (11,'load',('grip',),'1234'),(15,'deliver',('posture',),'12'),(15,'load',('posture',),'34'),
          (19,'deliver',('dock',),'1234'),(23,'load',('frame',),'1234')),
}


def _label(field,value):
    if field == 'posture':
        return '立放' if value == 'U' else '平放'
    if field == 'lid':
        return '保持封口' if value == 'K' else '打开检视盖'
    return {'grip':'抓位G','frame':'独立车架构型','dock':'卸台D'}[field] + str(value)


OPERATIONS = {
    'load': tuple({'grip':g,'posture':p,'frame':f,
                   'description':f'从抓位G{g}装车，' + _label('posture',p) + f'，用独立车架构型{f}。'}
                  for g in (1,2,3) for p in ('U','F') for f in ('A','B')),
    'deliver': tuple({'dock':d,'posture':p,'lid':lid,
                      'description':f'交付至卸台D{d}，' + _label('posture',p) + '，' + _label('lid',lid) + '。'}
                     for d in (1,2,3) for p in ('U','F') for lid in ('K','O')),
}


def _requirements(history,at,batch,phase,entries):
    text = '；'.join(box + '：' + '、'.join(_label(field,value) for field,value in values.items())
                    for box,values in entries.items())
    history.add(at, f"{batch}批{'装车' if phase == 'load' else '交付'}处置单：{text}",
                event='cargo_requirement',batch=batch,phase=phase,requirements=entries)


def build(index):
    layout, loading, unloading, *vectors = CONFIGS[index]
    requirements = {f'F{i+1}': {phase:{field:(int(vector[i]) if field in ('grip','dock') else vector[i])
                                      for field,vector in zip(FIELDS[phase],vectors[start:start+3],strict=True)}
                               for phase,start in (('load',0),('deliver',3))} for i in range(4)}
    sequence = [{'box':f'F{i}','phase':phase} for phase,order in (('load',loading),('deliver',unloading)) for i in order]
    history = History()
    history.add(1, 'B8批四箱按装车清单依次装车，平台统一运抵后按交付清单卸货。地面分阶段处置单持续有效。'
                '每箱三字段全部符合的装车为准备里程碑；只有准备已验收，该箱才可完成合规交付。'
                '其他字段不符则该阶段不验收，无额外危险。禁开盖而打开使该箱全部成果失效，撤销准备；'
                '应开盖而保封只缺交付，不损伤准备。所有设备与位置正常，低层轨迹预置，每箱独立工装。'
                '装车未执行后也可下发空载交付请求，但不会产生货物成果。每项最多3次提交，第三次格式错误跳项，'
                '有效动作即推进且不能返工；总最多24次提交，可提前结束。该合成物流合同不能由箱名或质量推断要求。',
                event='cargo_assignment',batch='B8',sequence=sequence)
    history.add(2, 'F1/F2/F3/F4质量分别2/4/6/8 kg；所有抓位均可达、卸台足够，每箱有独立A/B构型货位，'
                '每货位承载不少于8 kg。质量不决定抓位、姿态或接收点；开盖不取走物品。',
                event='cargo_equipment',mass_kg={'F1':2,'F2':4,'F3':6,'F4':8},operations=OPERATIONS)
    for at,phase,fields,boxes in LAYOUTS[layout]:
        _requirements(history,at,'B8',phase,{f'F{i}':{field:requirements[f'F{i}'][phase][field] for field in fields} for i in boxes})
    if layout in ('B','D','E'):
        at,batch,boxes,load,deliver = {
            'B':(25,'B7','1',(2,'U','A'),(2,'U','K')),
            'D':(26,'B9','1234',(1,'U','B'),(3,'F','O')),
            'E':(26,'B7','1234',(3,'F','A'),(1,'U','K')),
        }[layout]
        for phase,values in (('load',load),('deliver',deliver)):
            _requirements(history,at,batch,phase,{f'F{i}':dict(zip(FIELDS[phase],values,strict=True)) for i in boxes})
        if layout == 'D':
            history.add(28,'B9下一批装载提案待执行。',event='cargo_proposal',batch='B9',executed=False)
        elif layout == 'E':
            history.add(28,'现批B8四只箱盘点完毕。',event='inventory_complete',batch='B8')
    history.add(30,'B8清单就绪，地面链路不可用，本轮尚未开始。',event='cargo_ready',batch='B8')
    task = task_shell('FM-C1-P3',index,background_group=f'FM-C1-P3-{layout}-{loading}-{unloading}',
                      current_input_group=f'FM-C1-P3-{loading}-{unloading}')
    task.public = {'time_s':clock('09:00'),'batch':'B8','max_steps':24,
                   'instruction':'继续完成B8四只货箱转运。设备就绪，请选择本次操作。','sequence':sequence,
                   'options_by_step':[ordered_options(OPERATIONS[row['phase']],'FM-C1-P3',step=i) for i,row in enumerate(sequence)]}
    task.initial = {'index':0,'executed':0,'format_attempts':0,
                    'boxes':{box:{'prepared':False,'delivered':False,'invalidated':False} for box in requirements}}
    task.world = {'requirements':requirements}
    task.rubric = {'score':'25 * sum((1 - Z) * (0.25 * P + 0.75 * P * Q))'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        return {**(self.task.public['sequence'][at] if at < 8 else {'box':None,'phase':None}),
                'executed_requests':self.state['executed'], 'remaining_format_submissions':3-self.state['format_attempts']}

    def operate(self,option,index):
        item = self.task.public['sequence'][index]
        required = self.task.world['requirements'][item['box']][item['phase']]
        state = self.state['boxes'][item['box']]
        complies = all(option[field] == value for field,value in required.items())
        if item['phase'] == 'load':
            state['prepared'] = complies
        else:
            state['delivered'] = complies
            if required['lid'] == 'K' and option['lid'] == 'O':
                state['invalidated'] = True
        self.score = 25 * sum(0.25 * b['prepared'] + 0.75 * b['prepared'] * b['delivered']
                              for b in self.state['boxes'].values() if not b['invalidated'])
        self.feedback = f"{item['box']}请求已执行：{option['description']}作业记录已保存。"
        if index == 3:
            self.feedback += '预置平台运输完成，进入交付阶段。'


def reconstruct(history,current):
    result = {}
    vocabulary = {**{f'抓位G{i}':('grip',i) for i in (1,2,3)},
                  **{f'卸台D{i}':('dock',i) for i in (1,2,3)},
                  '立放':('posture','U'),'平放':('posture','F'),
                  '独立车架构型A':('frame','A'),'独立车架构型B':('frame','B'),
                  '保持封口':('lid','K'),'打开检视盖':('lid','O')}
    for text in paragraphs(history):
        header = re.fullmatch(r'([A-Z]\d+)批(装车|交付)处置单：(.*)',text)
        if header is None or header[1] != current['batch']:
            continue
        phase = {'装车':'load','交付':'deliver'}[header[2]]
        for item in header[3].split('；'):
            requirement = re.fullmatch(r'(F\d+)：(.*)',item)
            if requirement is None:
                raise ValueError('Missing public cargo identity')
            row = result.setdefault(requirement[1],{}).setdefault(phase,{})
            for label in requirement[2].split('、'):
                if label not in vocabulary:
                    raise ValueError('Incomplete public cargo requirement')
                field,value = vocabulary[label]
                if field in row and row[field] != value:
                    raise ValueError('Conflicting persistent cargo requirements')
                row[field] = value
    for item in current['sequence']:
        expected = {'grip','posture','frame'} if item['phase'] == 'load' else {'dock','posture','lid'}
        if set(result.get(item['box'],{}).get(item['phase'],{})) != expected:
            raise ValueError('Incomplete cargo requirements')
    return result


def next_action(facts,current):
    item = current['state']
    required = facts[item['box']][item['phase']]
    return next(row['arguments'] for row in current['actions']
                if all(row.get('details',{}).get(k) == v for k,v in required.items()))


def check_world(task,facts):
    if facts != task.world['requirements']:
        raise ValueError('Cargo scoring requirements differ from public instructions')


def audit_cases(task,facts,solution):
    cases = [(solution[:4]+[{'action':'end'}],25),([{}]*24,0),([{}]*3+solution[1:],75)]
    for index,item in enumerate(task.public['sequence']):
        required = facts[item['box']][item['phase']]
        key = 'grip' if item['phase'] == 'load' else 'dock'
        altered = {**required,key:required[key]%3+1}
        chosen = next(o for o in task.public['options_by_step'][index] if all(o[k] == v for k,v in altered.items()))
        cases.append((solution[:index]+[{'action':'select','option':chosen['option']}]+solution[index+1:],
                      75 if item['phase'] == 'load' else 81.25))
        if item['phase'] == 'deliver':
            altered = {**required,'lid':'O' if required['lid'] == 'K' else 'K'}
            chosen = next(o for o in task.public['options_by_step'][index] if all(o[k] == v for k,v in altered.items()))
            cases.append((solution[:index]+[{'action':'select','option':chosen['option']}]+solution[index+1:],
                          75 if required['lid'] == 'K' else 81.25))
    return cases
