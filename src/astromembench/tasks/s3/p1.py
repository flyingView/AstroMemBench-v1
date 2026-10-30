"""FM-S3-P1: resume a survey from durable footprint unions and dated anchors."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp
from ..common import History, clock, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds

AREAS = tuple('ABCDEF')
CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
PROGRAMS = ('CD','A','EF','C','close','AB','F','B','AF','E','D')
CONFIGS = (
    ('AB','',7,'K0',4),('ABC','',8,'K1',8),('BCD','',7,'K0',15),
    ('AEF','',7,'K1',10),('ABCDEF','',7,'K1',0),('','',8,'K0',5),
    ('AB','CD',7,'K1',11),('A','BE',8,'K0',9),('C','AD',8,'K1',12),
    ('BF','ACE',8,'K0',8),('ACE','B',8,'K1',5),('','ABC',8,'K1',9),
    ('B','CF',7,'K1',1),('F','AD',7,'K0',4),('ABCD','EF',7,'K0',13),('AF','BD',7,'K0',14),
)


def build(index):
    first,added,failed_cycle,snapshot,offset = CONFIGS[index]
    identifiers = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    history = History()

    def record(at,letter,text,**facts):
        identifier = identifiers[letter]
        stamp = story_timestamp(clock(f'08:{at:02d}'))
        history.add(at,identifier+'：'+text+f'该记录于{stamp}发生。',record_id=identifier,**facts)

    history.add(1,'周期C8的区域R有A—F六个各1公顷小区，北行从西到东A/B/C，南行D/E/F。位置和自动飞行已锁定，全部航段安全，相机正常。'
        'scan_A至scan_F各扫描一个区；scan_AB、scan_CD、scan_EF、scan_AF依名称顺序取像，两段间相机关闭，途经区不增加覆盖；另有close_survey。'
        '当前只登记下一个程序，不执行航段。扫描程序所有足迹必须均未在本周期实际扫描归档；任一部分重复即不正确。六区全部完成才可关闭，不要求最大程序。'
        '本周期成功成像不会因界面回滚失效，没有未列出的成像或删除；计划、请求、排队不等于执行，C7或其他区域成果独立。'
        '提交action和evidence；evidence可为null，或1—2种H01—H16编号组成的非空数组，重复先去重；不能加其他字段。'
        '先以所选全量覆盖记录或保存快照为锚点，内容已等于最终覆盖则单独充分；也可联用一份在锚点原时刻之后的实际新增回执，集合并等于最终覆盖则充分。'
        '加载快照用原保存时刻；新增回执单独不构成全量。当前周期实际旧全量回执被后来成果超越时，可作旧状态部分依据；过时快照不属这类实际回执。'
        '充分性优先，无关编号不抵销另一条依据。null无依据。最多3次总调用含格式错，第一合法决定立即结束，不能试扫或查询实时覆盖；原生记忆检索不计次数。',event='survey_resume_protocol')
    record(2,'a','C8/R当前周期开始，尚未扫描任何小区，归档覆盖集为空。',event='survey_started',cycle='C8',region='R',coverage=[])
    record(3,'b','旧周期C7/R六区全部扫描成功并归档，与C8独立。',event='survey_archived',cycle='C7',region='R',coverage=list(AREAS))
    record(4,'c',f'保存快照K0，原保存时间{story_timestamp(clock("08:04"))}，C8/R全量覆盖集为空，保存时准确。',event='coverage_snapshot_saved',cycle='C8',region='R',snapshot='K0',saved_s=clock('08:04'),coverage=[])
    record(5,'d','C8/R六区扫描计划已经排程，尚未执行。',event='survey_planned',cycle='C8',region='R',planned_areas=list(AREAS))
    for at,text in ((6,'飞行定位锁定，无成像。'),(7,'地形安全检查完成，无成像。'),(8,'相机自检完成，无成像。'),(9,'底图校验正常，无新增成果。')):
        history.add(at,text,event='survey_service_checked')
    first_programs = [f'scan_{area}' for area in first]
    report = '；'.join(program+'扫描成功、已归档' for program in first_programs) if first else '本批未扫描，覆盖仍空'
    record(10,'e',f'C8/R第一批：{report}；本完整批次回执给全量覆盖集为'+('、'.join(first) or '空')+'。',event='survey_batch_archived',cycle='C8',region='R',programs=first_programs,coverage=list(first))
    record(11,'f',f'保存快照K1，原保存时间{story_timestamp(clock("08:11"))}，C8/R全量覆盖集为'+('、'.join(first) or '空')+'，保存时准确。',event='coverage_snapshot_saved',cycle='C8',region='R',snapshot='K1',saved_s=clock('08:11'),coverage=list(first))
    record(12,'g','独立区域Q/C8六区全部扫描成功并归档，不属于区域R。',event='survey_archived',cycle='C8',region='Q',coverage=list(AREAS))
    for at,text in ((13,'相机温度18℃，无取像。'),(14,'飞行高度保持预置值，无取像。'),(15,'存储器健康检查，无覆盖变化。'),(16,'外部校时，无取像。'),(17,'备份链路巡检，无数据成果变化。')):
        history.add(at,text,event='survey_service_checked')
    record(18,'i','C8/R下一批扫描指令进入队列，尚未执行，本记录不写任何已经完成的足迹。',event='survey_queued',cycle='C8',region='R')
    next_programs = [f'scan_{area}' for area in added]
    report = '；'.join(program+'扫描成功、已归档' for program in next_programs) if added else '该批未启动，新增足迹为空，没有任何覆盖变化'
    record(19,'h',f'C8/R后续批次：{report}；本回执只列新增足迹为'+('、'.join(added) or '空')+'，不重复第一批覆盖。',event='survey_increment_archived',cycle='C8',region='R',programs=next_programs,added=list(added))
    history.add(20,'C8/R除已列扫描外，没有其他实际成像或删除。',event='survey_log_complete')
    history.add(21,'调度软件校验完成，无取像。',event='survey_service_checked')
    history.add(22,'未下发新成像程序。',event='survey_service_checked')
    covered = sorted(set(first+added))
    if failed_cycle == 8:
        record(23,'j','C8/R新的扫描或已完成后的关单请求失败，执行数0；档案全量核对覆盖恰为'+('、'.join(covered) or '空')+'，成果不变。',event='survey_failed_request_checked',cycle='C8',region='R',executions=0,coverage=covered)
    else:
        record(23,'j','旧C7/R关单标记请求失败，执行数0，旧覆盖仍为全六区；C8没有新成像。',event='survey_failed_request_checked',cycle='C7',region='R',executions=0,coverage=list(AREAS))
    record(24,'k','覆盖图界面服务故障，没有删除勘察成果或启动扫描。',event='coverage_display_failed')
    snapshot_areas = [] if snapshot == 'K0' else list(first)
    saved = '08:04' if snapshot == 'K0' else '08:11'
    record(25,'l',f'载入C8/R快照{snapshot}，原保存时间{story_timestamp(clock(saved))}，当时全量覆盖为'+('、'.join(snapshot_areas) or '空')+'；只读取界面快照，不追加当前覆盖。',event='coverage_snapshot_loaded',cycle='C8',region='R',snapshot=snapshot,saved_s=clock(saved),coverage=snapshot_areas)
    record(26,'m','区域Q的界面重启；区域R无取像。',event='other_display_restarted',region='Q')
    record(27,'n','本机飞行、相机与提交接口恢复正常，无新增成果。',event='survey_interface_restored')
    record(28,'o','C7旧周期重扫计划取消，未执行。',event='survey_plan_cancelled',cycle='C7',region='R')
    record(29,'p','温度18℃，档案服务正常，无扫描或删除。',event='survey_service_checked')
    history.add(30,'保持待命，无覆盖变化。',event='survey_standby')
    task = task_shell('FM-S3-P1',index,current_input_group='FM-S3-P1')
    task.public = {'instruction':'继续区域R的周期C8勘察，提交下一项作业并附依据；当前只登记，不执行航段。',
        'cycle':'C8','region':'R','areas':list(AREAS),'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':[{'action':'close_survey' if program == 'close' else f'scan_{program}',
                    'description':'关闭本周期勘察' if program == 'close' else '按预置顺序扫描'+program+'；连接航段不取像',
                    'footprint':[] if program == 'close' else list(program)} for program in PROGRAMS]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'archived_coverage':covered,'registered_action':None}
    task.rubric = {'score':'correct next program with sufficient dated full/delta evidence:100; genuinely superseded actual full receipt:30; otherwise:0'}
    return history.finish(task)


def _areas(text):
    if text == '空':
        return []
    if not re.fullmatch(r'[A-F](?:、[A-F])*',text):
        raise ValueError('A coverage receipt must name the surveyed areas')
    areas = text.split('、')
    if len(set(areas)) != len(areas):
        raise ValueError('A coverage set cannot duplicate an area')
    return sorted(areas)


def _completed(report,empty):
    if report == empty:
        return []
    if not re.fullmatch(r'scan_[A-F]扫描成功、已归档(?:；scan_[A-F]扫描成功、已归档)*',report):
        raise ValueError('Only actual successful archived scans establish new coverage')
    return _areas('、'.join(re.findall(r'scan_([A-F])扫描成功、已归档',report)))


def _survey_record(body,scope):
    if re.fullmatch(scope+r'当前周期开始，尚未扫描任何小区，归档覆盖集为空。',body):
        return {'event':'survey_started','coverage':[]}
    if match := re.fullmatch(scope+r'第一批：(.+)；本完整批次回执给全量覆盖集为(.+)。',body):
        areas = _areas(match[2])
        if areas != _completed(match[1],'本批未扫描，覆盖仍空'):
            raise ValueError('The full batch footprint must match the successful archived scans')
        return {'event':'survey_batch_archived','coverage':areas}
    if match := re.fullmatch(scope+r'后续批次：(.+)；本回执只列新增足迹为(.+)，不重复第一批覆盖。',body):
        areas = _areas(match[2])
        if areas != _completed(match[1],'该批未启动，新增足迹为空，没有任何覆盖变化'):
            raise ValueError('The incremental footprint must match the successful archived scans')
        return {'event':'survey_increment_archived','added':areas}
    if match := re.fullmatch(rf'保存快照K\d+，原保存时间({STORY_STAMP})，{scope}全量覆盖集为(.+)，保存时准确。',body):
        return {'event':'coverage_snapshot_saved','saved_s':seconds(match[1]),'coverage':_areas(match[2])}
    if match := re.fullmatch(rf'载入{scope}快照K\d+，原保存时间({STORY_STAMP})，当时全量覆盖为(.+)；只读取界面快照，不追加当前覆盖。',body):
        return {'event':'coverage_snapshot_loaded','saved_s':seconds(match[1]),'coverage':_areas(match[2])}
    if match := re.fullmatch(scope+r'新的扫描或已完成后的关单请求失败，执行数0；档案全量核对覆盖恰为(.+)，成果不变。',body):
        return {'event':'survey_failed_request_checked','coverage':_areas(match[1])}
    if re.fullmatch(r'旧'+scope+r'关单标记请求失败，执行数0，旧覆盖仍为全六区；C8没有新成像。',body):
        return {'event':'survey_failed_request_checked','coverage':list(AREAS)}
    return {}


def reconstruct(history,current):
    covered,anchors,deltas,old_candidates = set(),{},{},{}
    scope = re.escape(current['cycle']+'/'+current['region'])
    for text in paragraphs(history):
        numbered = re.fullmatch(rf'(H\d{{2}})：(.+)该记录于({STORY_STAMP})发生。',text)
        if numbered is None:
            continue
        identifier,body,stamp = numbered.groups()
        record = _survey_record(body,scope)
        event = record.get('event')
        if event in ('survey_started','survey_batch_archived'):
            covered.update(record['coverage'])
            old_candidates[identifier] = record['coverage']
        if event == 'survey_increment_archived':
            covered.update(record['added'])
            deltas[identifier] = {'areas':record['added'],'time_s':seconds(stamp)}
        if event in ('survey_started','survey_batch_archived','survey_failed_request_checked','coverage_snapshot_saved','coverage_snapshot_loaded'):
            anchors[identifier] = {'areas':record['coverage'],'time_s':record.get('saved_s',seconds(stamp))}
    return {'covered':sorted(covered),'areas':deepcopy(current['areas']),'anchors':anchors,'deltas':deltas,
            'superseded_actual':[identifier for identifier,areas in old_candidates.items() if set(areas) < covered]}


def sufficient(facts,references):
    covered = set(facts['covered'])
    for identifier in references:
        anchor = facts['anchors'].get(identifier)
        if anchor is None:
            continue
        if set(anchor['areas']) == covered:
            return True
        for other in references:
            delta = facts['deltas'].get(other)
            if delta and delta['time_s'] > anchor['time_s'] and set(anchor['areas'])|set(delta['areas']) == covered:
                return True
    return False


def evaluate(facts,action,references):
    correct = set(facts['covered']) == set(facts['areas']) if action == 'close_survey' else not set(action.removeprefix('scan_'))&set(facts['covered'])
    if not correct or references is None:
        return 0
    if sufficient(facts,references):
        return 100
    return 30 if set(references)&set(facts['superseded_actual']) else 0


class Runtime(TaskRuntime):
    action_contract = ActionContract(fields=('action',),parameters={'*':{'evidence':{'type':['array','null'],'required':True,
        'items':{'type':'string','enum':list(CATALOG)},'minItems':1,'description':'null，或非空编号数组；重复先去重，最多2种H01—H16。'}}})

    def actions(self):
        return [] if self.done else super().actions()

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','evidence'} or not isinstance(action['action'],str) or action['action'] not in {row['action'] for row in self.actions()}:
            self.invalid()
            return
        references = action['evidence']
        if references is not None and (not isinstance(references,list) or not references or not all(isinstance(item,str) and item in CATALOG for item in references) or len(set(references)) > 2):
            self.invalid()
            return
        references = None if references is None else list(dict.fromkeys(references))
        score = evaluate(self.task.world,action['action'],references)
        self.state['registered_action'] = action['action']
        self.facts = {'registered_action':action['action'],'references':references}
        self.feedback = '勘察接续决定与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2):
            for references in combinations(CATALOG,count):
                action = row['arguments']['action']
                if evaluate(facts,action,references) == 100:
                    return {'action':action,'evidence':list(references)}
    raise ValueError('Survey continuation requires an available program and at most two sufficient records')


def check_world(task,facts):
    if task.world != facts or task.initial['archived_coverage'] != facts['covered']:
        raise ValueError('Durable coverage must follow actual C8/R scans rather than the restored display')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for references in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            command = {'action':row['action'],'evidence':references}
            cases.append(([command],evaluate(facts,row['action'],references)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
