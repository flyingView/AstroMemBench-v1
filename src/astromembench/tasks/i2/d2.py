"""FM-I2-D2: only physical drains clear analog charge before destructive readout."""
import re

from ..common import History, clock, fixed_options, task_shell
from ..decisions import DecisionRuntime, decision_cases, decision_command
from ..prose import paragraphs

# Target, pre-drain exposures, confirmed drain outcome, subsequent exposures.
CONFIGS = (
    ('A',(),None,(3,4,5)),('B',(),None,(10,12,8)),('C',(),None,(5,6,4)),
    ('C',(),None,(6,7,4)),('B',(),None,(40,30,50)),('C',(),None,(4,6,3)),
    ('C',(20,15),True,(7,9,8)),('B',(30,10),False,(3,5,4)),('B',(15,5),False,(7,6,7)),
    ('A',(10,15),True,(5,4,6)),('B',(18,6),False,(8,10,12)),('C',(40,10),False,(5,4,4)),
    ('C',(10,),True,(4,0,5,3,5)),('C',(50,),True,(30,0,25,35,30)),
    ('A',(12,),False,(5,0,6,4,5)),('A',(8,),False,(2,0,3,4,3)),
)
GAINS = (6,2,9,1,7,4,10,3,8,5)


def build(index):
    target,prefix,cleared,suffix = CONFIGS[index]
    u,v = ['ABC'[('ABC'.index(target)+n)%3] for n in (1,2)]
    charge = dict.fromkeys('ABC',0)
    history = History()
    history.add(1,'独立模拟积分井A/B/C初始均空，满井容量128q，1q=250个电子，井名整题固定。'
        '曝光回执+v仅指该次实际新增vq，不能把请求当已注入。真正打开排空栅且确认排空完成的CLEAR才清除旧电荷；'
        '旧观测已完整归档，本窗口只读新一轮积累。失败CLEAR、未执行清空计划、下游数字计数器重置、关闭快门、暂停或恢复电子学均不排空。'
        '此简化模型无暗电流、漏电、外来曝光或隐含衰减，不代表通用探测器规范。'
        'ADC原始输入满量程120q，固定十增益1至10；一次读出先转移全部井电荷Q，等效输入为gQ。'
        'gQ≤120含等号正常，超过120饱和，高端信息无法恢复。无论饱和与否，读出1秒后该井物理排空、其他井不变。'
        '档案保留增益、数值min(gQ,120)和饱和标志，已结束任务不再提供该档案查询或重读。'
        '目标是在这份积累上使用最大不饱和增益，充分利用量化级数；饱和时无法形成有效成果。'
        '所有增益的其他噪声和带宽相同，没有未知工程折衷，也无第二次曝光机会。'
        '当前只接受select和字符串option或end，最多3次总调用含格式错误与合法选择；额外字段、数值型或范围外编号无效。'
        '首次合法选择真实读出并结束；无电荷/电压查询、预览、试读恢复、清空补拍接口，不能饱和后重选。',
        event='charge_protocol',well_capacity_q=128,electrons_per_q=250,adc_full_scale_q=120,readout_seconds=1)
    history.add(2,'A/B/C三个井初始电荷均0q，固定可用读出增益为1、2、3、4、5、6、7、8、9、10。',
                event='charge_initial',charge_q=charge,gains=list(range(1,11)))
    exposures = [(8,u,10,10),(24,v,15,15)]
    prefix_rounds = (3,7) if index < 12 else (3,)
    for at,actual in zip(prefix_rounds,prefix):
        exposures.append((at,target,actual,actual))
    suffix_rounds = (4,13,23) if index < 6 else (16,22,27) if index < 12 else (9,12,18,25,28)
    for ordinal,(at,actual) in enumerate(zip(suffix_rounds,suffix,strict=True)):
        requested = actual+2 if index >= 6 and ordinal == 0 else 2 if index >= 12 and ordinal == 1 else actual
        exposures.append((at,target,requested,actual))
    clear_round = 11 if index < 12 else 6
    for at in range(1,31):
        if cleared is not None and at == clear_round:
            if cleared:
                charge[target] = 0
            history.add(at,f'对井{target}请求CLEAR。'+('排空栅打开，井内电荷实际全部移除，操作完成；此前观测归档完整。' if cleared else
                        '排空栅未打开，实际移除0q，井电荷保持；本次未排空不影响后续正常读出。'),
                        event='charge_clear_receipt',well=target,requested='CLEAR',actual_effect='emptied' if cleared else 'unchanged')
        for when,well,requested,actual in exposures:
            if when != at:
                continue
            charge[well] += actual
            note = '快门未开，实际新增0q。' if actual == 0 else '提前结束，只有实际量已注入。' if requested != actual else '实际注入完成。'
            history.add(at,f'积分井{well}曝光：请求新增{requested}q，实际新增{actual}q。{note}',
                        event='charge_exposure_receipt',well=well,requested_q=requested,actual_q=actual)
    if index >= 6:
        history.add(15,f'拟对积分井{target}执行CLEAR，仅候选计划，尚未执行，排空栅未动作。',
                    event='charge_clear_plan',well=target,executed=False)
        history.add(19 if index < 12 else 21,f'重置井{target}的下游ADC数字计数器，排空栅未动作，模拟井内电荷保留。',
                    event='adc_counter_reset',well=target,charge_changed=False)
    history.add(29,'关闭快门，无新增电荷；未打开排空栅，井内电荷保持。',event='shutter_closed',charge_changed=False)
    history.add(30,f'积分井{target}及读出电路接口正常。',event='charge_ready',well=target)
    task = task_shell('FM-I2-D2',index)
    task.public = {'instruction':f'科学观测积累已结束，积分井{target}与读出电路正常。请执行本次读出。',
                   'target':target,'time_s':clock('09:00'),'max_steps':3,'state_fields':[],
                   'actions':fixed_options([{'description':f'以增益{g}读出本次积累。','operation':{'action':'read','gain':g}} for g in GAINS])}
    task.initial = {'time_s':clock('09:00'),'charge_q':charge,'readout':None,'transferred_q':0}
    task.world = {'charge_q':charge,'maximum_gain':min(10,120//charge[target])}
    task.rubric = {'score':'0 if gain*charge>120, otherwise 100*gain/maximum_non_saturating_gain'}
    return history.finish(task)


class Runtime(DecisionRuntime):
    def invalid(self):
        self.feedback = '格式无效，请使用当前菜单编号。'

    def submit(self,action):
        super().submit(action)
        if action == {'action':'end'}:
            self.feedback = '本窗口已结束。'

    def execute(self,operation):
        target,gain = self.task.public['target'],operation['gain']
        charge = self.state['charge_q'][target]
        saturated = gain*charge > 120
        self.state['charge_q'][target] = 0
        self.state.update(time_s=self.state['time_s']+1,transferred_q=charge,
                          readout={'gain':gain,'adc_value':min(gain*charge,120),'saturated':saturated})
        self.feedback = '本次读出已结束，结果已归档。'
        return 0 if saturated else 100*gain/min(10,120//charge)


def reconstruct(history,current):
    charge = {}
    for text in paragraphs(history):
        initial = re.match(r'A/B/C三个井初始电荷均(\d+)q，',text)
        receipt = re.match(r'积分井([ABC])曝光：请求新增(\d+)q，实际新增(\d+)q。',text)
        cleared = re.match(r'对井([ABC])请求CLEAR。(.*)',text)
        if initial:
            charge = dict.fromkeys('ABC',int(initial[1]))
        elif receipt:
            well,requested,actual = receipt[1],int(receipt[2]),int(receipt[3])
            if not 0 <= actual <= requested or charge[well]+requested > 128:
                raise ValueError('Exposure request and execution must fit the physical well')
            charge[well] += actual
        elif cleared:
            if cleared[2].startswith('排空栅打开，井内电荷实际全部移除，操作完成；'):
                charge[cleared[1]] = 0
            elif not cleared[2].startswith('排空栅未打开，实际移除0q，井电荷保持；'):
                raise ValueError('CLEAR needs a confirmed physical outcome')
    if set(charge) != set('ABC') or not 0 < charge[current['target']] <= 120:
        raise ValueError('Each case requires all three wells and a nonempty readable target')
    return {'charge_q':charge,'maximum_gain':min(10,120//charge[current['target']])}


def next_action(facts,current):
    return decision_command(current,{'action':'read','gain':facts['maximum_gain']})


def check_world(task,facts):
    if facts != task.world or facts['charge_q'] != task.initial['charge_q']:
        raise ValueError('Analog charge must survive failed CLEAR and digital counter resets')


def audit_cases(task,facts,solution):
    charge = facts['charge_q'][task.public['target']]
    return decision_cases(task,solution,lambda op:0 if op['gain']*charge > 120 else 100*op['gain']/facts['maximum_gain'])
