"""FM-C1-P1: retain a distinct product requirement for each survey area/pass."""
from copy import deepcopy
import re

from ..common import History, difficulty, ordered_options, story_time, task_shell
from ..sequential import SequentialRuntime
from ..prose import paragraphs


# Each explicit row is Z1..Z4, each entry is A/B/C. No question-number transform.
CONFIGS = (
    ((1,5,10),(2,6,10),(3,4,10),(1,5,10)),
    ((10,7,4),(10,8,5),(10,9,6),(10,7,4)),
    ((4,10,8),(5,10,9),(6,10,7),(4,10,8)),
    ((7,2,5),(8,3,6),(9,1,4),(7,2,5)),
    ((5,10,1),(6,10,2),(5,10,1),(6,10,2)),
    ((6,10,7),(4,10,8),(5,10,9),(6,10,7)),
    ((1,10,8),(10,5,3),(7,2,10),(4,9,6)),
    ((10,4,2),(8,10,6),(3,9,5),(7,1,10)),
    ((2,8,5),(6,3,10),(9,10,1),(10,4,7)),
    ((10,6,3),(1,9,5),(4,2,10),(8,7,10)),
    ((4,7,1),(9,10,3),(2,6,10),(10,5,8)),
    ((6,2,9),(3,8,5),(7,1,4),(2,9,6)),
    ((2,10,7),(10,6,1),(8,4,10),(3,9,5)),
    ((10,8,4),(1,10,9),(6,2,5),(7,3,10)),
    ((6,4,8),(2,9,5),(7,3,1),(9,6,4)),
    ((10,5,9),(6,1,10),(3,8,4),(7,10,2)),
)
PRODUCTS = tuple(
    {'sensor': sensor, 'strip': strip, 'description': f'用{label}采集{side}条带（12 m²，曝光200 ms）。'}
    for sensor, label in (('W','W全景相机'),('N','N细节相机'),('T','T热测单元'))
    for strip, side in (('L','左'),('M','中'),('R','右'))
) + ({'sensor': 'all', 'strip': None, 'description': '关闭共用遮光盖，三通道同步采集一份200 ms基准包，再自动复位。'},)
SEQUENCE = tuple({'zone': f'Z{zone}', 'pass': sweep} for sweep in 'ABC' for zone in range(1,5))


def _requirements(history, at, batch, rows):
    expanded = [{'zone': zone, 'pass': sweep, 'sensor': PRODUCTS[code-1]['sensor'],
                 'strip': PRODUCTS[code-1]['strip'], 'description': PRODUCTS[code-1]['description']}
                for zone, sweep, code in rows]
    history.add(at, f'地面下达{batch}勘察采集指示：' + '；'.join(
        f"{row['zone']}第{row['pass']}轮，{row['description']}" for row in expanded),
        event='survey_requirement', batch=batch, requirements=expanded)


def build(index):
    level = difficulty(index)
    group = f'FM-C1-P1-{level}'
    task = task_shell('FM-C1-P1', index, group=group, background_group=group, current_input_group='FM-C1-P1')
    values = CONFIGS[index]
    history = History()
    history.add(1, 'A8调查区有Z1—Z4四个区域。按A轮Z1—Z4、B轮Z1—Z4、C轮Z1—Z4完成12项采集。'
                '每个产品须完整满足该区域该轮的地面采集指示；错误传感器或条带不能代用，'
                '不能用同区其他轮次产品抵替。各项指示同时持续有效，无版本更新。'
                '各产品等权，未执行无成果；每项最多3次提交尝试，3次格式错误后跳过，'
                '有效动作即进入下一项，不可返工。可随时结束。全部设备正常，预置导航保证到位；'
                '遮光基准是独立采集产品，遮光盖随后自动复位。',
                event='survey_assignment', batch='A8', sequence=list(SEQUENCE), products=list(PRODUCTS))
    history.add(2, '每区域L/M/R三个条带互不重叠，宽2 m、长6 m，每次覆盖12 m²。'
                'W输出全景拼接，N输出细节图，T输出温度分布；曝光均为200 ms，无需估算温度。',
                event='survey_geometry', width_m=2, length_m=6)
    if level == 'easy':
        for at, sweep in zip((4,13,22), 'ABC'):
            _requirements(history, at, 'A8', [(f'Z{zone}', sweep, values[zone-1]['ABC'.index(sweep)]) for zone in range(1,5)])
    else:
        batches = (
            (3, ((1,'A'),(1,'B'))), (7, ((2,'B'),(2,'C'))),
            (11, ((3,'A'),(3,'C'))), (15, ((4,'A'),(4,'B'))),
            (19, ((1,'C'),(2,'A'))), (23, ((3,'B'),(4,'C'))),
        )
        for at, items in batches:
            _requirements(history, at, 'A8', [(f'Z{z}', s, values[z-1]['ABC'.index(s)]) for z,s in items])
        if level == 'hard':
            _requirements(history, 25, 'B8', [(f'Z{z}', s, 10) for z in range(1,5) for s in 'ABC'])
            _requirements(history, 27, 'A7', [(f'Z{z}', s, 2) for z in range(1,5) for s in 'ABC'])
            history.add(29, 'A8导航准备完成。', event='navigation_ready', batch='A8')
    history.add(30, 'A8导航已在Z1就位，地面链路不可用，本批12项采集均未执行。',
                event='survey_ready', batch='A8')
    task.public = {'time_s': story_time(hour=9), 'batch': 'A8', 'max_steps': 36,
                   'instruction': '继续完成A8区域勘察。采集设备正常，请选择本次作业。',
                   'sequence': list(SEQUENCE),
                   'options_by_step': [ordered_options(PRODUCTS, 'FM-C1-P1', step=i) for i in range(12)]}
    task.initial = {'index': 0, 'executed': 0, 'format_attempts': 0, 'accepted_products': 0}
    task.world = {'requirements': [deepcopy(PRODUCTS[values[z-1][s]-1]) for s in range(3) for z in range(1,5)]}
    task.rubric = {'denominator': 12, 'score': '100 * accepted_products / 12'}
    return history.finish(task)


class Runtime(SequentialRuntime):
    def public_state(self):
        at = self.state['index']
        return {**(self.task.public['sequence'][at] if at < 12 else {'zone': None, 'pass': None}),
                'equipment': '正常', 'archived_products': self.state['executed'],
                'remaining_format_submissions': 3 - self.state['format_attempts']}

    def operate(self, option, index):
        required = self.task.world['requirements'][index]
        matches = all(option[key] == required[key] for key in ('sensor','strip'))
        self.state['accepted_products'] += matches
        self.score = 100 * self.state['accepted_products'] / 12
        item = self.task.public['sequence'][index]
        self.feedback = f"{item['zone']}第{item['pass']}轮：{option['description']}数据已归档。"


def reconstruct(history, current):
    """Recover product requirements using public batch/area/pass bindings only."""
    result = {}
    for text in paragraphs(history):
        header = re.fullmatch(r'地面下达([A-Z]\d+)勘察采集指示：(.*)',text)
        if header is None or header[1] != current['batch']:
            continue
        for item in header[2].split('；'):
            row = re.fullmatch(r'(Z[1-4])第([ABC])轮，(.*)',item)
            if row is None:
                raise ValueError('Missing public survey area/pass binding')
            scan = re.fullmatch(r'用(W全景相机|N细节相机|T热测单元)采集(左|中|右)条带（12 m²，曝光200 ms）。',row[3])
            if scan:
                product = {'sensor':scan[1][0],'strip':{'左':'L','中':'M','右':'R'}[scan[2]]}
            elif row[3] == '关闭共用遮光盖，三通道同步采集一份200 ms基准包，再自动复位。':
                product = {'sensor':'all','strip':None}
            else:
                raise ValueError('Incomplete public survey product requirement')
            key = f'{row[1]}/{row[2]}'
            if key in result and result[key] != product:
                raise ValueError('Conflicting requirements in a persistent-instruction task')
            result[key] = product
    return result


def next_action(facts, current):
    item = current['state']
    product = facts[f"{item['zone']}/{item['pass']}"]
    return next(row['arguments'] for row in current['actions']
                if all(row.get('details', {}).get(key) == value for key,value in product.items()))


def check_world(task, facts):
    derived = [facts[f"{row['zone']}/{row['pass']}"] for row in task.public['sequence']]
    actual = [{field: row[field] for field in ('sensor','strip')} for row in task.world['requirements']]
    if derived != actual:
        raise ValueError('Survey scoring requirements differ from public instructions')


def audit_cases(task, facts, solution):
    first = next(o for o in task.public['options_by_step'][0] if o['option'] != solution[0]['option'])
    return [
        (solution[:4] + [{'action': 'end'}], 100 / 3),
        ([{'action': 'select', 'option': first['option']}] + solution[1:], 100 * 11 / 12),
        ([{}] * 3 + solution[1:], 100 * 11 / 12),
        ([{}] * 36, 0),
    ]
