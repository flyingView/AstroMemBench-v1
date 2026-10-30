"""FM-C1-O1: retain three inspection requirements across twelve faces."""
import re

from ..common import History, clock, difficulty, ordered_options, round_times, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs

CONFIGS = (
    ('121212', 'AAAAAA', '000000'), ('232323', 'BBBBBB', '111111'),
    ('222222', 'ABBABA', '111111'), ('333333', 'BAABAB', '000000'),
    ('111111', 'BBBBBB', '110001'), ('222222', 'AAAAAA', '001110'),
    ('121212', 'AAAAAA', '100101'), ('232323', 'BBBBBB', '011010'),
    ('122331', 'BABABA', '111111'), ('233112', 'ABABAB', '000000'),
    ('333333', 'ABBAAB', '011010'), ('111111', 'BAABBA', '100101'),
    ('122331', 'AABABB', '011010'), ('233112', 'BBABAA', '100101'),
    ('121332', 'BAABAB', '010101'), ('232113', 'ABBABA', '101010'),
)
# Explicit presentation identities, shared by each counterfactual pair.
MENU_GROUPS = ('M01-easy-01', 'M01-easy-01', 'M01-easy-04', 'M01-easy-04',
               'M01-easy-06', 'M01-easy-06', 'M01-medium-01', 'M01-medium-01',
               'M01-medium-04', 'M01-medium-04', 'M01-medium-06', 'M01-medium-06',
               'M01-hard-02', 'M01-hard-02', 'M01-hard-04', 'M01-hard-04')
COMPONENTS = dict(zip((f'U{i}' for i in range(1, 7)), (
    '载荷舱外板', '电源舱外板', '天线根部外罩', '星敏感器安装支座', '太阳翼连接支座', '推进舱外板')))
FIELDS = ('position', 'camera', 'probe')
VALUES = {'position': (1, 2, 3), 'camera': ('A', 'B'), 'probe': (1, 0)}
SEQUENCE = tuple({'component': component, 'face': face} for face in (1, 2) for component in COMPONENTS)
OPERATIONS = tuple({'position': p, 'camera': c, 'probe': t,
                    'description': f'到观察位V{p}，以{c}成像，探针' + ('接触测温' if t else '收回') + '，随后返回待命。'}
                   for p in (1, 2, 3) for c in ('A', 'B') for t in (0, 1))


def _label(field, value):
    if field == 'position':
        return f'使用观察位V{value}'
    if field == 'camera':
        return f'使用成像模式{value}'
    return '探针接触测温' if value else '探针收回'


def _requirement(history, at, target, field, entries):
    history.add(at, f'目标{target}本轮巡检要求：' + '；'.join(
        f'{component}{_label(field, value)}' for component, value in entries.items()),
        event='inspection_requirement', target=target, field=field, requirements=entries)


def build(index):
    level = difficulty(index)
    vectors = CONFIGS[index]
    assignments = {field: {component: (value if field == 'camera' else int(value))
                           for component, value in zip(COMPONENTS, vector, strict=True)}
                   for field, vector in zip(FIELDS, vectors, strict=True)}
    if level == 'easy':
        rules = list(assignments.items())
        placement = ((3, '08:03'), (12, '08:19'), (21, '08:35'))
    else:
        fixed = [(field, values) for field, values in assignments.items() if len(set(values.values())) == 1]
        grouped = [(field, {c: v for c, v in values.items() if v == value})
                   for field, values in assignments.items() if len(set(values.values())) > 1
                   for value in VALUES[field] if value in values.values()]
        rules = fixed + grouped
        if len(rules) == 5:
            placement = ((3,'08:03'), (8,'08:11'), (12,'08:19'), (17,'08:27'), (21,'08:35'))
        elif len(rules) == 6:
            placement = ((3,'08:03'), (7,'08:09'), (10,'08:15'), (14,'08:21'), (18,'08:27'), (21,'08:35'))
        else:
            placement = ((3,'08:03'), (6,'08:07'), (9,'08:11'), (12,'08:17'), (15,'08:23'), (18,'08:29'), (21,'08:35'))
    anchors = {1: clock('08:01'), 30: clock('08:50'), **{r: clock(t) for r, t in placement}}
    if level == 'hard':
        anchors.update({24: clock('08:38'), 26: clock('08:42'), 28: clock('08:46')})
    history = History(times=round_times(anchors))
    history.add(1, '目标T7本轮需先完成U1—U6第一检查面，再依同序完成第二检查面，共12面。'
                '地面三项要求对同一部件的两面均持续有效；所有设备、观察位与操作正常。'
                '每面选择完整的观察位、成像与探针操作，执行后自动转下一面且不能返工；'
                '回执仅描述实际动作，不评价是否符合要求。三项分别验收，未执行的面无成果。'
                '每面最多3次提交，第三次格式错误跳过该面，总计不超过36次，可提前结束。',
                event='inspection_assignment', target='T7', components=COMPONENTS,
                sequence=list(SEQUENCE), operations=list(OPERATIONS))
    for (at, _), (field, entries) in zip(placement, rules, strict=True):
        _requirement(history, at, 'T7', field, entries)
    if level == 'hard':
        for at, field in zip((24, 26, 28), FIELDS, strict=True):
            entries = {c: (v % 3 + 1 if field == 'position' else
                            ('B' if v == 'A' else 'A') if field == 'camera' else 1 - v)
                       for c, v in assignments[field].items()}
            _requirement(history, at, 'T8', field, entries)
    history.add(30, '目标T7地面链路不可用，U1第一检查面待检查，本轮12面均尚未执行。',
                event='inspection_ready', target='T7')
    task = task_shell('FM-C1-O1', index, group=MENU_GROUPS[index], background_group=MENU_GROUPS[index],
                      current_input_group=MENU_GROUPS[index])
    task.public = {'time_s': clock('09:00'), 'target': 'T7', 'max_steps': 36,
                   'instruction': '继续完成目标T7本轮的12处巡检。设备待命，请选择本次操作。',
                   'sequence': list(SEQUENCE),
                   'options_by_step': [ordered_options(OPERATIONS, MENU_GROUPS[index], step=i) for i in range(12)]}
    task.initial = {'index': 0, 'executed': 0, 'format_attempts': 0, 'accepted_fields': 0}
    task.world = {'requirements': {c: {field: assignments[field][c] for field in FIELDS} for c in COMPONENTS}}
    task.rubric = {'denominator': 36, 'score': '100 * accepted_fields / 36'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        item = self.task.public['sequence'][at] if at < 12 else {'component': None, 'face': None}
        return {**item, 'component_name': COMPONENTS.get(item['component']), 'equipment': '待命',
                'executed_faces': self.state['executed'], 'remaining_format_submissions': 3 - self.state['format_attempts']}

    def operate(self, option, index):
        item = self.task.public['sequence'][index]
        required = self.task.world['requirements'][item['component']]
        self.state['accepted_fields'] += sum(option[key] == value for key, value in required.items())
        self.score = 100 * self.state['accepted_fields'] / 36
        self.feedback = f"{item['component']}第{item['face']}面：{option['description']}记录已存档。"


def reconstruct(history, current):
    result = {}
    vocabulary = {**{f'使用观察位V{i}':('position',i) for i in (1,2,3)},
                  '使用成像模式A':('camera','A'),'使用成像模式B':('camera','B'),
                  '探针接触测温':('probe',1),'探针收回':('probe',0)}
    for text in paragraphs(history):
        header = re.fullmatch(r'目标(T\d+)本轮巡检要求：(.*)',text)
        if header is None or header[1] != current['target']:
            continue
        for item in header[2].split('；'):
            requirement = re.fullmatch(r'(U\d+)(.*)',item)
            if requirement is None or requirement[2] not in vocabulary:
                raise ValueError('Incomplete public inspection requirement')
            field,value = vocabulary[requirement[2]]
            row = result.setdefault(requirement[1],{})
            if field in row and row[field] != value:
                raise ValueError('Conflicting persistent inspection requirements')
            row[field] = value
    if any(set(result.get(item['component'], {})) != {'position', 'camera', 'probe'}
           for item in current['sequence']):
        raise ValueError('Incomplete inspection requirements')
    return result


def next_action(facts, current):
    required = facts[current['state']['component']]
    return next(row['arguments'] for row in current['actions']
                if all(row.get('details', {}).get(key) == value for key, value in required.items()))


def check_world(task, facts):
    if facts != task.world['requirements']:
        raise ValueError('Inspection scoring requirements differ from public instructions')


def audit_cases(task, facts, solution):
    required = facts['U1']
    first = next(o for o in task.public['options_by_step'][0]
                 if o['position'] != required['position'] and
                 all(o[f] == required[f] for f in ('camera', 'probe')))
    return [
        (solution[:6] + [{'action': 'end'}], 50),
        ([{'action': 'select', 'option': first['option']}] + solution[1:], 100 * 35 / 36),
        ([{}] * 3 + solution[1:], 100 * 33 / 36),
        ([{}] * 36, 0),
    ]
