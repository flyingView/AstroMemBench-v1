"""FM-R3-O1: reuse segmentation masks and count each physical defect cell once."""
import re

from ...action_contract import ActionContract
from ..common import History, clock, task_shell
from ..computation import ComputationRuntime
from ..prose import paragraphs

AREAS = dict(zip(('P1','P2','P3','P4','P5','P6'),(2,3,5,7,11,13),strict=True))
SLOTS = {'A':['P1','P2','P3','P4'],'B':['P3','P4','P5','P6']}
# Order permutation, complete four-bit A/B masks, and current report cells.
CONFIGS = (
    (1,'1010','1001','123456'),
    (1,'0011','1101','3456'),
    (3,'1000','0010','135'),
    (1,'0001','0111','246'),
    (3,'1011','1100','135'),
    (2,'0110','1001','246'),
    (2,'1111','1100','123456'),
    (3,'0000','0011','1234'),
    (2,'1010','1010','3456'),
    (1,'1001','0101','1256'),
    (2,'0011','1100','246'),
    (3,'1110','1001','2346'),
    (2,'1011','1111','123456'),
    (3,'0110','1000','1456'),
    (1,'1101','0111','2345'),
    (3,'1111','1110','1356'),
)


def panel_masks(jobs,current):
    return {tile:next(j['mask'] for j in jobs.values() if
        (j['panel'],j['tile'],j['image_package'],j['model']) ==
        (current['panel'],tile,current['image_package'],current['model'])) for tile in current['slots']}


def defect_area(masks,current):
    cells = {cell for tile,mask in masks.items() for cell,bit in zip(current['slots'][tile],mask,strict=True) if bit == '1'}
    return sum(current['cell_areas'][cell] for cell in cells.intersection(current['report_cells']))


def build(index):
    permutation,a,b,report = CONFIGS[index]
    definitions = (('K','A',a),('K','B',b),('L','A','1001'))
    jobs = {}
    for identifier,position in zip(('J12','J27','J04'),{1:(0,1,2),2:(1,2,0),3:(2,0,1)}[permutation],strict=True):
        panel,tile,mask = definitions[position]
        jobs[identifier] = {'id':identifier,'panel':panel,'tile':tile,'image_package':'S','model':'M','energy':18,'mask':mask}
    history = History()
    history.add(1,'准确报告当前指定区域的缺陷面积并节省计算能源；本题只报告面积，不执行巡检或改变面板。'
        '面板K分成六个互不相交的物理单元，面积P1=2、P2=3、P3=5、P4=7、P5=11、P6=13 cm²。'
        '图块A的槽1/2/3/4对应P1/P2/P3/P4，B的槽1/2/3/4对应P3/P4/P5/P6。四位掩码从左到右对应槽1至4；1表示整个单元有缺陷，0表示无缺陷。'
        '同一面板重叠P3/P4的两图结果必一致；映射到物理单元后取并集，再与报告集合W相交，每个物理单元只计一次，W外不计。'
        '相同面板、图块、图像包S及模型M且表面未变时，成功的分割结果可复用；改变报告集合W不使掩码失效。另面板L独立，不得混入K。'
        '当前仅给身份、W、面积和槽位表，没有原图、掩码或原始分割输入，不能凭几何免费恢复缺陷；可以从合法记忆复用充分的结果并做集合及加法。'
        '当前能源48，历史计算费用不扣当前能源。get_steps的scope=A/B各耗18，all耗36，省略scope按all，只返回请求的K图块。'
        '付费返回固定代理整数u=m XOR 7和步骤m=u XOR 7，把m写成四位二进制并保留前导0，最左为最高位，即所求掩码。'
        '代理代表当前无法免费访问的分割服务，费用是服务代价，不是真实XOR能耗；不改变图像或缺陷。成功调用重复照付，余额不足则不调用、不扣费、不返回输入但占额度。'
        '已记得结果无需重算；W只需一图时允许只补一图，不强制双图收费。原生记忆检索不计环境动作。'
        'submit顶层value为单个有限JSON数值cm²，等值十进制及科学计数可接受；布尔、非有限值、字符串、算式和多值为格式错。'
        '首次有效数值提交立即结束，正确错误均反馈巡检面积已接收，记录已存档，不允许重答。须正确报告面积并尽量减少当前实际计算耗能，无需解释或证据号。'
        '面积为0也须明确提交数值0；end或额度耗尽即结束，已付能源不退。最多4次总调用，含无效格式、余额不足、get_steps、submit及end。'
        'get_steps仅action及可选scope，submit仅action/value，end仅action；未知动作/scope、额外字段或结构错报请求格式无效，不扣能源但占额度。终止反馈不报正误。',
        event='segmentation_reuse_protocol',cell_areas=AREAS,slots=SLOTS,initial_energy=48,costs={'A':18,'B':18,'all':36},max_actions=4,unit='cm²')
    history.add(2,'当前K的A、B都使用同一图像包S及模型M，目标表面未变；L是另一个独立面板。',
        event='segmentation_input_identities',panel='K',tiles=['A','B'],image_package='S',model='M',surface_unchanged=True)
    starts = {'J12':6,'J27':17,'J04':24} if index < 6 else ({'J12':4,'J27':8,'J04':12} if index < 12 else {'J27':3,'J04':7,'J12':11})
    finishes = starts if index < 6 else ({'J04':19,'J12':23,'J27':27} if index < 12 else {'J12':20,'J27':24,'J04':28})
    for at in range(3,29):
        for identifier,job in jobs.items():
            if at == starts[identifier]:
                if index < 6:
                    history.add(at,f'{identifier}登记面板{job["panel"]}图块{job["tile"]}/S/M，实际已付18，分割成功，四位掩码{job["mask"]}。',
                        event='segmentation_succeeded',**job)
                elif index < 12:
                    history.add(at,f'{identifier}登记面板{job["panel"]}图块{job["tile"]}/S/M，实际已付18开始分割。',
                        event='segmentation_started',**{k:v for k,v in job.items() if k != 'mask'})
                else:
                    history.add(at,f'{identifier}登记面板{job["panel"]}、图块{job["tile"]}。',
                        event='segmentation_job',id=identifier,panel=job['panel'],tile=job['tile'])
            if index >= 12 and at == starts[identifier]+2:
                history.add(at,f'{identifier}补充图像包S及模型M，实际已付18开始分割。',
                    event='segmentation_started',id=identifier,image_package='S',model='M',energy=18)
            if index >= 6 and at == finishes[identifier]:
                history.add(at,f'{identifier}分割成功，四位掩码{job["mask"]}。',event='segmentation_result',id=identifier,mask=job['mask'])
        if at == 15:
            history.add(at,'拟对面板L追加拍照，尚未执行，不影响K。',event='segmentation_photo_plan',panel='L',executed=False)
    history.add(29,'K的A、B图像包S及模型M保持，目标表面没有物理变化。',
        event='segmentation_inputs_unchanged',panel='K',tiles=['A','B'],image_package='S',model='M',surface_unchanged=True)
    task = task_shell('FM-R3-O1',index,current_input_group=f'FM-R3-O1-W{report}')
    task.public = {'instruction':f'面板K的A、B图像包S及模型M与此前相同，面板没有物理变化。本次只报告物理单元{["P"+n for n in report]}的缺陷面积，请提交总cm²。',
        'time_s':clock('09:00'),'panel':'K','image_package':'S','model':'M','surface_unchanged':True,
        'report_cells':['P'+n for n in report],'cell_areas':AREAS,'slots':SLOTS,'unit':'cm²','max_steps':4,'state_fields':['energy'],
        'actions':[{'action':'get_steps','description':'重新分割所请求的K图块；A/B各耗18，all耗36，省略scope按all。'},
            {'action':'submit','description':'提交顶层value为单个有限数值的报告区域缺陷总面积。'},{'action':'end','description':'结束任务。'}]}
    task.initial = {'energy':48}
    task.world = {'jobs':jobs,'masks':panel_masks(jobs,task.public)}
    task.rubric = {'metric':'correct_unique_defect_area_times_remaining_energy_over_48','range':[0,100]}
    return history.finish(task)


class Runtime(ComputationRuntime):
    query_costs = {'A':18,'B':18,'all':36}
    default_scope = 'all'
    insufficient_feedback = '计算能源不足，未调用分割服务'
    submitted_feedback = '巡检面积已接收，记录已存档。'
    action_contract = ActionContract(('action',),parameters={
        'get_steps':{'scope':{'type':'string','enum':['A','B','all'],'required':False,'default':'all'}},
        'submit':{'value':{'type':'number','required':True,'description':'单个有限JSON数值cm²，不接受数组、字符串、布尔值或算式。'}}})

    def computation_inputs(self,scope):
        names = ('A','B') if scope == 'all' else (scope,)
        return {tile:{'u':int(self.task.world['masks'][tile],2)^7} for tile in names},'每个所给图块m=u XOR 7；将m写成四位二进制并保留前导0，最左为最高位，对应槽1至4；映射物理单元取并集，再与W相交求面积'

    def answer_credit(self,value):
        correct = value == defect_area(self.task.world['masks'],self.task.public)
        self.facts['value_correct'] = correct
        return 100 if correct else 0


def reconstruct(history,current):
    jobs = {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(J\d+)登记面板([A-Z])图块([A-Z])/([A-Z0-9]+)/([A-Z0-9]+)，实际已付(\d+)，分割成功，四位掩码([01]{4})。',text):
            identifier,panel,tile,package,model,cost,mask = match.groups()
            jobs[identifier] = {'id':identifier,'panel':panel,'tile':tile,'image_package':package,
                'model':model,'energy':int(cost),'mask':mask}
        elif match := re.fullmatch(r'(J\d+)登记面板([A-Z])图块([A-Z])/([A-Z0-9]+)/([A-Z0-9]+)，实际已付(\d+)开始分割。',text):
            identifier,panel,tile,package,model,cost = match.groups()
            jobs[identifier] = {'id':identifier,'panel':panel,'tile':tile,'image_package':package,
                'model':model,'energy':int(cost)}
        elif match := re.fullmatch(r'(J\d+)登记面板([A-Z])、图块([A-Z])。',text):
            identifier,panel,tile = match.groups()
            jobs[identifier] = {'id':identifier,'panel':panel,'tile':tile}
        elif match := re.fullmatch(r'(J\d+)补充图像包([A-Z0-9]+)及模型([A-Z0-9]+)，实际已付(\d+)开始分割。',text):
            identifier,package,model,cost = match.groups()
            jobs[identifier].update(image_package=package,model=model,energy=int(cost))
        elif match := re.fullmatch(r'(J\d+)分割成功，四位掩码([01]{4})。',text):
            jobs[match[1]]['mask'] = match[2]
    if any(j['energy'] != 18 or len(j['mask']) != 4 or set(j['mask'])-{'0','1'} for j in jobs.values()):
        raise ValueError('Reuse requires paid successful complete four-bit masks')
    masks = panel_masks(jobs,current)
    if masks['A'][2:] != masks['B'][:2]:
        raise ValueError('Overlapping physical cells must agree')
    return {'jobs':jobs,'masks':masks,'value':defect_area(masks,current)}


def next_action(facts,current):
    return {'action':'submit','value':facts['value']}


def check_world(task,facts):
    if any(facts[k] != task.world[k] for k in ('jobs','masks')):
        raise ValueError('Segmentation reuse must retain panel, tile, package, model and order bindings')


def audit_cases(task,facts,solution):
    cases = []
    for prefix,energy in (([],48),([{'action':'get_steps','scope':'A'}],30),([{'action':'get_steps','scope':'B'}],30),
        ([{'action':'get_steps'}],12),([{'action':'get_steps','scope':'all'}],12),
        ([{'action':'get_steps','scope':'A'},{'action':'get_steps','scope':'B'}],12),
        ([{'action':'get_steps','scope':'A'}]*3,12),([{'action':'get_steps'}]*3,12)):
        for value in (facts['value'],facts['value']+1):
            cases.append((prefix+[{'action':'submit','value':value}],100*energy/48 if value == facts['value'] else 0))
    duplicated = sum(task.public['cell_areas'][cell] for tile,mask in facts['masks'].items()
        for cell,bit in zip(task.public['slots'][tile],mask,strict=True) if bit == '1' and cell in task.public['report_cells'])
    return cases+[([{'action':'submit','value':duplicated}],100 if duplicated == facts['value'] else 0),
        ([{'action':'submit','value':0}],100 if facts['value'] == 0 else 0),([{}]*3+solution,100),([{}]*4,0)]
