"""FM-C1-D1: platform patrol requirements and per-reading active-test limits."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

CONFIGS = (
    ('A','112233','RRRRRR','000000'),('B','231231','SSSSSS','111111'),
    ('C','333333','RSRSRS','010101'),('J','222222','RRSRSS','110010'),
    ('J','111111','RSSRRS','111000'),('J','222222','SRRSSR','000111'),
    ('D','123321','RRSSRS','101001'),('E','212133','SRRSSR','011010'),
    ('F','321122','RSSRRS','100110'),('K','213312','SSRRRS','101001'),
    ('L','312123','SSRRSR','101010'),('L','322113','RRSSSR','001110'),
    ('G','132231','SRSRRS','010110'),('H','213312','RSRSSR','101001'),
    ('M','123312','SRSSRR','100101'),('N','132312','RSRSSR','001110'),
)
FIELDS = ('bus','format','active_test')
LAYOUTS = {
    'A':((3,'bus','123456'),(13,'format','123456'),(24,'active_test','123456')),
    'B':((5,'bus','123456'),(14,'format','123456'),(25,'active_test','123456')),
    'C':((4,'bus','123456'),(15,'format','123456'),(23,'active_test','123456')),
    'D':((3,'bus','1234'),(10,'format','123456'),(18,'bus','56'),(25,'active_test','123456')),
    'E':((5,'bus','123456'),(12,'format','123456'),(20,'active_test','12346'),(26,'active_test','5')),
    'F':((4,'bus','123456'),(11,'format','123456'),(19,'active_test','1234'),(25,'active_test','56')),
    'G':((3,'bus','123456'),(10,'format','123456'),(17,'active_test','123456')),
    'H':((3,'bus','123456'),(9,'format','12345'),(16,'active_test','123456'),(21,'format','6')),
    'J':((4,'bus','123456'),(13,'format','123456'),(22,'active_test','123456')),
    'K':((3,'bus','135'),(15,'bus','246'),(7,'format','12'),(19,'format','3456'),(11,'active_test','14'),(23,'active_test','2356')),
    'L':((4,'active_test','123'),(18,'active_test','456'),(9,'format','123456'),(13,'bus','12'),(24,'bus','3456')),
    'M':((3,'bus','14'),(13,'bus','2356'),(7,'format','25'),(19,'format','1346'),(11,'active_test','36'),(23,'active_test','1245')),
    'N':((3,'active_test','135'),(17,'active_test','246'),(7,'bus','246'),(21,'bus','135'),(12,'format','123456')),
}
SEQUENCE = tuple({'unit':f'H{i}','pass':p} for p in (1,2) for i in range(1,7))


def _label(field,value):
    if field == 'bus':
        return f'从总线{value}读取'
    if field == 'format':
        return '保存原始遥测R' if value == 'R' else '保存诊断摘要S'
    return '必须执行短自检' if value else '仅被动读取，禁止短自检'


OPERATIONS = tuple({'bus':b,'format':f,'active_test':t,
                    'description':f'从总线{b}读取，' + _label('format',f) + ('，执行短自检。' if t else '，不执行短自检。')}
                   for b in (1,2,3) for f in ('R','S') for t in (0,1))


def _requirements(history,at,platform,leg,field,entries):
    history.add(at,f'{platform}平台{leg}巡航段要求：' + '；'.join(f'{unit}{_label(field,value)}' for unit,value in entries.items()),
                event='patrol_requirement',platform=platform,leg=leg,field=field,requirements=entries)


def build(index):
    layout,*vectors = CONFIGS[index]
    requirements = {f'H{i+1}':{f:(v[i] if f == 'format' else int(v[i])) for f,v in zip(FIELDS,vectors,strict=True)} for i in range(6)}
    history = History()
    history.add(1,'H平台Q8段先依H1—H6轮巡，再同序复读，共12项；各单元总线、归档格式和主动测试要求全程有效，无修订。'
                'H1/H2为热控，H3/H4为电源，H5/H6为载荷保障。所有设备与总线可用，自检不会造成新故障。'
                '每项分别验收总线读取、归档及自检选择；禁自检而启动会扰动当次读数、该次全无效，'
                '不撤销另一轮。必要自检未做只缺自检份额，读取归档仍可验收。每项最多3次提交，第三次格式错误跳项，'
                '有效动作即推进且不可返工；总最多36次提交，可提前结束。',
                event='patrol_assignment',platform='H',leg='Q8',sequence=list(SEQUENCE),operations=list(OPERATIONS))
    for at,field,indices in sorted(LAYOUTS[layout]):
        _requirements(history,at,'H','Q8',field,{f'H{i}':requirements[f'H{i}'][field] for i in indices})
    if layout in ('G','M','N'):
        at,platform,leg,values = {'G':(24,'J','Q8',(1,'R',1)), 'M':(26,'J','Q8',(3,'S',0)), 'N':(25,'H','Q7',(2,'R',1))}[layout]
        for field,value in zip(FIELDS,values,strict=True):
            _requirements(history,at,platform,leg,field,{f'{platform}{i}':value for i in range(1,7)})
    if layout == 'H':
        for field,value in (('format','S'),('active_test',0)):
            _requirements(history,27,'J','Q8',field,{'J1':value,'J2':value})
    if layout in ('G','M','N'):
        history.add(28,{'G':'备用J平台尚未投入。','M':'下一巡航段J平台排程待执行。','N':'H平台当前Q8段接口准备完成。'}[layout],
                    event='patrol_status')
    history.add(30,'H平台Q8段接口准备完成，尚未开始轮巡，地面不可用。',event='patrol_ready',platform='H',leg='Q8')
    task = task_shell('FM-C1-D1',index,background_group=f'FM-C1-D1-{layout}',current_input_group='FM-C1-D1')
    task.public = {'time_s':clock('09:00'),'platform':'H','leg':'Q8','max_steps':36,
                   'instruction':'继续完成H平台Q8巡航段的两轮保障检查。接口就绪，请选择本次操作。','sequence':list(SEQUENCE),
                   'options_by_step':[ordered_options(OPERATIONS,'FM-C1-D1',step=i) for i in range(12)]}
    task.initial = {'index':0,'executed':0,'format_attempts':0,'accepted_shares':0}
    task.world = {'requirements':requirements}
    task.rubric = {'denominator':60,'score':'100 * accepted_shares / 60; bus/format/test shares = 2/2/1'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        return {**(self.task.public['sequence'][at] if at < 12 else {'unit':None,'pass':None}),
                'executed_readings':self.state['executed'],'remaining_format_submissions':3-self.state['format_attempts']}

    def operate(self,option,index):
        item = self.task.public['sequence'][index]
        required = self.task.world['requirements'][item['unit']]
        if not (option['active_test'] and not required['active_test']):
            self.state['accepted_shares'] += 2*(option['bus'] == required['bus']) + 2*(option['format'] == required['format']) + (option['active_test'] == required['active_test'])
        self.score = 100 * self.state['accepted_shares'] / 60
        self.feedback = f"{item['unit']}第{item['pass']}轮：{option['description']}作业记录已保存。"


def reconstruct(history,current):
    result = {}
    vocabulary = {**{f'从总线{i}读取':('bus',i) for i in (1,2,3)},
                  '保存原始遥测R':('format','R'),'保存诊断摘要S':('format','S'),
                  '必须执行短自检':('active_test',1),'仅被动读取，禁止短自检':('active_test',0)}
    for text in paragraphs(history):
        header = re.fullmatch(r'([A-Z])平台(Q\d+)巡航段要求：(.*)',text)
        if header is None or (header[1],header[2]) != (current['platform'],current['leg']):
            continue
        for item in header[3].split('；'):
            requirement = re.fullmatch(r'([A-Z]\d+)(.*)',item)
            if requirement is None or requirement[2] not in vocabulary:
                raise ValueError('Incomplete public patrol requirement')
            field,value = vocabulary[requirement[2]]
            row = result.setdefault(requirement[1],{})
            if field in row and row[field] != value:
                raise ValueError('Conflicting persistent patrol requirements')
            row[field] = value
    if any(set(result.get(row['unit'],{})) != {'bus','format','active_test'} for row in current['sequence']):
        raise ValueError('Incomplete patrol requirements')
    return result


def next_action(facts,current):
    required = facts[current['state']['unit']]
    return next(row['arguments'] for row in current['actions'] if all(row.get('details',{}).get(k) == v for k,v in required.items()))


def check_world(task,facts):
    if facts != task.world['requirements']:
        raise ValueError('Patrol scoring requirements differ from public instructions')


def audit_cases(task,facts,solution):
    cases = [(solution[:6]+[{'action':'end'}],50),([{}]*36,0),([{}]*3+solution[1:],100*11/12)]
    for at,item in enumerate(task.public['sequence']):
        required = facts[item['unit']]
        for fields,loss in (({'bus':required['bus']%3+1},2),({'format':'S' if required['format'] == 'R' else 'R'},2),
                            ({'active_test':1-required['active_test']},1 if required['active_test'] else 5)):
            altered = {**required,**fields}
            choice = next(o for o in task.public['options_by_step'][at] if all(o[k] == v for k,v in altered.items()))
            cases.append((solution[:at]+[{'action':'select','option':choice['option']}]+solution[at+1:],100*(60-loss)/60))
    return cases
