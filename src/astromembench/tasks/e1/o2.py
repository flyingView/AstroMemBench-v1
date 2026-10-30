"""FM-E1-O2: preserve every certified closed repair interval and every valid choice."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Material, medium, exact current temperature, A/B/C/D/E/F programs, repeated/latest scope, full set.
CONFIGS = (
    ('E','V',-20,(3,8,11,5,1,9),'A','A',(3,)),
    ('E','V',0,(3,8,11,5,1,9),'D','B',(3,8)),
    ('E','V',30,(7,2,10,12,4,6),'A','C',(10,)),
    ('E','G',-10,(9,5,1,8,11,3),'A','E',(11,)),
    ('E','V',10,(12,6,3,9,2,8),'C','B',(6,3)),
    ('E','V',-6,(1,9,7,4,10,5),'B','A',(1,)),
    ('E','V',-1,(8,4,12,6,3,10),'A','B',(8,4)),
    ('E','V',1,(8,4,12,6,3,10),'A','B',(4,)),
    ('M','G',-20,(6,1,9,3,12,8),'F','D',(8,)),
    ('E','V',9,(10,7,2,11,5,4),'B','C',(7,)),
    ('E','V',10,(10,7,2,11,5,4),'C','B',(7,2)),
    ('E','V',16,(5,12,8,1,6,9),'B','C',(8,)),
    ('E','V',14,(3,6,12,8,1,11),'C','B',(6,12)),
    ('E','V',16,(3,6,12,8,1,11),'B','C',(12,)),
    ('M','V',-5,(12,5,1,9,6,3),'B','D',(9,)),
    ('E','V',-5,(12,5,1,9,6,3),'D','A',(12,5)),
)
RANGES = (
    ('E','V',-20,0,-10),('E','V',-5,15,5),('E','V',10,30,20),
    ('M','V',-20,30,0),('E','G',-20,30,5),('M','G',-20,30,5),
)


def _condition(material,medium):
    return {'material':material,'material_name':{'E':'弹性密封','M':'金属密封'}[material],
            'medium':medium,'medium_name':{'V':'真空','G':'惰性气体'}[medium]}


def _covers(certificate,condition,temperature):
    return certificate['condition'] == condition and certificate['temperature_interval_c'][0] <= temperature <= certificate['temperature_interval_c'][1]


def build(index):
    material,medium,temperature,programs,frequent,recent,full = CONFIGS[index]
    history = History()
    history.add(1,'合成密封工艺模型：材料E为弹性密封、M为金属密封；介质V为真空、G为惰性气体，温度单位摄氏度。'
                '历史认证表示在整个明确温度区间完成规定试验并通过，不是仅测两个端点后的内插。温区是闭区间，两端包含。'
                '必须同时匹配材料、介质和温度，覆盖当前条件的任一已验证工艺都能完整修复4个检漏点。'
                '不同工况的认证并存，始终有效；后来单点成功不缩窄完整范围，也不撤销其他工艺。未覆盖当前工况者不能验收，得0点。'
                'R1—R12都是可执行原子预置，包含夹持、施胶或紧固、检查，编号无冷热或优劣顺序。'
                '设备与连接就绪，仅评价经验选择；每种工艺10分钟，没有中途改选。有效无效共3次，首合法选择执行后结束，end放弃。'
                '推理和记忆检索不推进故事时间。',event='repair_experience_protocol')
    certificates = []
    layout = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'
    for scope,(at,program,(mat,gas,lower,upper,_)) in enumerate(zip((3,7,11,15,19,23),programs,RANGES,strict=True)):
        job = 'Q'+'ABCDEF'[scope]
        condition = _condition(mat,gas)
        completed = clock(f'08:{at:02d}',119)
        certificate = {'program':f'R{program}','condition':condition,'temperature_interval_c':[lower,upper],'accepted_points':4}
        certificates.append(certificate)
        scope_text = f'{condition["material_name"]}{mat}、{condition["medium_name"]}{gas}'
        result_text = f'工艺R{program}已通过整个闭温区[{lower},{upper}]℃规定验证，4个检漏点全部合格，完整范围持续有效；报告于{story_timestamp(completed)}完成。'
        if layout == 'combined':
            history.add(at,f'{job}：{scope_text}，{result_text}',occurred=completed,event='repair_certificate',job=job,
                        report_completed_s=completed,**certificate)
        else:
            history.add(at-1 if layout == 'previous_round' else at,f'{job}：登记已完成验证报告的材料和介质为{scope_text}。',
                        occurred=completed,event='repair_certificate_condition',job=job,condition=condition,report_completed_s=completed)
            history.add(at,f'{job}：{result_text}',occurred=completed,event='repair_certificate_result',job=job,program=f'R{program}',
                        temperature_interval_c=[lower,upper],accepted_points=4,report_completed_s=completed)
    for position,(at,reference,job) in enumerate(zip((24,26,28,29),(frequent,frequent,frequent,recent),('J41','J36','J43','J38'),strict=True)):
        scope = 'ABCDEF'.index(reference)
        certificate = certificates[scope]
        point = RANGES[scope][4]
        start = clock('12:00',119)+position*1200
        finish = start+600
        condition = certificate['condition']
        history.add(at,f'{job}：第119日的独立维修，{condition["material_name"]}、{condition["medium_name"]}、{point}℃，'
                    f'执行{certificate["program"]}，{story_timestamp(start)}开始，{story_timestamp(finish)}完成，4个检漏点全部合格。',
                    occurred=finish,event='repair_trial',job=job,program=certificate['program'],condition=condition,temperature_c=point,
                    started_s=start,finished_s=finish,accepted_points=4)
    history.add(30,'当前维修件已到位，材料、介质和温度已测得；工装正常、连接完成。',event='seal_ready')
    task = task_shell('FM-E1-O2',index)
    current = _condition(material,medium)
    task.public = {'time_s':clock('09:00'),'condition':current,'temperature_c':temperature,'required_points':4,'equipment_ready':True,
                   'max_steps':3,'state_fields':[],'instruction':f'第120日09:00，当前{current["material_name"]}{material}、'
                   f'{current["medium_name"]}{medium}、精确温度{temperature}℃，需修复4个检漏点，设备和连接已就绪。请选择下一步操作。',
                   'actions':fixed_options([{'operation':{'program':f'R{p}'},'description':f'执行工艺R{p}修复当前密封。'} for p in range(1,13)])}
    task.initial = {'time_s':clock('09:00'),'repairs':[]}
    task.world = {'certificates':sorted(certificates,key=lambda r:int(r['program'][1:])),
                  'valid_programs':[f'R{p}' for p in sorted(full)]}
    task.rubric = {'score':'100 for every certified material/medium/closed interval covering the exact current temperature; otherwise zero'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        program = operation['program']
        accepted = program in self.task.world['valid_programs']
        start = self.state['time_s']
        self.state['time_s'] += 600
        self.state['repairs'].append({'program':program,'condition':self.task.public['condition'],'temperature_c':self.task.public['temperature_c'],
                                      'started_s':start,'finished_s':self.state['time_s'],
                                      'points':[{'point':f'L{i}','repair_performed':True,'accepted':accepted} for i in range(1,5)]})
        self.feedback = '操作已执行，记录已存档。'
        return 100 if accepted else 0


def _read_condition(text):
    match = re.fullmatch(r'(弹性密封|金属密封)([EM]?)、(真空|惰性气体)([VG]?)',text)
    if not match:
        raise ValueError('Missing repair material and medium in prose')
    material = {'弹性密封':'E','金属密封':'M'}[match[1]]
    medium = {'真空':'V','惰性气体':'G'}[match[3]]
    if match[2] not in ('',material) or match[4] not in ('',medium):
        raise ValueError('Repair material or medium code disagrees with its name')
    return {'material':material,'material_name':match[1],'medium':medium,'medium_name':match[3]}


def reconstruct(history,current):
    conditions,results,repeats = {},{},[]
    for text in paragraphs(history):
        record = re.fullmatch(r'(Q[A-F])：(.+)',text)
        if record:
            job,body = record.groups()
            condition = re.fullmatch(r'登记已完成验证报告的材料和介质为(.+)。',body)
            if condition:
                conditions[job] = _read_condition(condition[1])
                continue
            result = re.fullmatch(rf'(?:(.+)，)?工艺(R\d+)已通过整个闭温区\[(-?\d+),(-?\d+)\]℃规定验证，'
                                  rf'(\d+)个检漏点全部合格，完整范围持续有效；报告于({STORY_STAMP})完成。',body)
            if result:
                if result[1]:
                    conditions[job] = _read_condition(result[1])
                results[job] = {'program':result[2],'temperature_interval_c':[int(result[3]),int(result[4])],'accepted_points':int(result[5])}
        repeat = re.fullmatch(rf'J\d+：第\d+日的独立维修，(.+)、(-?\d+)℃，执行(R\d+)，'
                              rf'{STORY_STAMP}开始，{STORY_STAMP}完成，(\d+)个检漏点全部合格。',text)
        if repeat:
            repeats.append({'condition':_read_condition(repeat[1]),'temperature_c':int(repeat[2]),
                            'program':repeat[3],'accepted_points':int(repeat[4])})
    if conditions.keys() != results.keys():
        raise ValueError('Every repair report must join its material/medium and complete interval results')
    certificates = sorted(({**result,'condition':conditions[job]} for job,result in results.items()),key=lambda r:int(r['program'][1:]))
    if any(r['accepted_points'] != 4 or r['temperature_interval_c'][0] > r['temperature_interval_c'][1] for r in certificates):
        raise ValueError('Repair certificates must describe an actually validated complete closed interval')
    for repeat in repeats:
        if repeat['accepted_points'] != 4 or not any(r['program'] == repeat['program'] and _covers(r,repeat['condition'],repeat['temperature_c']) for r in certificates):
            raise ValueError('Single-point repeat contradicts its stable complete certification')
    valid = [r['program'] for r in certificates if _covers(r,current['condition'],current['temperature_c'])]
    return {'certificates':certificates,'valid_programs':valid}


def next_action(facts,current):
    return decision_command(current,{'program':facts['valid_programs'][0]})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Repair acceptance must preserve all publicly certified matching programs')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100 if op['program'] in facts['valid_programs'] else 0)
