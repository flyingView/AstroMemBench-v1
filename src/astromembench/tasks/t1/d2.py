"""FM-T1-D2: an entire exposure must fit one continuous periodic visible segment."""
import re

from ..common import ArchiveHistory, clock, ordered_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp

CONFIGS = (
    ('N1',600,1260,((60,240),),'L'),('N1',600,1380,((60,240),),'M'),
    ('N1',600,1420,((60,240),),'F'),('N1',600,1440,((60,240),),None),
    ('N2',600,1230,((60,240),),None),('N2',600,1381,((60,240),),'F'),
    ('N2',600,1350,((60,180),(240,480)),'F'),('N2',600,1500,((60,180),(300,480)),'L'),
    ('N3',600,1620,((60,180),(300,480)),'M'),('N1',600,1670,((60,180),(300,480)),None),
    ('N3',480,1080,((30,200),(260,440)),'M'),('N2',300,640,((40,160),(200,280)),'L'),
    ('N1',600,1320,((60,240),),'L'),('N1',600,1321,((60,240),),'M'),
    ('N1',300,760,((40,160),(170,290)),None),('N2',300,770,((40,160),(170,290)),'L'),
)
PROGRAMS = {'F':{'name':'快照','duration_s':20,'value':1},
            'M':{'name':'标准谱','duration_s':60,'value':2},
            'L':{'name':'深度谱','duration_s':120,'value':4}}


def _operation(target=None,program=None):
    return {'target':target,'program':program}


def build(index):
    target,period,delta,segments,best = CONFIGS[index]
    now = clock('12:00')
    models = {'N1':{'epoch_s':clock('11:40'),'period_s':600,'segments':[[0,180]]},
              'N2':{'epoch_s':clock('11:44'),'period_s':480,'segments':[[0,120]]},
              'N3':{'epoch_s':clock('11:50'),'period_s':300,'segments':[[0,60]]}}
    models[target] = {'epoch_s':now-delta,'period_s':period,'segments':[list(s) for s in segments]}
    history = ArchiveHistory(now)
    history.add(1,'Q8科学观测，N1/N2/N3各有独立已预置指向通道，定位、亮度、仪器与存储都满足。'
                '每目标可见性按其本轮参考历元t0、周期P和周期内可视片段精确重复，没有漂移；相位为当前与t0秒差模P。'
                '各片段含起点不含终点，曝光需现在起步且全过程在同一连续可视片段，完成恰在终点允许。'
                '读出耗时已另外预留；不可跨暗隙、截断、暂停拼接或等下一周期再开始，不可更换指定目标。'
                'F快照20秒价值1，M标准谱60秒价值2，L深度谱120秒价值4，均为独立完整且授权产品。'
                '目标是取得指定目标当前最大可实现科学价值，若无方案能完整曝光则保持载荷待机等后续调度。'
                '旧Q7、重新排版计划和指向准备不更新本轮几何预测。'
                '有效/无效提交总计3次，首个有效选择即实际曝光或待机并结束，不能预检、失败重拍或改选；end是放弃。'
                '推理和记忆检索不推进故事时钟，反馈仅给实际目标、方案与起止。',
                event='exposure_protocol',cycle='Q8',programs=PROGRAMS)

    def model_record(at,object_id,cycle,model,fields):
        fields = {key:model[key] for key in fields}
        descriptions = []
        if 'epoch_s' in fields:
            descriptions.append(f'参考历元{story_timestamp(fields["epoch_s"])}')
            fields['epoch_at'] = story_timestamp(fields['epoch_s'])
        if 'period_s' in fields:
            descriptions.append(f'周期{fields["period_s"]}秒')
        if 'segments' in fields:
            descriptions.append('可视片段'+','.join(f'[{a},{b})' for a,b in fields['segments'])+'秒，各端点距周期起点')
        history.add(at,f'{cycle}对象{object_id}，'+ '；'.join(descriptions)+'。',event='visibility_model',cycle=cycle,target=object_id,**fields)

    for object_id,model in models.items():
        if index < 6:
            model_record(4,object_id,'Q8',model,('epoch_s','period_s','segments'))
        else:
            for at,field in ((4,'epoch_s'),(14,'period_s'),(24,'segments')):
                model_record(at,object_id,'Q8',model,(field,))
        if index >= 12:
            model_record(8,object_id,'Q7',{'epoch_s':clock('11:40',119),'period_s':600,'segments':[[0,180]]},('epoch_s','period_s','segments'))
    if index >= 12:
        history.add(26,'重新排版观测计划完成，未改变本轮几何预测。',event='plan_reformatted')
        history.add(28,'三个目标均已完成指向准备。',event='pointing_ready')
    history.add(30,'计划生成，尚未曝光。',event='exposure_ready')
    group = f'FM-T1-D2-{target}'
    entries = [{'operation':_operation(object_id,code),
                'description':f'立即对{object_id}执行{p["name"]}，完整曝光{p["duration_s"]}秒，科学价值{p["value"]}。',
                'duration_s':p['duration_s'],'science_value':p['value']} for object_id in models for code,p in PROGRAMS.items()]
    entries.append({'operation':_operation(),'description':'保持载荷待机。','duration_s':0})
    task = task_shell('FM-T1-D2',index,current_input_group=group)
    task.public = {'time_s':now,'cycle':'Q8','target':target,'targets':list(models),'max_steps':3,'state_fields':[],
                   'instruction':f'第120日12:00:00，Q8科学目标{target}，指向和载荷就绪。请执行下一步观测操作。',
                   'actions':ordered_options(entries,group)}
    task.initial = {'time_s':now,'exposure':None}
    task.world = {'models':models,'best_program':best,'maximum_value':PROGRAMS[best]['value'] if best else 0}
    task.rubric = {'score':'100*complete_target_product_value/best_current_value; entire exposure must fit one segment; no feasible exposure requires standby'}
    return history.finish(task)


def _feasible(model,now,programs):
    phase = (now-model['epoch_s']) % model['period_s']
    return [code for code,p in programs.items() if any(a <= phase < b and phase+p['duration_s'] <= b for a,b in model['segments'])]


def _score(operation,target,model,now,programs):
    feasible = _feasible(model,now,programs)
    if operation['target'] is None:
        return 100 if not feasible else 0
    if operation['target'] != target or operation['program'] not in feasible:
        return 0
    return 100*programs[operation['program']]['value']/max(programs[code]['value'] for code in feasible)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        target,program = operation['target'],operation['program']
        now = self.state['time_s']
        if target is None:
            self.feedback = '载荷保持待机，未执行曝光。'
        else:
            self.state['time_s'] += PROGRAMS[program]['duration_s']
            self.state['exposure'] = {'target':target,'program':program,'started_s':now,'finished_s':self.state['time_s']}
            self.feedback = f'已对{target}执行{PROGRAMS[program]["name"]}，曝光从{story_timestamp(now)}至{story_timestamp(self.state["time_s"])}。'
        selected_target = self.task.public['target']
        return _score(operation,selected_target,self.task.world['models'][selected_target],now,PROGRAMS)


def reconstruct(history,current):
    models = {target:{} for target in current['targets']}
    programs = None
    cycle = re.escape(current['cycle'])
    for text in paragraphs(history):
        if text.startswith(f'{current["cycle"]}科学观测，'):
            programs = {code:{'name':name,'duration_s':int(duration),'value':int(value)}
                        for code,name,duration,value in re.findall(r'([FML])([^\d，。]+)(\d+)秒价值(\d+)',text)}
        record = re.fullmatch(rf'{cycle}对象(N\d+)，(.+)。',text)
        if record:
            model = models[record[1]]
            for field in record[2].split('；'):
                epoch = re.fullmatch(rf'参考历元({STORY_STAMP})',field)
                period = re.fullmatch(r'周期(\d+)秒',field)
                segments = re.fullmatch(r'可视片段(\[\d+,\d+\)(?:,\[\d+,\d+\))*)秒，各端点距周期起点',field)
                if epoch:
                    model['epoch_s'] = seconds(epoch[1])
                elif period:
                    model['period_s'] = int(period[1])
                elif segments:
                    model['segments'] = [list(map(int,pair)) for pair in re.findall(r'\[(\d+),(\d+)\)',segments[1])]
    if programs is None or set(programs) != {'F','M','L'} or any(set(m) != {'epoch_s','period_s','segments'} for m in models.values()):
        raise ValueError('Missing complete geometry models or exposure programs')
    feasible = _feasible(models[current['target']],current['time_s'],programs)
    best = max(feasible,key=lambda code:programs[code]['value'],default=None)
    return {'models':models,'programs':programs,'target':current['target'],'time_s':current['time_s'],
            'best_program':best,'maximum_value':programs[best]['value'] if best else 0}


def next_action(facts,current):
    return decision_command(current,_operation(current['target'],facts['best_program']) if facts['best_program'] else _operation())


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('models','best_program','maximum_value')):
        raise ValueError('Exposure optimum differs from target-specific continuous periodic visibility')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:_score(op,facts['target'],facts['models'][facts['target']],facts['time_s'],facts['programs']))
