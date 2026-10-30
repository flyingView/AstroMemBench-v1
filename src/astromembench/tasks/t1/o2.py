"""FM-T1-O2: substitutable adhesives have separate irreversible mixing clocks."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ((30,160,280),('AH',),4),((100,190,150),('CH',),4),((80,160,280),('AM','BM'),2),
    ((130,220,290),('AF',),1),((160,230,300),(),0),((50,100,175),('AH','BH','CH'),4),
    ((60,180,270),('AH',),4),((61,180,270),('AM','BM'),2),((120,181,270),('AM',),2),
    ((121,181,270),('AF','BF','CF'),1),((150,211,301),('AF',),1),((151,211,301),(),0),
    ((151,210,271),('BF',),1),((151,211,271),(),0),((60,120,180),('AH','BH','CH'),4),((181,180,180),('CH',),4),
)
LIFETIMES = {'A':180,'B':240,'C':300}
PROGRAMS = {'F':{'name':'快速点粘','duration_s':30,'value':1},
            'M':{'name':'标准覆盖','duration_s':60,'value':2},
            'H':{'name':'完整加固','duration_s':120,'value':4}}


def _operation(material=None,program=None):
    return {'material':material,'program':program}


def build(index):
    ages,best,value = CONFIGS[index]
    now = clock('12:00')
    mixed = {material:now-age for material,age in zip('ABC',ages,strict=True)}
    history = ArchiveHistory(now)
    history.add(1,'Q8维修点J补片已定位，支撑、隔离、清洁、尺寸、温度、胶料兼容性均保证。'
                'A/B/C三支同用途不同配方胶料可替代，但各自实际混合完成后适用期为180/240/300秒；全程规定温度，不暂停、不清零。'
                '计划混料、静置、装筒和重新装入胶枪都不重置，施工只用一支，不中途换胶或掺混。'
                'F快速点粘30秒形成价值1；M标准覆盖60秒价值2；H完整加固120秒价值4，均为已批准完整维修等级，不是省略强制步骤。'
                '整个方案完成须不晚于该胶混合时刻加适用期，恰等截止允许；已过期或途中到期都不能形成合格维修，设备速度固定。'
                '公开目标是最大化本次补片可实现维修价值，等价材料无偏好；无可行施工则保持定位并停止施胶。'
                '有效/无效提交共3次，首次有效选择后结束；施工选择立即真实开工、完整耗时和消耗所选胶料，不可预检过期或业务重试。'
                'end是放弃，记忆检索和真实推理不推进故事时间。适用期是题内假设，不是真实航天维修规程。',
                event='adhesive_protocol',cycle='Q8',lifetimes_s=LIFETIMES,programs=PROGRAMS,completion_inclusive=True)
    for position,(material,stamp) in enumerate(mixed.items()):
        history.add(4 if index < 6 else (4,14,24)[position],f'{story_timestamp(stamp)}，Q8胶料{material}实际混合完成。',
                    occurred=stamp,event='adhesive_mixed',cycle='Q8',material=material,mixed_s=stamp,mixed_at=story_timestamp(stamp))
        if index >= 12:
            old = clock('11:59',119)
            history.add(8,f'{story_timestamp(old)}，旧Q7胶料{material}实际混合完成。',occurred=old,
                        event='adhesive_mixed',cycle='Q7',material=material,mixed_s=old,mixed_at=story_timestamp(old))
    if 6 <= index < 12:
        history.add(27,'第120日11:59:20所有胶料装筒完成，未混入新料。',occurred=clock('11:59:20'),event='cartridge_loaded')
    if index >= 12:
        history.add(20,'第120日11:59:05建议另配一组新料，未批准、未开始。',occurred=clock('11:59:05'),event='new_mix_proposed')
        history.add(28,'Q8胶枪安装就绪，没有混料。',event='gun_installed')
    history.add(30,'补片定位完毕，施工计划生成，尚未施胶。',event='repair_ready')
    entries = [{'operation':_operation(material,code),
                'description':f'用{material}执行{program["name"]}，耗时{program["duration_s"]}秒，维修价值{program["value"]}。',
                'duration_s':program['duration_s'],'repair_value':program['value']}
               for material in mixed for code,program in PROGRAMS.items()]
    entries.append({'operation':_operation(),'description':'保持补片定位并停止施胶。','duration_s':0})
    task = task_shell('FM-T1-O2',index,current_input_group='FM-T1-O2')
    task.public = {'time_s':now,'cycle':'Q8','repair_site':'J','materials':list(mixed),'max_steps':3,'state_fields':[],
                   'instruction':'第120日12:00:00，Q8维修点J，A/B/C胶枪与补片就绪，未开始施工，请执行下一步。',
                   'actions':ordered_options(entries,'FM-T1-O2')}
    task.initial = {'time_s':now,'material_consumed':{m:False for m in mixed},'applied_repair':None}
    task.world = {'mixed_s':mixed,'best_operations':[_operation(code[0],code[1]) for code in best],'maximum_value':value}
    task.rubric = {'score':'100*feasible_repair_value/best_current_value, all equal-value feasible materials accepted; no feasible action requires stopping'}
    return history.finish(task)


def _feasible(mixed,now,lifetimes,programs):
    return [(m,p) for m,t in mixed.items() for p,program in programs.items() if now+program['duration_s'] <= t+lifetimes[m]]


def _score(operation,mixed,now,lifetimes,programs):
    feasible = _feasible(mixed,now,lifetimes,programs)
    if operation['material'] is None:
        return 100 if not feasible else 0
    if (operation['material'],operation['program']) not in feasible:
        return 0
    return 100*programs[operation['program']]['value']/max(programs[p]['value'] for _,p in feasible)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        now = self.state['time_s']
        material,program = operation['material'],operation['program']
        if material is None:
            self.feedback = '保持补片定位，未执行施胶。'
        else:
            self.state['time_s'] += PROGRAMS[program]['duration_s']
            self.state['material_consumed'][material] = True
            self.state['applied_repair'] = {'material':material,'program':program,'started_s':now,'finished_s':self.state['time_s']}
            self.feedback = f'Q8维修点J已使用胶料{material}执行{PROGRAMS[program]["name"]}，完成于{story_timestamp(self.state["time_s"])}。'
        return _score(operation,self.task.world['mixed_s'],now,LIFETIMES,PROGRAMS)


def reconstruct(history,current):
    mixed,lifetimes,programs = {},None,None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        if text.startswith(f'{current["cycle"]}维修点{current["repair_site"]}补片已定位'):
            lifetime = re.search(r'([A-Z/]+)三支同用途不同配方胶料可替代，但各自实际混合完成后适用期为([\d/]+)秒',text)
            if lifetime:
                lifetimes = dict(zip(lifetime[1].split('/'),map(int,lifetime[2].split('/')),strict=True))
            programs = {code:{'name':name,'duration_s':int(duration),'value':int(value)}
                        for code,name,duration,value in re.findall(r'([FMH])([^\d；。]+)(\d+)秒(?:形成)?价值(\d+)',text)}
        receipt = re.search(rf'({STORY_STAMP})，{cycle}胶料([A-Z])实际混合完成。',text)
        if receipt:
            mixed[receipt[2]] = seconds(receipt[1])
    if set(mixed) != set(current['materials']) or lifetimes is None or programs is None or set(programs) != {'F','M','H'}:
        raise ValueError('Missing actual current adhesive mixing times or physical model')
    mixed = {m:mixed[m] for m in current['materials']}
    feasible = _feasible(mixed,current['time_s'],lifetimes,programs)
    value = max((programs[p]['value'] for _,p in feasible),default=0)
    best = [_operation(m,p) for m,p in feasible if programs[p]['value'] == value]
    return {'mixed_s':mixed,'lifetimes_s':lifetimes,'programs':programs,'best_operations':best,'maximum_value':value,'time_s':current['time_s']}


def next_action(facts,current):
    return decision_command(current,facts['best_operations'][0] if facts['best_operations'] else _operation())


def check_world(task,facts):
    if any(facts[key] != task.world[key] for key in ('mixed_s','best_operations','maximum_value')):
        raise ValueError('Repair optimum differs from independent material completion deadlines')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['mixed_s'],facts['time_s'],facts['lifetimes_s'],facts['programs']))
