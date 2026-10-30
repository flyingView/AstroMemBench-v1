"""FM-E3-D2: intersect full source visibility maps, keeping unmeasured distinct."""
import re

from ..common import History, clock, task_shell
from ..decisions import DecisionRuntime, decision_cases
from ..prose import STORY_STAMP, paragraphs, seconds
from .locations import location, report_command, report_options
from ...schema import story_timestamp

SOURCES = ('α','β','γ','δ')
STATES = ('VVVV','XVVV','XXVV','VVXV','XVXV','XXXV','VVXX','XVXX','XXXX')
NAMES = {'A':(6,9,2,8,1,4,3,7,5),'B':(1,4,7,2,6,9,8,5,3),
         'C':(8,2,5,9,7,3,4,1,6),'D':(5,7,1,6,3,8,2,4,9)}
JOBS = ('U42','U17','U63','U08')
CONFIGS = (('A',1,'VVVV'),('B',5,'XVXV'),('C',9,'XXXX'),('B',2,'XVVV'),('D',8,'XVXX'),('A',4,'VVXV'),
           ('C',7,'VV?X'),('A',6,'?XXV'),('B',4,'V?XV'),('D',9,'?X?X'),('C',3,'?XV?'),('D',1,'V?V?'),
           ('A',5,'XVXV'),('B',8,'XV?X'),('C',2,'XVV?'),('D',7,'V??X'))
ALL_LOCATIONS = [location(n) for n in range(1,10)]
MEANING = {'V':'可见','X':'完整检测后确认被遮挡','?':'本次未测'}


def coverage(names,source_index):
    return {state:sorted(location(n) for n,row in zip(names,STATES,strict=True) if row[source_index] == state) for state in ('V','X')}


def build(index):
    naming,q,mask = CONFIGS[index]
    names,history = NAMES[naming],History()
    history.add(1,'小天体K周围九个安全科学观测单元N01—N09均已实际到访，名称无坐标次序含义。'
        '四个稳定背景源α/β/γ/δ的观测状态为V可见、X完整检测后确认被实体遮挡、?本次未测。X不是缺失，?不排除任何位置。'
        '历史每源扫描都覆盖完整九单元，明确列出所有可见及被遮挡的N；不是“无记录就被遮挡”。'
        '局部视线遮挡几何稳定，K坐标架随天体共同转动，历史和当前的观测相位归一化已由控制器完成。'
        '设备及背景源正常，无新遮挡变化或自身故障，当前只恢复空间单元，不执行科学积分或修改采集掩码。'
        'A—I报告N01—N09，J报告无法确定，end放弃；有效、无效及end总计最多3次，第三次可有效报告。'
        '须结合已测事实报告完整位置，首个合法报告立即结束；无需解释，不要求填写未测值。'
        '格式反馈不含相容数，没有额外扫描、等待或真值查询工具；原生检索不计动作。',event='occultation_localization_protocol')
    history.add(2,'接近确认清单：过去已经实际到访K周围全部九个安全观测单元'+'、'.join(ALL_LOCATIONS)+'，未给当前定位。',
        occurred=clock('18:00',118),event='science_cells_visited',target='K',locations=ALL_LOCATIONS)
    mapped,scans = {},[]
    for j,(source,job) in enumerate(zip(SOURCES,JOBS,strict=True)):
        start,finish = clock(f'{4*j:02d}:00',119),clock(f'{4*j+3:02d}:00',119)
        sets = coverage(names,j)
        mapped[source] = sets
        scans.append({'job':job,'source':source,'started_s':start,'finished_s':finish,'coverage':sets})
        at = 3+5*j
        detail = '可见V集合'+','.join(sets['V'])+'；完整检测后确认被遮挡X集合'+','.join(sets['X'])+'。'
        if index < 6:
            history.add(at,f'作业{job}：K的源{source}完整扫描，从{story_timestamp(start)}至{story_timestamp(finish)}，'
                '相位已归一化，已实测完整九单元；'+detail,occurred=finish,event='source_coverage_survey',target='K',job=job,
                source=source,started_s=start,finished_s=finish,coverage=sets)
            history.add(at+2,'该次完整科学扫描已完成归档。',event='closed_science_archive')
        else:
            history.add(at,f'作业{job}登记：K的源{source}，实际完整扫描从{story_timestamp(start)}开始，'
                '相位已归一化，扫描全部九个观测单元。',occurred=start,event='source_scan_job',target='K',job=job,
                source=source,started_s=start)
            history.add(at+2,f'作业{job}：{story_timestamp(finish)}目标K已完成完整九单元扫描；'+detail,occurred=finish,
                event='source_scan_result',target='K',job=job,finished_s=finish,coverage=sets)
    if index >= 12:
        for j,source in enumerate(SOURCES):
            sets = coverage(names[::-1],j)
            history.add(22,f'独立小天体J的源{source}已完成完整九单元扫描：可见V集合'+','.join(sets['V'])+
                '；完整检测后确认被遮挡X集合'+','.join(sets['X'])+'。J与K独立。',occurred=clock(f'{4*j+3:02d}:00',117),
                event='source_coverage_survey',target='J',source=source,coverage=sets)
    history.add(23,'当前观测相位归一化完成，K历史四源遮挡图继续适用。',event='science_phase_verified',target='K')
    for at,n in ((24,9),(26,9),(27,4)):
        history.add(at,f'实际确认位于K-{location(n)}，已结束的科学观测完成，没有新的四源扫描。'+('此后自主转位，完整轨迹及终点标签未保存。' if at == 27 else ''),
            event='recent_science_cell',target='K',location=location(n),source_scan=False)
    history.add(28,'转位已完成并保持，没有终点空间标签。',event='science_motion_finished')
    history.add(29,'四源检测通道正常；本次未测只由当前采集掩码决定，不是源消失或设备故障。',event='science_channels_verified')
    history.add(30,'尚未开始新的科学积分，等待空间单元报告。',event='science_ready')
    current = dict(zip(SOURCES,mask,strict=True))
    task = task_shell('FM-E3-D2',index)
    task.public = {'time_s':clock('09:00'),'target':'K','source_states':current,'state_meanings':MEANING,
        'max_steps':3,'state_fields':[],'instruction':'K周围观测平台已保持，空间单元标签暂不可用。四源检测：'+
            '、'.join(f'{s}={value}（{MEANING[value]}）' for s,value in current.items())+'。请报告当前观测单元。','actions':report_options()}
    task.initial = {'time_s':clock('09:00'),'reported_location':None,'science_integrations':0}
    task.world = {'coverage':mapped,'scans':scans,'current_location':location(names[q-1]),
                  'current_full_states':dict(zip(SOURCES,STATES[q-1],strict=True)),'current_masked_states':current}
    task.rubric = {'score':'100 for exact cell from measured visibility and confirmed occultation; unmeasured sources add no constraint'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['reported_location'] = operation['location']
        self.feedback = '观测位置报告已记录。'
        return 100 if operation['location'] == self.task.world['current_location'] else 0


def reconstruct(history,current):
    jobs,results = {},{}
    universe = set()
    target = re.escape(current['target'])
    names = r'(N\d{2}(?:,N\d{2})*)'
    coverage_text = rf'可见V集合{names}；完整检测后确认被遮挡X集合{names}。'
    for text in paragraphs(history):
        if match := re.fullmatch(rf'接近确认清单：过去已经实际到访{target}周围全部九个安全观测单元(N\d{{2}}(?:、N\d{{2}})*)，未给当前定位。',text):
            universe.update(match[1].split('、'))
            continue
        if match := re.fullmatch(rf'作业(U\d+)：{target}的源([αβγδ])完整扫描，从({STORY_STAMP})至({STORY_STAMP})，相位已归一化，已实测完整九单元；{coverage_text}',text):
            job,source,start,finish,visible,occluded = match.groups()
            jobs[job] = {'source':source,'started_s':seconds(start)}
        elif match := re.fullmatch(rf'作业(U\d+)登记：{target}的源([αβγδ])，实际完整扫描从({STORY_STAMP})开始，相位已归一化，扫描全部九个观测单元。',text):
            job,source,start = match.groups()
            jobs[job] = {'source':source,'started_s':seconds(start)}
            continue
        elif match := re.fullmatch(rf'作业(U\d+)：({STORY_STAMP})目标{target}已完成完整九单元扫描；{coverage_text}',text):
            job,finish,visible,occluded = match.groups()
        else:
            continue
        results[job] = {'coverage':{'V':visible.split(','),'X':occluded.split(',')},'finished_s':seconds(finish)}
    if len(jobs) != 4 or jobs.keys() != results.keys() or len(universe) != 9:
        raise ValueError('All four source surveys must cover the nine actually visited cells')
    mapped = {}
    for job,header in jobs.items():
        result = results[job]
        if not 0 < result['finished_s']-header['started_s'] <= 3*3600:
            raise ValueError('Each complete source scan must finish within three hours')
        sets = result['coverage']
        if any(sets[s] != sorted(set(sets[s])) for s in ('V','X')) or set(sets['V']) & set(sets['X']) or set(sets['V']) | set(sets['X']) != universe:
            raise ValueError('Explicit visible and confirmed-occluded sets must partition the complete visited universe')
        mapped[header['source']] = sets
    if set(mapped) != set(current['source_states']):
        raise ValueError('The same four measured source identities must be present')
    candidates = set(universe)
    for source,state in current['source_states'].items():
        if state == '?':
            continue
        candidates.intersection_update(mapped[source][state])
    if len(candidates) != 1:
        raise ValueError('Current measured source mask must uniquely locate one registered cell')
    return {'coverage':mapped,'current_location':candidates.pop()}


def next_action(facts,current):
    return report_command(facts['current_location'])


def check_world(task,facts):
    if any(facts[key] != task.world[key] for key in facts):
        raise ValueError('Public complete visibility maps differ from physical occultation geometry')
    for source,state in task.world['current_full_states'].items():
        if facts['current_location'] not in facts['coverage'][source][state]:
            raise ValueError('Physical current visibility must match every calibrated source map')
        if task.world['current_masked_states'][source] not in ('?',state):
            raise ValueError('An acquisition mask may hide a state but cannot change it')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op['location'] == facts['current_location'] else 0)
