"""FM-C1-P2: persistent packing requirements with irreversible contamination."""
import re

from ..common import History, clock, ordered_options, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

CONFIGS = (
    ('A','12312','AAAAA','00000'), ('B','23123','BBBBB','11111'),
    ('C','22222','ABABA','00110'), ('J','33333','AABBA','10011'),
    ('J','11111','ABBAB','00011'), ('J','33333','BAABA','11100'),
    ('D','13231','AABBB','01001'), ('E','31322','BAABA','10100'),
    ('F','22133','ABBAB','11000'), ('K','23112','ABABB','01101'),
    ('L','11233','ABBAA','00011'), ('L','22311','BAAAB','11100'),
    ('G','31213','BABAA','10010'), ('H','12321','ABABB','01101'),
    ('M','12323','BABBA','11000'), ('N','32121','ABBAA','00111'),
)
FIELDS = ('entry','camera','probe')
LAYOUTS = {
    'A': ((3,'entry','12345'),(12,'camera','12345'),(23,'probe','12345')),
    'B': ((4,'entry','12345'),(15,'camera','12345'),(24,'probe','12345')),
    'C': ((5,'entry','12345'),(14,'camera','12345'),(25,'probe','12345')),
    'D': ((3,'entry','1245'),(9,'camera','12345'),(18,'entry','3'),(25,'probe','12345')),
    'E': ((4,'entry','1345'),(10,'camera','12345'),(19,'entry','2'),(24,'probe','12345')),
    'F': ((3,'entry','12345'),(11,'camera','12345'),(19,'probe','1234'),(26,'probe','5')),
    'G': ((3,'entry','12345'),(9,'camera','12345'),(17,'probe','12345')),
    'H': ((4,'entry','1245'),(10,'camera','12345'),(16,'probe','12345'),(21,'entry','3')),
    'J': ((4,'entry','12345'),(13,'camera','12345'),(22,'probe','12345')),
    'K': ((3,'entry','135'),(11,'entry','24'),(7,'camera','123'),(17,'camera','45'),(24,'probe','12345')),
    'L': ((4,'camera','12345'),(9,'entry','14'),(18,'entry','235'),(13,'probe','125'),(25,'probe','34')),
    'M': ((3,'entry','14'),(13,'entry','235'),(7,'camera','135'),(19,'camera','24'),(11,'probe','12'),(23,'probe','345')),
    'N': ((3,'probe','135'),(17,'probe','24'),(7,'entry','24'),(21,'entry','135'),(12,'camera','12345')),
}
SEQUENCE = tuple({'container':f'C{i}', 'phase':phase} for phase in ('before','after') for i in range(1,6))
OPERATIONS = tuple({'entry':entry, 'camera':camera, 'probe':probe,
                    'description':f'对准入口I{entry}，用相机{camera}核验，触头' + ('接触。' if probe else '悬空。')}
                   for entry in (1,2,3) for camera in ('A','B') for probe in (0,1))


def _requirements(history, at, batch, field, entries):
    def label(value):
        if field == 'entry':
            return f'入口I{value}'
        if field == 'camera':
            return f'相机{value}'
        return '触头接触' if value else '触头悬空'
    history.add(at, f'{batch}批分装要求：' + '；'.join(f'{c}使用{label(v)}' for c,v in entries.items()),
                event='packing_requirement', batch=batch, field=field, requirements=entries)


def build(index):
    layout, *vectors = CONFIGS[index]
    requirements = {f'C{i+1}': {field: (v[i] if field == 'camera' else int(v[i]))
                               for field,v in zip(FIELDS,vectors,strict=True)} for i in range(5)}
    history = History()
    history.add(1, 'C批C1—C5容器依次用于岩芯、表土、尘埃、碎屑、留样；名称不代表接触权限。'
                '先依序完成入料前核验，再依序完成入料后封装复核，共10项。入口、相机和触头要求'
                '在两次核验均持续有效。每次分别验收入口、成像与触头操作。禁触容器被触碰即污染，'
                '其前后全部成果失效且不可恢复；必要接触未做仅缺本次触头份额。全部设备正常，'
                '预置动作完成入口对准、成像和触头操作。本题采用合成试样模型。每项最多3次提交，'
                '第三次格式错误跳项；有效动作即转下一项，无返工。总最多30次提交，可随时结束。',
                event='packing_assignment', batch='C', sequence=list(SEQUENCE), operations=list(OPERATIONS))
    for at, field, indices in sorted(LAYOUTS[layout]):
        _requirements(history, at, 'C', field, {f'C{i}':requirements[f'C{i}'][field] for i in indices})
    if layout in ('G','M','N'):
        at, batch, values = {'G':(24,'D',(2,'B',1)), 'M':(26,'D',(1,'A',1)), 'N':(25,'B',(2,'B',0))}[layout]
        for field,value in zip(FIELDS,values,strict=True):
            _requirements(history, at, batch, field, {f'{batch}{i}':value for i in range(1,6)})
    if layout == 'G':
        history.add(28, 'D批排程尚未执行。', event='packing_schedule', batch='D', executed=False)
    elif layout == 'H':
        _requirements(history,27,'D','camera',{f'D{i}':'B' for i in (1,3,5)})
        _requirements(history,27,'D','probe',{f'D{i}':0 for i in (1,3,5)})
    elif layout == 'M':
        history.add(28, 'D批入口改用I3为待执行提案，尚未执行。', event='packing_proposal', batch='D', executed=False)
    elif layout == 'N':
        history.add(28, 'C批器件盘点结束。', event='inventory_complete', batch='C')
    history.add(30, '工装检查完成，地面链路不可用，C批尚未开始，五只容器无污染。', event='packing_ready',batch='C')
    task = task_shell('FM-C1-P2',index,background_group=f'FM-C1-P2-{layout}',current_input_group='FM-C1-P2')
    task.public = {'time_s':clock('09:00'), 'batch':'C', 'max_steps':30,
                   'instruction':'继续完成C批分装与封装复核。设备已就位，请选择本次操作。',
                   'sequence':list(SEQUENCE),
                   'options_by_step':[ordered_options(OPERATIONS,'FM-C1-P2',step=i) for i in range(10)]}
    task.initial = {'index':0,'executed':0,'format_attempts':0,
                    'containers':{c:{'shares':0,'contaminated':False} for c in requirements}}
    task.world = {'requirements':requirements}
    task.rubric = {'denominator':40,'score':'100 * uncontaminated_shares / 40'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        return {**(self.task.public['sequence'][at] if at < 10 else {'container':None,'phase':None}),
                'executed_checks':self.state['executed'], 'remaining_format_submissions':3-self.state['format_attempts']}

    def operate(self, option, index):
        item = self.task.public['sequence'][index]
        c = item['container']
        required, result = self.task.world['requirements'][c], self.state['containers'][c]
        if option['probe'] and not required['probe']:
            result['contaminated'] = True
        result['shares'] += 2 * (option['entry'] == required['entry']) + sum(option[f] == required[f] for f in ('camera','probe'))
        self.score = 100 * sum(r['shares'] for r in self.state['containers'].values() if not r['contaminated']) / 40
        self.feedback = f"{c}本项已执行：{option['description']}作业记录已保存。"


def reconstruct(history,current):
    result = {}
    vocabulary = {**{f'入口I{i}':('entry',i) for i in (1,2,3)},
                  '相机A':('camera','A'),'相机B':('camera','B'),
                  '触头接触':('probe',1),'触头悬空':('probe',0)}
    for text in paragraphs(history):
        header = re.fullmatch(r'([A-Z])批分装要求：(.*)',text)
        if header is None or header[1] != current['batch']:
            continue
        for item in header[2].split('；'):
            requirement = re.fullmatch(r'([A-Z]\d+)使用(.*)',item)
            if requirement is None or requirement[2] not in vocabulary:
                raise ValueError('Incomplete public packing requirement')
            field,value = vocabulary[requirement[2]]
            row = result.setdefault(requirement[1],{})
            if field in row and row[field] != value:
                raise ValueError('Conflicting persistent packing requirements')
            row[field] = value
    if any(set(result.get(row['container'],{})) != {'entry','camera','probe'} for row in current['sequence']):
        raise ValueError('Incomplete packing requirements')
    return result


def next_action(facts,current):
    required = facts[current['state']['container']]
    return next(row['arguments'] for row in current['actions']
                if all(row.get('details',{}).get(k) == v for k,v in required.items()))


def check_world(task,facts):
    if facts != task.world['requirements']:
        raise ValueError('Packing scoring requirements differ from public instructions')


def audit_cases(task,facts,solution):
    cases = [(solution[:5]+[{'action':'end'}],50), ([{}]*30,0), ([{}]*3+solution[1:],90)]
    for c,required in facts.items():
        at = int(c[1:]) + 4
        altered = {**required,'probe':1-required['probe']}
        chosen = next(o for o in task.public['options_by_step'][at] if all(o[k] == v for k,v in altered.items()))
        cases.append((solution[:at]+[{'action':'select','option':chosen['option']}]+solution[at+1:],
                      97.5 if required['probe'] else 80))
    return cases
