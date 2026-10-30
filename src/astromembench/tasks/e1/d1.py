"""FM-E1-D1: match a verified cyclic irradiation pattern and illuminated face."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs
from ...schema import story_timestamp

# Full programs, partial programs, accepted minutes, archive order; all indexed by face/pattern.
BOOKS = (
    ((6,1,10,3,8,12),(4,9,2,11,5,7),(4,2,4,2,4,2),(4,1,6,2,5,3)),
    ((11,5,2,9,4,7),(3,12,8,1,10,6),(2,4,2,4,2,4),(2,5,3,6,1,4)),
    ((2,8,5,12,7,1),(9,3,11,4,6,10),(4,4,2,2,4,2),(6,3,1,5,4,2)),
    ((9,4,12,6,1,8),(7,10,3,2,11,5),(2,4,4,2,2,4),(3,5,2,4,6,1)),
    ((5,11,7,2,10,4),(1,6,12,8,3,9),(4,2,4,4,2,2),(1,4,5,3,2,6)),
    ((12,3,8,10,6,2),(4,7,1,5,9,11),(2,4,2,4,4,2),(5,6,4,1,3,2)),
    ((7,10,4,1,12,6),(2,5,9,3,8,11),(4,2,2,4,2,4),(2,4,1,6,3,5)),
    ((1,6,11,8,3,9),(10,2,5,12,7,4),(2,4,4,2,4,2),(6,2,5,1,4,3)),
)
CYCLES = (('001111','011110','111100','111001','110011','100111'),
          ('010111','101110','011101','111010','110101','101011'),('011011','110110','101101'))
START_MINUTES = (0,432,864,1080,1512,1944)
# Book, face, current sequence, frequent/latest programs, full/partial/actual partial count.
CONFIGS = (
    (1,'X','001111',6,6,6,4,4),(1,'X','111010',9,12,1,9,2),(1,'Y','110110',12,7,12,7,2),
    (2,'Y','111100',1,2,9,1,4),(2,'X','101101',2,8,2,8,2),(3,'Y','011101',7,6,7,6,4),
    (4,'X','011110',9,9,9,7,2),(4,'X','110101',10,8,4,10,4),(4,'Y','101101',8,5,8,5,4),
    (5,'X','011011',7,7,7,12,4),(5,'Y','101110',3,5,10,3,2),(6,'Y','100111',10,10,10,5,4),
    (7,'X','110110',4,9,4,9,2),(7,'Y','111001',12,1,1,3,4),(8,'X','010111',6,6,6,2,4),(8,'Y','101101',4,1,9,4,2),
)


def _program(p):
    return f'T{p:02d}'


def _canonical(sequence):
    return min(sequence[i:]+sequence[:i] for i in range(len(sequence)))


def _table(face,sequence,results):
    return {'face':face,'cycle':_canonical(sequence),'results':results}


def build(index):
    book,face,sequence,frequent,recent,correct,partial,partial_count = CONFIGS[index]
    full,partials,counts,archive = BOOKS[book-1]
    history = History()
    history.add(1,'平台受照面为X或Y；每位1表示300W/m²，0表示100W/m²，每位持续1分钟，六位按时间顺序循环。'
                '六位总有四高两低、平均700/3W/m²，但任意重排不等价。所有相位均已经实际测试：同一序列的循环平移，'
                '在同一受照面、同一程序下得到相同合格分钟数。预置内置自动相位同步，不需手动算启动相位。'
                '不同面和形态的经验分别持续有效，不因新记录撤销。设备健康、构型能源不变；当前周期由传感器测明，后续按确认周期重复。'
                'T01—T12编号无性能顺序，均运行完整6分钟采集，每分钟一份等权数据，仅热稳指标合格的分钟验收。'
                '内部保护使不合格分钟不损伤设备、不阻断后续采集；不允许中途切换。有效无效共3次，首合法选择原子执行后结束，end放弃。'
                '推理与记忆检索不推进故事时间。',event='cyclic_cruise_protocol')
    history.add(2,'各次试验使用相同健康平台，十二程序能耗相等且资源充分；独立重置后运行，不遗留前次热态。',event='cruise_trial_resources')
    tables = []
    layout = 'combined' if index < 6 else 'same_round' if index < 12 else 'previous_round'
    for at,condition_number,job in zip((4,7,10,13,16,19),archive,('W31','W08','W24','W05','W17','W12'),strict=True):
        slot = condition_number-1
        trial_face = 'X' if slot < 3 else 'Y'
        cycles = list(CYCLES[slot%3])
        results = [{'program':_program(p),'accepted_minutes':6 if p == full[slot] else counts[slot] if p == partials[slot] else 0} for p in range(1,13)]
        tables.append(_table(trial_face,cycles[0],results))
        start = clock('00:00',116)+START_MINUTES[slot]*60
        finish = start+len(cycles)*12*360
        condition = {'job':job,'face':trial_face,'measured_cycles':cycles,'batch_started_s':start}
        result = {'job':job,'results':results,'all_listed_cycles_tested':True,'batch_started_s':start,'batch_finished_s':finish,
                  'trial_seconds':360,'order':'按关联工况中所列不同六位序列顺序，每序列依T01—T12各独立运行6分钟'}
        description = f'受照面{trial_face}，完整六位序列'+ '、'.join(cycles)
        measured = '；'.join(f'{row["program"]}合格{row["accepted_minutes"]}分钟' for row in results)
        text = f'{job}：已实际测试所列全部不同循环平移，各序列的十二程序实际合格分钟数均为：{measured}。'
        text += f'{story_timestamp(start)}开始至{story_timestamp(finish)}完成，每项独立6分钟，按上述序列顺序，每序列依T01—T12测试。'
        if layout == 'combined':
            history.add(at,description+'；'+text,occurred=finish,event='cruise_trial_batch',**condition,**{k:v for k,v in result.items() if k not in condition})
        else:
            history.add(at-1 if layout == 'previous_round' else at,f'{job}的已完成试验工况：{description}。',
                        occurred=start,event='cruise_batch_condition',**condition)
            history.add(at,text,occurred=finish,event='cruise_batch_results',**result)
    for position,(at,preset,job) in enumerate(zip((22,24,26,29),(frequent,frequent,frequent,recent),('J41','J36','J43','J38'),strict=True)):
        slot = full.index(preset) if preset in full else partials.index(preset)
        trial_face = 'X' if slot < 3 else 'Y'
        cycle = CYCLES[slot%3][0]
        accepted = 6 if preset in full else counts[slot]
        start = clock('12:00',119)+position*720
        history.add(at,f'{job}：受照面{trial_face}，六位序列{cycle}，{_program(preset)}从{story_timestamp(start)}独立运行6分钟，'
                    f'{story_timestamp(start+360)}完成，实际{accepted}分钟热稳合格，其他分钟仍完成采集但未验收。',
                    occurred=start+360,event='cruise_trial',job=job,face=trial_face,cycle=cycle,program=_program(preset),
                    accepted_minutes=accepted,started_s=start,finished_s=start+360)
    history.add(30,'09:00开始的六分钟普通巡航采集已排入本机队列，等待届时实际测得的环境与程序选择。',event='cruise_queued')
    task = task_shell('FM-E1-D1',index)
    readings = [{'time_s':clock('08:54')+i*60,'irradiance_w_m2':300 if bit == '1' else 100} for i,bit in enumerate(sequence)]
    task.public = {'time_s':clock('09:00'),'face':face,'irradiance_readings':readings,'cycle_bits':sequence,
                   'repeat_confirmed':True,'repeat_interval_s':[clock('09:00'),clock('09:06')],'equipment_ready':True,
                   'required_data':6,'max_steps':3,'state_fields':[],
                   'instruction':f'第120日09:00，受照面{face}，08:54—08:59按时间测得六位读数{sequence}。'
                   '系统确认09:00—09:05按相同次序逐分钟重复，设备正常，目标六份普通巡航数据。请选择本段保障程序。',
                   'actions':fixed_options([{'operation':{'program':_program(p)},'description':f'启动{_program(p)}预置保障程序，运行6分钟并完成普通巡航采集。'} for p in range(1,13)])}
    accepted = {_program(p):6 if p == correct else partial_count if p == partial else 0 for p in range(1,13)}
    task.initial = {'time_s':clock('09:00'),'data':[],'accepted_minutes':0,'program':None}
    task.world = {'tables':sorted(tables,key=lambda r:(r['face'],r['cycle'])),'accepted_minutes':accepted}
    task.rubric = {'score':'100 times the empirically accepted cruise minutes divided by 6; all six minutes are always collected'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        self.state['program'] = operation['program']
        for i,bit in enumerate(self.task.public['cycle_bits']):
            self.state['data'].append({'minute':i+1,'started_s':self.state['time_s'],'finished_s':self.state['time_s']+60,
                                      'face':self.task.public['face'],'irradiance_w_m2':300 if bit == '1' else 100,'collected':True})
            self.state['time_s'] += 60
        # The measured contract specifies a count, not which individual minute passes.
        accepted = self.task.world['accepted_minutes'][operation['program']]
        self.state['accepted_minutes'] = accepted
        self.feedback = '操作已执行，记录已存档。'
        return 100*accepted/6


def reconstruct(history,current):
    conditions,results,repeats = {},{},[]
    for text in paragraphs(history):
        batch = re.search(r'(W\d+)(?:的已完成试验工况：|：已实际测试)',text)
        if batch:
            job = batch[1]
            condition = re.search(r'受照面([XY])，完整六位序列([01、]+)',text)
            if condition:
                conditions[job] = {'face':condition[1],'measured_cycles':condition[2].split('、')}
            measured = re.search(r'已实际测试所列全部不同循环平移，各序列的十二程序实际合格分钟数均为：(.+?)。',text)
            if measured:
                rows = []
                for entry in measured[1].split('；'):
                    value = re.fullmatch(r'(T\d+)合格(\d+)分钟',entry)
                    if not value:
                        raise ValueError('Missing actual cruise acceptance count in prose')
                    rows.append({'program':value[1],'accepted_minutes':int(value[2])})
                if [r['program'] for r in rows] != [_program(p) for p in range(1,13)]:
                    raise ValueError('Cruise prose must contain each measured program including zero outcomes')
                results[job] = {'all_listed_cycles_tested':True,'results':rows}
        repeat = re.fullmatch(rf'J\d+：受照面([XY])，六位序列([01]{{6}})，(T\d+)从{STORY_STAMP}独立运行6分钟，'
                              rf'{STORY_STAMP}完成，实际(\d+)分钟热稳合格，其他分钟仍完成采集但未验收。',text)
        if repeat:
            repeats.append({'face':repeat[1],'cycle':repeat[2],'program':repeat[3],'accepted_minutes':int(repeat[4])})
    if conditions.keys() != results.keys():
        raise ValueError('Cyclic trial jobs must join the full tested domain and actual program counts')
    tables,lookup = [],{}
    for job,condition in conditions.items():
        cycles = condition['measured_cycles']
        complete = {cycles[0][i:]+cycles[0][:i] for i in range(6)}
        if set(cycles) != complete or not results[job]['all_listed_cycles_tested']:
            raise ValueError('Cycle equivalence requires the actual complete rotation domain')
        result = results[job]['results']
        tables.append(_table(condition['face'],cycles[0],result))
        for row in result:
            lookup[(condition['face'],_canonical(cycles[0]),row['program'])] = row['accepted_minutes']
    for r in repeats:
        if lookup[(r['face'],_canonical(r['cycle']),r['program'])] != r['accepted_minutes']:
            raise ValueError('Repeat changed a stable cyclic experiment')
    pattern = ''.join('1' if r['irradiance_w_m2'] == 300 else '0' for r in current['irradiance_readings'])
    if pattern != current['cycle_bits']:
        raise ValueError('Current measured irradiance must agree with its displayed sequence')
    accepted = {_program(p):lookup[(current['face'],_canonical(pattern),_program(p))] for p in range(1,13)}
    return {'tables':sorted(tables,key=lambda r:(r['face'],r['cycle'])),'accepted_minutes':accepted}


def next_action(facts,current):
    program = next(p for p,n in facts['accepted_minutes'].items() if n == 6)
    return decision_command(current,{'program':program})


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Cruise acceptance differs from public face/cyclic-pattern experiments')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*facts['accepted_minutes'][op['program']]/6)
