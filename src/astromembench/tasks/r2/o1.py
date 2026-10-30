"""FM-R2-O1: reserve only uncompleted, uncancelled mandatory inspection units."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

LEVELS = (5,1,8,0,4,9,2,6,3,7)
# Per batch: total units, unit cost, actual completion order, cancellations, draft, forwarded unit.
CONFIGS = (
    ((7,5,(),(),None,None),None),((8,4,(),(),None,None),None),
    ((5,4,(),(),None,None),None),((7,2,(),(),None,None),None),
    ((8,5,(6,),(),None,None),None),((8,4,(2,7),(),None,None),None),
    ((6,3,(2,5),(),None,None),(4,2,(4,),(),None,None)),
    ((7,3,(2,7,1,5),(),None,None),(6,2,(6,3),(),None,None)),
    ((7,4,(6,1,4,7),(),None,None),(6,3,(2,6,3),(),None,None)),
    ((8,5,(8,2,5),(),None,None),(5,2,(3,5),(),None,None)),
    ((6,4,(5,2,6,3),(),None,None),(5,5,(4,1,5),(),None,None)),
    ((5,2,(5,1,4,2),(),None,None),(6,3,(6,2,4),(),None,None)),
    ((8,4,(7,2),(4,8),1,7),(6,3,(6,2),(4,),1,None)),
    ((6,5,(6,3),(1,),5,3),(6,2,(5,2,6),(3,),1,None)),
    ((7,4,(6,1,4,7),(3,),5,6),(6,3,(5,2,6),(1,),4,None)),
    ((8,4,(8,3),(6,),2,8),(7,3,(7,2),(4,),1,None)),
)
BATCHES = (('U','天线转向机构外表面',0,4,18),('V','展开支架接点',1,9,22))


def reserved_energy(batches,stage,priority):
    return sum(batch['unit_energy']*sum(status == 'pending' for status in batch['units'].values())
        for batch in batches.values() if batch['stage'] == stage and batch['priority'] < priority)


def build(index):
    rows = CONFIGS[index]
    battery = 40+sum(row[1]*len(row[2]) for row in rows if row)
    entries = [{'description':f'精查{level}个Q单元，耗电{2+3*level if level else 0}。',
                'operation':{'level':level,'energy':2+3*level if level else 0,'yield':level}} for level in LEVELS]
    history = History()
    history.add(1,'阶段I5，当前目标Q精查优先级2。先保证剩余高优必检单元，再尽可能多完成本次Q独立等价值精查单元。'
        '优先级数字越小越高；U/V为另两个目标的必检清单，固定部位ID不是访问次序，自动视角可先检查高编号。'
        '每个ID仅需成功检查一次，批内各ID同价，单价已包含自动定位路径；没有跨单元共享启动费。'
        '实际检查完成才扣单价并移出待检，转发同一回执不重复检查或扣款。正式取消此前未执行的ID不扣电且解除该ID需求。'
        '计划与预填完成栏都尚未检查、不扣款，仍须保留需求；已完和取消ID互斥。低优X可顺延，不减少Q产出。'
        '无补能，基础平台能耗另行保障。剩余高优单元由固定流程09:20后执行，本次精查09:10前结束，没有时间冲突。'
        '当前Q是独立新目标，历史U/V检查不计Q产出。Q档位0—9各完成j个单元；0档不执行、不扣款，正档只收本次启动2及每单元3。'
        '十项完整菜单的费用与产出如下，均可用当前电量执行；挤占未来必检预算也照常精查、扣费并终止，不可重选。'
        '严格提交select及字符串option，或end；全部有效、无效与end合计最多3次，首次有效选择或end即结束，解释不计分。',
        event='inspection_reserve_protocol',stage='I5',current_priority=2,
        current_complete_before_s=clock('09:10'),programs=[entry['operation'] for entry in entries])
    history.add(2,f'本阶段起始电量读数{battery}。',event='inspection_reserve_initial',battery=battery)
    batches,receipts = {},{}
    for at in range(3,31):
        for row,(code,title,priority,register_at,complete_at) in zip(rows,BATCHES,strict=True):
            if row is None:
                continue
            total,cost,completed,cancelled,draft,forwarded = row
            if at == register_at:
                unit_ids = [f'{code}{i}' for i in range(1,total+1)]
                fields = {'batch':code,'title':title,'stage':'I5','priority':priority,'unit_energy':cost,'unit_ids':unit_ids}
                batches[code] = {**fields,'units':dict.fromkeys(unit_ids,'pending')}
                history.add(at,f'I5阶段{code}清单「{title}」正式登记，优先级{priority}，每单元确定耗电{cost}；完整部位ID为'+','.join(unit_ids)+'。',
                    event='inspection_batch_registered',**fields)
            if at == complete_at:
                for number in completed:
                    unit = f'{code}{number}'
                    before = battery
                    battery -= cost
                    batches[code]['units'][unit] = 'completed'
                    receipt = f'R{at:02d}-{unit}'
                    fields = {'event':'inspection_unit_completed','receipt_id':receipt,'batch':code,'unit':unit,'stage':'I5',
                        'energy':cost,'battery_before':before,'battery_after':battery}
                    occurred = clock(f'08:{at:02d}:{len(history.events[at-1].records):02d}')
                    receipts[unit] = (receipt,occurred,fields)
                    history.add(at,f'I5单元{unit}已实际检查完成，独立回执{receipt}，扣{cost}，余额从{before}变为{battery}。',
                        record_id=receipt,**fields)
            if at == 25:
                for number in cancelled:
                    unit = f'{code}{number}'
                    batches[code]['units'][unit] = 'cancelled'
                    history.add(at,f'正式取消I5单元{unit}复检；该单元此前未执行，不扣款，不再要求检查。',
                        event='inspection_unit_cancelled',stage='I5',batch=code,unit=unit)
            if at == 27 and forwarded is not None:
                receipt,occurred,fields = receipts[f'{code}{forwarded}']
                history.add(at,f'转发原执行回执{receipt}，保留原执行时刻和原扣款记录；仅转发，不是新检查、没有新增扣电。',
                    occurred=occurred,forwarded=True,**fields)
            if at == 28 and draft is not None:
                history.add(at,f'I5单元{code}{draft}仅预填完成栏，尚未实际执行或扣电，仍待检查。',
                    event='inspection_completion_draft',stage='I5',batch=code,unit=f'{code}{draft}',executed=False)
        if at == 16:
            history.add(at,'低优X登记于I5，优先级4、费用8，可顺延，不减少当前Q精查。',
                event='optional_inspection_registered',stage='I5',id='X',priority=4,energy=8)
    history.add(30,'当前目标Q精查设备正常。',event='current_inspection_ready',target='Q')
    task = task_shell('FM-R2-O1',index,current_input_group='FM-R2-O1')
    task.public = {'instruction':'选择目标Q的精查规模。','time_s':clock('09:00'),'stage':'I5','priority':2,'target':'Q',
        'max_steps':3,'state_fields':['battery','inspected_units'],'actions':fixed_options(entries)}
    task.initial = {'time_s':clock('09:00'),'battery':battery,'inspected_units':[]}
    task.world = {'batches':batches}
    task.rubric = {'metric':'inspection_yield_after_remaining_mandatory_units','range':[0,100]}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def execute(self,operation):
        reserve = reserved_energy(self.task.world['batches'],self.task.public['stage'],self.task.public['priority'])
        available = self.task.initial['battery']-reserve
        maximum = max(r['operation']['yield'] for r in self.task.public['actions'] if r['operation']['energy'] <= available)
        self.state['battery'] -= operation['energy']
        self.state['inspected_units'] = [f'Q{i}' for i in range(1,operation['yield']+1)]
        self.feedback = '精查程序已执行，作业记录已存档。'
        return 0 if self.state['battery'] < reserve else 100*operation['yield']/maximum


def reconstruct(history,current):
    batches,battery,receipts = {},None,{}
    for text in paragraphs(history):
        if match := re.fullmatch(r'本阶段起始电量读数(\d+)。',text):
            battery = int(match[1])
        elif match := re.fullmatch(r'([A-Z]\d+)阶段([A-Z]+)清单「([^」]+)」正式登记，优先级(\d+)，每单元确定耗电(\d+)；完整部位ID为([A-Z0-9,]+)。',text):
            stage,code,title,priority,cost,units = match.groups()
            unit_ids = units.split(',')
            batches[code] = {'batch':code,'title':title,'stage':stage,'priority':int(priority),
                'unit_energy':int(cost),'unit_ids':unit_ids,'units':dict.fromkeys(unit_ids,'pending')}
        elif match := re.fullmatch(r'([A-Z]\d+)单元([A-Z]+\d+)已实际检查完成，独立回执([A-Z0-9-]+)，扣(\d+)，余额从(\d+)变为(\d+)。',text):
            stage,unit,receipt,cost,before,after = match.groups()
            batch = next((b for b in batches.values() if unit in b['units']),None)
            if batch is None or batch['stage'] != stage:
                raise ValueError('Unit status must identify a registered inspection unit in this stage')
            if receipt in receipts:
                if receipts[receipt] != match.groups():
                    raise ValueError('A forwarded receipt must retain its original unit and debit')
                continue
            if int(before) != battery or int(cost) != batch['unit_energy']:
                raise ValueError('Each new actual unit completion must debit its own registered unit quote')
            battery -= batch['unit_energy']
            if int(after) != battery:
                raise ValueError('Actual unit completion receipts must preserve the energy ledger')
            receipts[receipt] = match.groups()
            batch['units'][unit] = 'completed'
        elif match := re.fullmatch(r'正式取消([A-Z]\d+)单元([A-Z]+\d+)复检；该单元此前未执行，不扣款，不再要求检查。',text):
            stage,unit = match.groups()
            batch = next((b for b in batches.values() if unit in b['units']),None)
            if batch is None or batch['stage'] != stage:
                raise ValueError('Unit status must identify a registered inspection unit in this stage')
            batch['units'][unit] = 'cancelled'
        elif match := re.fullmatch(r'转发原执行回执([A-Z0-9-]+)，保留原执行时刻和原扣款记录；仅转发，不是新检查、没有新增扣电。',text):
            if match[1] not in receipts:
                raise ValueError('A forwarded receipt needs its original actual inspection in the prose')
    if battery != current['state']['battery']:
        raise ValueError('Forwarded receipts and drafts must not debit current energy again')
    reserve = reserved_energy(batches,current['stage'],current['priority'])
    safe = [r['details']['operation'] for r in current['actions'] if r['details']['operation']['energy'] <= battery-reserve]
    return {'batches':batches,'battery':battery,'reserve':reserve,'available':battery-reserve,
        'safe_operations':safe,'maximum_yield':max(op['yield'] for op in safe)}


def next_action(facts,current):
    return decision_command(current,max(facts['safe_operations'],key=lambda op:op['yield']))


def check_world(task,facts):
    if facts['batches'] != task.world['batches'] or facts['battery'] != task.initial['battery']:
        raise ValueError('Mandatory inspection reserves must follow distinct unit completion and cancellation records')


def audit_cases(task,facts,solution):
    return decision_cases(task,solution,lambda op:100*op['yield']/facts['maximum_yield'] if op in facts['safe_operations'] else 0)
