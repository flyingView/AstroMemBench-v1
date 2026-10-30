"""FM-S3-O1: durable inspection artifacts and cleared volatile analysis."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ...schema import story_timestamp
from ..common import History, clock, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds

CATALOG = tuple(f'H{i:02d}' for i in range(1,17))
STEPS = ('capture','analyze','save_draft','submit_report','finish')
LABELS = ('取像并持久保存原片','固定程序判读并写入易失缓冲','持久保存判读草稿','提交报告并由外部档案接收归档','结束目标任务')
# Complete early/late progress for A, B, C. All three objects have the same
# receipt structure; each row has three different post-restart states.
CONFIGS = (
    ('A',((0,0),(1,2),(2,3)),'K1',3,None),
    ('B',((3,4),(0,0),(1,2)),'K2',12,None),
    ('C',((2,3),(0,0),(1,2)),'K2',5,None),
    ('B',((1,2),(2,3),(3,4)),'K1',8,None),
    ('A',((0,4),(0,0),(1,2)),'K1',4,None),
    ('C',((2,3),(1,2),(3,4)),'K1',6,None),
    ('C',((2,3),(0,4),(0,0)),'K2',9,'C'),
    ('C',((3,4),(0,0),(2,2)),'K1',7,'A'),
    ('A',((1,2),(2,3),(0,4)),'K1',15,'B'),
    ('A',((2,3),(0,0),(3,4)),'K2',12,'C'),
    ('B',((0,0),(3,3),(1,2)),'K1',5,'A'),
    ('C',((0,0),(1,2),(4,4)),'K1',14,'B'),
    ('B',((1,2),(0,0),(2,3)),'K2',4,'C'),
    ('C',((3,4),(0,0),(1,2)),'K1',6,'D'),
    ('C',((0,0),(0,4),(2,3)),'K1',11,'C'),
    ('A',((2,4),(1,2),(2,3)),'K1',9,'D'),
)
ASSIGNMENTS = {'A':('ABC',('J26','J42','J11')),'B':('BCA',('J42','J11','J26')),
               'C':('CAB',('J11','J42','J26')),'D':('CBA',('J26','J11','J42'))}


def domains(stage):
    return {'original_saved':stage >= 1,'volatile_analysis':stage >= 2,'draft_saved':stage >= 3,'report_archived':stage >= 4,'ended':False}


def domain_text(state):
    return '；'.join((
        '原片已持久保存' if state['original_saved'] else '尚无原片',
        '易失缓冲内有判读结果' if state['volatile_analysis'] else '易失缓冲内无判读结果',
        '判读草稿已持久保存' if state['draft_saved'] else '未保存判读草稿',
        '报告已由外部档案接收归档' if state['report_archived'] else '未提交外部报告',
        '目标任务尚未结束'))


def direct_identity(target,cycle='W8'):
    return {'cycle':cycle,'target':target,'image_id':cycle+'-'+target}


def identity_text(identity):
    return identity['cycle']+'/'+identity.get('package_id',identity.get('job_id',identity.get('target','')))+(
        '，原片'+identity['image_id'] if 'image_id' in identity else '')


def package_bindings_text(packages):
    return '；'.join(f'W8/{package}对应W8/{job}' for package,job in packages.items())


def job_bindings_text(jobs):
    return '；'.join(f'{entry["cycle"]}/{job}对应目标{entry["target"]}、原片{entry["image_id"]}' for job,entry in jobs.items())


def build(index):
    target,progress,loaded,offset,assignment = CONFIGS[index]
    stages = dict(zip('ABC',progress,strict=True))
    ids = {letter:f'H{1+(at+offset)%16:02d}' for at,letter in enumerate('abcdefghijklmnop')}
    jobs,packages = {},{}
    if assignment:
        names,bindings = ASSIGNMENTS[assignment]
        jobs = {job:direct_identity(name) for job,name in zip(('J11','J26','J42'),names,strict=True)}
        if index >= 12:
            packages = dict(zip(('PK4','PK7','PK9'),bindings,strict=True))
    order = ([jobs[packages[package]]['target'] for package in ('PK4','PK7','PK9')] if packages else
             [jobs[job]['target'] for job in ('J11','J26','J42')] if jobs else list('ABC'))

    def identity(name):
        if index < 6:
            return direct_identity(name)
        job = next(job for job,entry in jobs.items() if entry['target'] == name)
        return {'cycle':'W8',**({'package_id':next(package for package,bound in packages.items() if bound == job)} if packages else {'job_id':job})}

    history = History()

    def record(at,letter,text,**facts):
        stamp = story_timestamp(clock(f'08:{at:02d}'))
        history.add(at,ids[letter]+'：'+text+f'该记录于{stamp}发生。',record_id=ids[letter],**facts)

    def receipt(at,letter,name,start,end,*,failed=False,cycle='W8'):
        subject = identity(name) if cycle == 'W8' else direct_identity(name,cycle)
        operations = [] if failed else list(STEPS[start:end])
        if failed:
            text = LABELS[end]+'请求失败，执行数0，实际各域没有变化'
        elif operations:
            text = '依次实际执行：'+'；'.join(LABELS[STEPS.index(action)]+'成功' for action in operations)
        else:
            text = '未执行新工序，进行完整域状态核对'
        record(at,letter,identity_text(subject)+'：'+text+'；'+domain_text(domains(end))+'。',
            event='inspection_receipt',subject=subject,domains=domains(end),operations=operations,
            **({'failed_operation':STEPS[end],'executions':0} if failed else {}))

    def snapshot(at,letter,name,phase,saved,*,load=False):
        objects = [{'subject':identity(obj),'domains':domains(stages[obj][phase])} for obj in order]
        text = '。'.join('对象键'+identity_text(obj['subject'])+'：'+domain_text(obj['domains']) for obj in objects)
        record(at,letter,('读取' if load else '保存')+name+f'，原保存时间{story_timestamp(clock(saved))}；'+text+
            '。这是显示字段，快照不保存或恢复缓冲中的判读数据本体，不改变持久成果。',
            event='inspection_snapshot_loaded' if load else 'inspection_snapshot_saved',objects=objects,snapshot=name,saved_s=clock(saved))

    history.add(1,'W8巡检周期的A/B/C目标分别是接口面PA/PB/PC，对应唯一原片W8-A/W8-B/W8-C；W7是独立旧周期。'
        '各目标依次capture取像写入原片盘、analyze固定程序判读写入易失缓冲、save_draft持久保存草稿、submit_report提交并由外部档案接收、finish结束。'
        '不得跳步，不重拍已保存原片、不重复提交归档报告。控制器故障只清空全部易失缓冲，持久原片、草稿和外部报告均保留；保存草稿不会撤销已有原片。'
        '快照只显示保存时字段，载入不能恢复缓冲字节，也不能倒撤持久成果。设备和接口当前正常，固定取像和检验程序不需要识别图像内容。'
        '工单与作业包只是本周期固定身份预分配，不代表原片或成果已存在；回执按原接口键给出，身份须依公开绑定解析。'
        '证据可按实际发生的控制器清空规则推知缓冲为空；早记录的持久字段若被后来保存或提交改变，不可借故障恢复旧值。'
        '当前只登记下一操作，不驱动设备，无免费查询或重放接口。提交action、target、evidence，证据为null或非空H01—H16编号数组，重复先去重最多2种；不得多加字段。'
        '最多3次总调用含格式错，首合法决定立即结束；原生记忆检索不计调用。',event='inspection_resume_protocol')
    record(2,'a','W8三个目标均尚无原片、无缓冲结果、无草稿、未提交外部报告，任务均未结束。',
        event='inspection_initialized',cycle='W8',objects={name:domains(0) for name in 'ABC'})
    receipt(3,'b',target,0,4,cycle='W7')
    history.add(4,'W8三个目标的取像到提交计划均已排程，尚未执行。',event='inspection_planned')
    history.add(5,'原片盘自检正常，无取像或分析。',event='inspection_monitoring')
    history.add(6,'指向控制锁定，无新增巡检成果。'+('预分配作业包到工单：'+package_bindings_text(packages)+'，未执行工序。' if packages else ''),
        event='inspection_packages_allocated' if packages else 'inspection_monitoring',**({'cycle':'W8','packages':packages} if packages else {}))
    history.add(7,'外部档案服务在线，无提交。'+('预分配工单到目标及原片：'+job_bindings_text(jobs)+'，身份分配不代表原片已存在。' if jobs else ''),
        event='inspection_jobs_allocated' if jobs else 'inspection_monitoring',**({'cycle':'W8','jobs':jobs} if jobs else {}))
    for at,letter,name in zip((8,9,10),'cde',order,strict=True):
        receipt(at,letter,name,0,stages[name][0])
    snapshot(11,'f','K1',0,'08:11')
    history.add(12,'整理线缆，无判读或保存。',event='inspection_monitoring')
    for at,letter,name in zip((13,14,15),'ghi',order,strict=True):
        receipt(at,letter,name,*stages[name])
    snapshot(16,'j','K2',1,'08:16')
    for at,letter,name in zip((17,18,19),'klm',order,strict=True):
        receipt(at,letter,name,stages[name][1],stages[name][1],failed=True)
    history.add(20,'没有表外取像、判读、保存或提交。',event='inspection_log_complete')
    history.add(21,'时钟同步，无成果变化。',event='inspection_monitoring')
    record(22,'n','控制器故障并重启，全部易失判读缓冲已清空；持久原片、草稿和外部报告未删除，没有其他工序执行。',event='inspection_controller_restarted')
    history.add(23,'处理器和传感器接口恢复正常，未重新执行判读。',event='inspection_monitoring')
    history.add(24,'数据盘健康检查，未改写成果。',event='inspection_monitoring')
    snapshot(25,'o',loaded,0 if loaded == 'K1' else 1,'08:11' if loaded == 'K1' else '08:16',load=True)
    history.add(26,'提交接口就绪，无新取像、判读、保存或提交。',event='inspection_interface_ready')
    history.add(27,'未追加新目标工序。',event='inspection_monitoring')
    record(28,'p',identity_text(direct_identity(target,'W7'))+'旧报告目录再次读出，已归档，不属于W8。',event='old_inspection_report_read',subject=direct_identity(target,'W7'))
    history.add(29,'硬件温度18℃，无新成果。',event='inspection_monitoring')
    history.add(30,'保持待命，没有档案修改。',event='inspection_monitoring')
    task = task_shell('FM-S3-O1',index,current_input_group=f'FM-S3-O1-{target}')
    task.public = {'instruction':f'继续W8目标{target}的巡检任务。提交下一项操作。',**direct_identity(target),
        'time_s':clock('09:00'),'max_steps':3,'record_catalog':list(CATALOG),'state_fields':[],
        'actions':[{'action':action,'target':name,'description':f'W8目标{name}，原片W8-{name}：'+label} for name in 'ABC' for action,label in zip(STEPS,LABELS,strict=True)]}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.initial = {'objects':deepcopy(task.world['objects']),'registered_operation':None}
    task.rubric = {'score':'correct next operation with a sufficient post-restart record:100; genuinely earlier actual target progress:30; otherwise:0'}
    return history.finish(task)


def progress(state):
    return 4 if state['report_archived'] else 3 if state['draft_saved'] else 2 if state['volatile_analysis'] else 1 if state['original_saved'] else 0


def _inspection_domains(text):
    choices = (
        ('original_saved','尚无原片','原片已持久保存'),
        ('volatile_analysis','易失缓冲内无判读结果','易失缓冲内有判读结果'),
        ('draft_saved','未保存判读草稿','判读草稿已持久保存'),
        ('report_archived','未提交外部报告','报告已由外部档案接收归档'),
        ('ended','目标任务尚未结束','目标任务已结束'))
    parts = text.split('；')
    if len(parts) != len(choices):
        raise ValueError('An inspection receipt must describe all five storage domains')
    state = {}
    for item,(key,no,yes) in zip(parts,choices,strict=True):
        if item not in (no,yes):
            raise ValueError('Unknown inspection storage-domain statement')
        state[key] = item == yes
    if ((not state['original_saved'] and any(state[key] for key in ('volatile_analysis','draft_saved','report_archived')))
            or state['report_archived'] and not state['draft_saved'] or state['ended']):
        raise ValueError('Inspection storage domains must follow the unfinished public workflow')
    return state


def _inspection_receipt(text):
    match = re.fullmatch(r'(.+)；((?:尚无原片|原片已持久保存)；.+)。',text)
    if match is None:
        raise ValueError('An actual inspection receipt must include its complete storage state')
    report,state = match[1],_inspection_domains(match[2])
    stage = progress(state)
    if report == '未执行新工序，进行完整域状态核对':
        return state
    if report == LABELS[stage]+'请求失败，执行数0，实际各域没有变化':
        return state
    if report.startswith('依次实际执行：'):
        operations = report.removeprefix('依次实际执行：').split('；')
        start = stage-len(operations)
        if start >= 0 and operations == [label+'成功' for label in LABELS[start:stage]] and state == domains(stage):
            return state
    raise ValueError('Inspection operations and complete storage state must agree')


def reconstruct(history,current):
    objects,receipts,jobs,packages,restarts = {},{},{},{},[]
    images = {}

    def resolve(text):
        match = re.fullmatch(r'(W\d+)/(PK\d+|J\d+|[ABC])(?:，原片([^，：]+))?',text)
        if match is None:
            raise ValueError('An inspection subject must identify its public interface key')
        cycle,key,image = match.groups()
        if cycle != current['cycle']:
            return None
        if key.startswith('PK'):
            subject = jobs[packages[(cycle,key)]]
        elif key.startswith('J'):
            subject = jobs[(cycle,key)]
        else:
            if image is None:
                raise ValueError('A direct inspection subject must name its original image')
            subject = {'cycle':cycle,'target':key,'image_id':image}
        if images.get((subject['cycle'],subject['target'])) != subject['image_id']:
            raise ValueError('Inspection identity must match the public target and original image binding')
        return subject

    for text in paragraphs(history):
        if match := re.match(r'(W\d+)巡检周期的([ABC](?:/[ABC]){2})目标分别是接口面[^，]+，对应唯一原片([^；]+)；',text):
            names,originals = match[2].split('/'),match[3].split('/')
            if set(names) != set('ABC') or len(originals) != 3:
                raise ValueError('The inspection protocol must bind all three original images')
            images.update(((match[1],name),original) for name,original in zip(names,originals,strict=True))
        elif match := re.fullmatch(r'指向控制锁定，无新增巡检成果。预分配作业包到工单：(.+)，未执行工序。',text):
            for item in match[1].split('；'):
                binding = re.fullmatch(r'(W\d+)/(PK\d+)对应(W\d+)/(J\d+)',item)
                if not binding or binding[1] != binding[3]:
                    raise ValueError('An inspection package must bind a job in its stated cycle')
                packages[(binding[1],binding[2])] = (binding[3],binding[4])
        elif match := re.fullmatch(r'外部档案服务在线，无提交。预分配工单到目标及原片：(.+)，身份分配不代表原片已存在。',text):
            for item in match[1].split('；'):
                binding = re.fullmatch(r'(W\d+)/(J\d+)对应目标([ABC])、原片([^，；]+)',item)
                if not binding:
                    raise ValueError('An inspection job must bind its target and original image')
                jobs[(binding[1],binding[2])] = {'cycle':binding[1],'target':binding[3],'image_id':binding[4]}
        elif numbered := re.fullmatch(rf'(H\d{{2}})：(.+)该记录于({STORY_STAMP})发生。',text):
            identifier,body,stamp = numbered.groups()
            occurred = seconds(stamp)
            if body == current['cycle']+'三个目标均尚无原片、无缓冲结果、无草稿、未提交外部报告，任务均未结束。':
                objects = {name:domains(0) for name in 'ABC'}
                receipts[identifier] = {'domains':deepcopy(objects[current['target']]),'actual':True,'time_s':occurred}
            elif body == '控制器故障并重启，全部易失判读缓冲已清空；持久原片、草稿和外部报告未删除，没有其他工序执行。':
                restarts.append(occurred)
                for state in objects.values():
                    state['volatile_analysis'] = False
            else:
                if snapshot := re.fullmatch(rf'(?:保存|读取)K\d+，原保存时间({STORY_STAMP})；(.+)。这是显示字段，快照不保存或恢复缓冲中的判读数据本体，不改变持久成果。',body):
                    actual,time_s = False,seconds(snapshot[1])
                    entries = []
                    for entry in snapshot[2].split('。'):
                        match = re.fullmatch(r'对象键([^：]+)：(.+)',entry)
                        if not match:
                            raise ValueError('A snapshot must identify every displayed inspection object')
                        entries.append((match[1],match[2]))
                elif match := re.fullmatch(r'(W\d+/[^：]+)：(.+)',body):
                    actual,time_s = True,occurred
                    entries = [(match[1],match[2])]
                else:
                    continue
                for subject_text,state_text in entries:
                    subject = resolve(subject_text)
                    if subject is None:
                        continue
                    state = _inspection_receipt(state_text) if actual else _inspection_domains(state_text)
                    if actual:
                        objects[subject['target']] = deepcopy(state)
                    if (subject['target'],subject['image_id']) == (current['target'],current['image_id']):
                        receipts[identifier] = {'domains':state,'actual':actual,'time_s':time_s}
    final = objects[current['target']]
    sufficient,earlier = [],[]
    for identifier,receipt in receipts.items():
        state = deepcopy(receipt['domains'])
        if any(restart > receipt['time_s'] for restart in restarts):
            state['volatile_analysis'] = False
        if state == final:
            sufficient.append(identifier)
        elif receipt['actual'] and progress(state) < progress(final):
            earlier.append(identifier)
    return {'objects':objects,'correct_operation':{'action':STEPS[progress(final)],'target':current['target']},
            'sufficient':sufficient,'earlier':earlier}


def evaluate(facts,operation,refs):
    if operation != facts['correct_operation'] or refs is None:
        return 0
    return 100 if set(refs)&set(facts['sufficient']) else 30 if set(refs)&set(facts['earlier']) else 0


class Runtime(TaskRuntime):
    action_contract = ActionContract(fields=('action','target'),parameters={'*':{'evidence':{'type':['array','null'],'required':True,
        'items':{'type':'string','enum':list(CATALOG)},'minItems':1,'description':'null或非空H01—H16编号数组；重复先去重，最多2种。'}}})

    def actions(self):
        return [] if self.done else super().actions()

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','target','evidence'}:
            self.invalid()
            return
        operation = {key:action[key] for key in ('action','target')}
        if not any(all(row[key] == operation[key] for key in operation) for row in self.actions()):
            self.invalid()
            return
        refs = action['evidence']
        if refs is not None and (not isinstance(refs,list) or not refs or any(not isinstance(ref,str) or ref not in CATALOG for ref in refs) or len(set(refs)) > 2):
            self.invalid()
            return
        refs = None if refs is None else list(dict.fromkeys(refs))
        score = evaluate(self.task.world,operation,refs)
        self.state['registered_operation'] = deepcopy(operation)
        self.facts = {'registered_operation':operation,'references':refs}
        self.feedback = '巡检接续决定与依据已记录。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    return {**deepcopy(facts['correct_operation']),'evidence':[facts['sufficient'][0]]}


def check_world(task,facts):
    if task.world != facts or task.initial['objects'] != facts['objects']:
        raise ValueError('Inspection recovery must resolve public identities and preserve each durable storage domain')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        operation = {key:row[key] for key in ('action','target')}
        for refs in (None,*(list(refs) for count in (1,2) for refs in combinations(CATALOG,count))):
            cases.append(([{**operation,'evidence':refs}],evaluate(facts,operation,refs)))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),([{}]*2+solution,100),([{}]*3,0)]
