"""FM-S2-P2: whole-batch measurement with independent functional and numeric evidence."""
from copy import deepcopy
from itertools import combinations
import re

from ...action_contract import ActionContract
from ...environment import TaskRuntime
from ..common import History, clock, fixed_options, task_shell
from ..prose import paragraphs

FUNCTIONS = {'grain':'粒度测量','volatile':'挥发组分测量','thermal':'温度测量','magnetic':'磁性测量'}
SHORT = dict(zip('GVTM',FUNCTIONS,strict=True))
BASE_MENU = tuple(device+function for device in 'XYZ' for function in 'GVTM')+('H',)
CONDITIONS = (
    ('G',6,2,'XY'),('G',6,2,'YZ'),('V',5,2,'XZ'),('G',5,2,'XY'),('G',7,2,'XY'),('V',5,1,'XZ'),
    ('G',6,2,'XY'),('V',7,3,'XZ'),('T',6,2,'XZ'),('V',7,2,'XY'),('G',6,1,'YZ'),('G',8,2,'XY'),
    ('G',6,2,'XY'),('T',6,2,'YZ'),('T',4,2,'YZ'),('T',6,2,'XY'),
)
RETAINED_MENUS = {
    0:'XG ZT XM XV XT YV H YT ZG ZV YM YG ZM',
    1:'XM YV ZV ZM YG YM YT XG XT H ZG ZT XV',
    2:'H YG YM XT YT XM ZV XV ZT ZM ZG YV XG',
    6:'ZT ZV ZM YG ZG YV XM H YT XV YM XG XT',
    7:'ZT XM YM H XG YV XV ZG YT XT ZM YG ZV',
    8:'YV YM YG ZM XG H ZV ZT ZG YT XT XM XV',
    12:'YG YT ZM H XT ZG XV YM XG ZT XM YV ZV',
    13:'XM YV ZV YT XV YG YM H ZM XG ZT XT ZG',
}
# Each tuple is (chain, function or None, capacity or None, error or None).
EXTENDED = {
    3:((('F','G',None,None),('C',None,5,None),('E',None,None,2)),4,(9,4,12,1,7,14,5,11,2,8,13,6,10,3)),
    4:((('C',None,7,None),('C',None,5,None),('E',None,None,2)),11,(7,13,4,10,1,6,12,3,9,14,5,2,11,8)),
    5:((('E',None,None,2),('U','V',None,1),('U','V',None,2)),2,(6,14,10,3,8,12,5,1,7,13,9,11,2,4)),
    9:((('R','V',8,2),('U','V',None,2),('C',None,8,None)),13,(8,1,11,4,13,5,10,2,12,7,3,9,14,6)),
    10:((('E',None,None,1),('E',None,None,1),('E',None,None,1)),11,(3,7,12,1,9,14,5,10,6,11,2,8,4,13)),
    11:((('C',None,7,None),('C',None,8,None),('E',None,None,2)),9,(7,11,1,5,14,9,3,13,8,6,12,2,4,10)),
    14:((('F','T',None,None),('R','T',4,2),('E',None,None,2)),12,(5,1,14,9,6,12,8,3,11,4,10,13,7,2)),
    15:((('R','T',8,3),('S','T',6,2),('E',None,None,2)),3,(11,14,7,4,1,10,13,6,9,2,5,8,12,3)),
}


def initial_capabilities():
    return {device:{**{name:name in (('grain','volatile','thermal') if device == 'X' else ('grain','thermal')) for name in FUNCTIONS},
                    'capacity':8 if device == 'X' else 6,'error':4 if device == 'Z' else 2} for device in 'XYZ'}


def source_records(index):
    """Manually authored native round facts from the current FM, not an old builder."""
    if index == 0:
        return (
            (3,3,'Z完成上批温度测量记录，未验证粒度功能。','Z',{}, {'thermal':True}),
            (6,4,'X粒度功能实际故障失效，其余功能、容量和误差不变。','X',{'grain':False},{'grain':False}),
            (9,5,'X电源复位完毕，粒度故障尚未通过验证解除，限制仍在。','X',{}, {'grain':False}),
            (12,6,'X温度功能正常，维修单仍只限制粒度功能。','X',{}, {'thermal':True,'grain':False}),
            (16,7,'Y清空样槽，不改容量与误差。','Y',{},{}),
            (21,8,'Z粒度附件重装建议登记，尚无复标。','Z',{},{}),
            (24,9,'X粒度模块更换申请受理，尚未维修或验证。','X',{},{}),
            (28,10,'三载荷通信自检完成，不代表测量恢复。',None,{},{}),
        )
    if index == 1:
        return (
            (3,3,'X在其他工位完成挥发组分测量，覆盖未变。','X',{}, {'volatile':True}),
            (6,4,'Y粒度功能实际故障失效，其他能力不变。','Y',{'grain':False},{'grain':False}),
            (9,5,'Y控制器复位完毕，粒度故障限制仍在。','Y',{}, {'grain':False}),
            (13,6,'Y温度功能正常，不能据此证明粒度恢复。','Y',{}, {'thermal':True}),
            (17,7,'Z精度提升预算获准，标定未执行。','Z',{},{}),
            (21,8,'X交回邻位样盒，未移入Y/Z工位。','X',{},{}),
            (24,9,'Y维修仅排程，粒度功能尚未恢复，限制仍在。','Y',{}, {'grain':False}),
            (28,10,'Z缓存清理，无新的粒度误差验证。','Z',{},{}),
        )
    if index == 2:
        return (
            (3,3,'Y归档粒度测量，仍无挥发组分功能。','Y',{}, {'grain':True,'volatile':False}),
            (5,4,'X挥发组分功能实际故障失效。','X',{'volatile':False},{'volatile':False}),
            (8,5,'X挥发组分模块复位指令已执行，尚未完成功能验证。','X',{},{}),
            (12,6,'X温度测量记录不能解除挥发组分故障限制。','X',{}, {'thermal':True,'volatile':False}),
            (16,7,'Z挥发组分附件已安装，仍等验收。','Z',{},{}),
            (19,8,'Z扩展挥发组分功能实际验收可用，当前误差2；容量不变。','Z',{'volatile':True,'error':2},{'volatile':True,'error':2}),
            (22,9,'Y挥发组分附件采购受理，未到货。','Y',{},{}),
            (26,10,'Z原温度功能仍可用，新功能未移除旧功能。','Z',{}, {'thermal':True}),
            (28,11,'X挥发组分恢复验证只排程，无实际通过。','X',{},{}),
        )
    if index == 6:
        return (
            (3,3,'Z曾服务另一架样盒，覆盖未变。','Z',{},{}),
            (4,4,'X粒度功能失效，其他能力正常。','X',{'grain':False},{'grain':False}),
            (8,5,'X复位已执行，粒度通道仍未验证恢复，本次故障限制尚未解除。','X',{}, {'grain':False}),
            (12,6,'Y实际隔离样槽，容量现为3组，精度不变。','Y',{'capacity':3},{'capacity':3}),
            (15,7,'Y三可用槽已清空，未开放隔离槽，当前可用容量仍为3组。','Y',{}, {'capacity':3}),
            (18,8,'Y六槽恢复仅审批，未硬件复检。','Y',{},{}),
            (22,9,'Z粒度实际复标，误差由4降为2、容量仍6组。','Z',{'error':2},{'grain':True,'error':2,'capacity':6}),
            (24,10,'Z在另一工位完成粒度复测，未换到X/Y工位。','Z',{}, {'grain':True}),
            (28,11,'Y恢复六槽方案未执行。','Y',{},{}),
            (29,12,'X温度功能正常，本次热测没有新的合格粒度验证；本条未对grain当前许可作状态确认。','X',{}, {'thermal':True}),
        )
    if index == 7:
        return (
            (3,3,'Y完成温度测量，未装挥发组分功能。','Y',{}, {'thermal':True,'volatile':False}),
            (4,4,'Z新增挥发组分功能并实际验收，误差3。','Z',{'volatile':True,'error':3},{'volatile':True,'error':3}),
            (7,5,'Z挥发组分附件交接，样槽数未变。','Z',{},{}),
            (13,6,'X挥发组分功能实际故障失效。','X',{'volatile':False},{'volatile':False}),
            (16,7,'X换模块请求受理，等验证。','X',{},{}),
            (19,8,'X挥发组分模块替换完成，只确认安装、尚未批准测量。','X',{}, {'volatile':False}),
            (23,9,'X挥发组分功能实际修复并验证恢复，容量8组、误差2。','X',{'volatile':True},{'volatile':True,'capacity':8,'error':2}),
            (25,10,'Z样槽清空，处理数量仍按原能力。','Z',{},{}),
            (28,11,'Y不具挥发组分功能，升级仍计划。','Y',{}, {'volatile':False}),
            (29,12,'Y升级说明编制，无新增验收功能。','Y',{},{}),
        )
    if index == 8:
        return (
            (3,3,'X温度功能实际故障不可用。','X',{'thermal':False},{'thermal':False}),
            (6,4,'X粒度功能正常，温度故障限制未解除。','X',{}, {'grain':True,'thermal':False}),
            (9,5,'Y在另一工位归档温度测量，未迁移。','Y',{}, {'thermal':True}),
            (12,6,'Z温度功能仍有，实测误差升至5。','Z',{'error':5},{'thermal':True,'error':5}),
            (15,7,'Z温控复位，不是误差复标。','Z',{},{}),
            (18,8,'X温度恢复申请已受理，未验证；本条不确认当前温度许可状态。','X',{},{}),
            (20,9,'Z复标申请受理，无实际通过。','Z',{},{}),
            (23,10,'Z标定排程未执行。','Z',{},{}),
            (27,11,'Y温度功能复检，误差仍2。','Y',{}, {'thermal':True,'error':2}),
            (29,12,'三载荷链路自检，无新增温度合格凭据。',None,{},{}),
        )
    if index == 12:
        return (
            (3,3,'X粒度功能实际失效，已申请维修。','X',{'grain':False},{'grain':False}),
            (5,4,'X维修申请受理，粒度功能仍限制。','X',{}, {'grain':False}),
            (8,5,'Z整理粒度标定资料，尚待复标。','Z',{},{}),
            (10,6,'Y容量实际降为4组。','Y',{'capacity':4},{'capacity':4}),
            (13,7,'Y四槽清空，其余两槽未启用，当前容量仍4组。','Y',{}, {'capacity':4}),
            (17,8,'Z粒度功能实际复标，误差2。','Z',{'error':2},{'grain':True,'error':2}),
            (20,9,'X模块替换结束，粒度待验证尚未获准，温度记录正常。','X',{}, {'grain':False,'thermal':True}),
            (23,10,'X粒度模块更换并实际验证恢复，容量8组、误差2。','X',{'grain':True},{'grain':True,'capacity':8,'error':2}),
            (25,11,'Y满量方案获批，无六槽复验。','Y',{},{}),
            (27,12,'Z精密部件再次漂移，实测误差4。','Z',{'error':4},{'error':4}),
            (28,13,'Z已重启，不撤销新漂移；本条未复标误差数值。','Z',{},{}),
            (29,14,'Z第二次复标仅入队，尚未执行。','Z',{},{}),
        )
    if index == 13:
        return (
            (3,3,'Z温度功能实际失效禁用。','Z',{'thermal':False},{'thermal':False}),
            (5,4,'Z修复申请受理，温度限制仍在。','Z',{}, {'thermal':False}),
            (8,5,'X粒度测量记录不能代替温度精度。','X',{}, {'grain':True}),
            (10,6,'X温度测量实测误差升为4。','X',{'error':4},{'thermal':True,'error':4}),
            (13,7,'Z替换件到货，未安装。','Z',{},{}),
            (17,8,'Y容量实际降为3组。','Y',{'capacity':3},{'capacity':3}),
            (19,9,'Y三槽清空，降额未解除，当前容量仍3组。','Y',{}, {'capacity':3}),
            (22,10,'Z修复获批，此时温度功能未恢复。','Z',{}, {'thermal':False}),
            (24,11,'Z安装完毕，仍等温度功能验证。','Z',{},{}),
            (27,12,'Z温度功能实际修复并验证，误差2、容量6组。','Z',{'thermal':True,'error':2},{'thermal':True,'error':2,'capacity':6}),
            (28,13,'X申请温度复标，无新误差测定值。','X',{},{}),
            (29,14,'Y六槽恢复仍为计划。','Y',{},{}),
        )
    raise ValueError('Only the eight explicitly retained cases have source records')


def build(index):
    function,quantity,limit,eligible = CONDITIONS[index]
    retained = index in RETAINED_MENUS
    identifiers = [f'H{i:02d}' for i in range(1,15)] if retained else [f'H{i:02d}' for i in EXTENDED[index][2]]
    history = History(times=[clock('09:00')+120*r for r in range(30)]) if retained else History()

    def emit(at,number,text,*,device=None,changes=None,claims=None,job_id=None,bind=False,only_job=False,event='measurement_record'):
        facts = {'event':event}
        if job_id:
            facts['job_id'] = job_id
            if bind:
                facts['job_device'] = device
        if device and not only_job:
            facts['device'] = device
        if changes:
            facts['changes'] = deepcopy(changes)
        if claims:
            facts['claims'] = deepcopy(claims)
        time = clock('09:00')+120*(at-1) if retained else None
        history.add(at,identifiers[number-1]+'：'+text,record_id=identifiers[number-1],occurred=time,received=time,**facts)

    emit(1,1,'三载荷X/Y/Z的一次作业只能调用一台的一种功能，整批样品必须一次覆盖，不能拆批、拼批或试测后换台。'
        '必须在当前覆盖名单内、所需功能实际获准、容量≥整批量且误差≤上限，等号可用；覆盖外载荷服务别的固定工位，不能搬入。'
        '无主备偏好，任一满足者都可；两台均不满足才保持。功能、容量和统一标定误差分别维护，误差越小越精确，数值界限适用于当前已列测量功能。'
        '故障只移除明示功能，未变化功能与参数保持；安装、申请、复位和恢复操作完成不等于实际验收通过。'
        '同载荷同功能实际验收才恢复；明确当前限制未解除的回执可证明不能用。纯计划和无新验证不提供未写出的数值或状态。'
        '未改变字段的初始依据仍有效；实际改变使旧值证据失效，即使后来变回也不复活。同值复验或明确确认可并列作证。'
        '菜单13操作全部可提交，首次合法选择立即执行并结束，不能补交依据或重答；反馈固定“作业与依据已存档。”，不说明正误。'
        'select只含action/option及可选evidence；option为菜单数字字符串；evidence是当前目录内编号字符串数组，可省略或空，先去重再检查最多两个不同ID。'
        '仅action=end可提前结束。3次总调用，格式错误仅字段提示并耗次，不执行作业；无免费读能力/重发历史操作，原生记忆检索不计动作。'
        '执行须提供所需功能、容量、误差三项当前依据；保持须为两覆盖台各提供至少一项失败的当前依据，其他题内事实不能替代未写字段。',event='measurement_protocol')
    initial = initial_capabilities()
    emit(2,2,'初始完整能力表：X获准粒度/挥发组分/温度测量、容量8组、误差2；Y获准粒度/温度测量、容量6组、误差2；'
        'Z获准粒度/温度测量、容量6组、误差4。三台均不支持磁性测量，Y/Z初始不支持挥发组分测量。',claims=initial,event='measurement_initial')
    if retained:
        for at,identifier,text,device,changes,claims in source_records(index):
            emit(at,identifier,text,device=device,changes=changes,claims=claims)
        menu = RETAINED_MENUS[index].split()
        catalog_size = max(record[1] for record in source_records(index))
    else:
        chains,shift,_ = EXTENDED[index]
        for phase,times in enumerate(((4,5,6),(12,16,20),(22,24,26))):
            for position,(device,chain,at) in enumerate(zip('XYZ',chains,times,strict=True)):
                kind,short,capacity,error = chain
                f = SHORT[short] if short else None
                label = FUNCTIONS[f] if f else ''
                changes,claims = {},{}
                if phase == 0:
                    if kind in ('F','R','S'):
                        changes = claims = {f:False}
                        text = label+'功能实际故障，使用限制生效，其他功能不变。'
                    else:
                        text = {'C':'容量调整提出申请，尚未执行。','E':'误差复标申请受理，尚未执行。','U':label+'附件安装申请受理，尚未装配。'}[kind]
                elif phase == 1:
                    if kind == 'F':
                        claims = {f:False}
                        text = '复位已完成，'+label+'尚未通过恢复验证，限制仍在。'
                    elif kind == 'C':
                        changes = claims = {'capacity':capacity}
                        text = f'样槽实际调整并验收，容量{capacity}组，功能与误差不变。'
                    elif kind == 'E':
                        changes = claims = {'error':error}
                        text = f'实际复标，误差界限{error}，功能与容量不变。'
                    elif kind == 'U':
                        changes = claims = {f:True,'error':error}
                        text = f'附件实际装好并验证，新增{label}功能，误差{error}，容量不变。'
                    else:
                        changes = claims = {f:True,'capacity':capacity,'error':error}
                        text = f'{label}实际修复并验证恢复，容量{capacity}组、误差{error}。'
                else:
                    if kind in ('F','S'):
                        claims = {f:False}
                        changes = claims if kind == 'S' else {}
                        text = label+('随后再次实际故障，限制重新生效；容量与误差数值不变。' if kind == 'S' else '当前限制明确未解除，其他功能不变。')
                    elif kind == 'C':
                        claims = {'capacity':capacity}
                        text = f'独立确认当前可用容量仍{capacity}组。'
                    elif kind == 'E':
                        claims = {'error':error}
                        text = f'独立确认同一当前误差界限仍{error}。'
                    elif kind == 'U':
                        claims = {f:True,'error':error}
                        text = f'独立确认{label}功能仍获准且当前误差{error}。'
                    else:
                        claims = {f:True,'capacity':capacity,'error':error}
                        text = f'再次完整确认{label}功能可用、容量{capacity}组、误差{error}。'
                job_id = 'J'+device if index >= 6 else None
                only_job = index >= 12 and phase == 2
                prefix = f'作业{job_id}：' if only_job else device+(f'（作业{job_id}）' if job_id else '')+'：'
                emit(at,3+3*phase+position,prefix+text,device=device,changes=changes,claims=claims,
                    job_id=job_id,bind=phase == 0,only_job=only_job)
        emit(27,12,'另批工位记录归档，不改本批能力。')
        emit(28,13,'下一班更换全部测量模块的方案尚未执行。')
        emit(29,14,'通信自检正常，未产生功能、容量或精度的新验证。')
        history.add(30,'普通准备完成。',event='measurement_prepared')
        shift %= 13
        menu = BASE_MENU[shift:]+BASE_MENU[:shift]
        catalog_size = 14
    entries = []
    for name in menu:
        operation = {'device':None,'function':'hold'} if name == 'H' else {'device':name[0],'function':SHORT[name[1]]}
        description = '保持待机，本批暂不执行测量' if name == 'H' else f'使用{name[0]}执行{FUNCTIONS[operation["function"]]}'
        entries.append({'description':description,'operation':operation})
    function = SHORT[function]
    task = task_shell('FM-S2-P2',index)
    task.public = {'instruction':f'本次需完成{quantity}组样品的{FUNCTIONS[function]}，误差界限不得超过{limit}。选择下一测量操作。',
        'required_function':function,'quantity':quantity,'error_limit':limit,'eligible_devices':list(eligible),
        'coverage_instruction':f'本次工位只由{eligible[0]}与{eligible[1]}覆盖；其余设备不能改换工位。',
        'time_s':clock('10:00' if retained else '09:00'),'max_steps':3,'state_fields':[],
        'record_catalog':[f'H{n:02d}' for n in range(1,catalog_size+1)],'actions':fixed_options(entries)}
    task.initial = {'measurement_attempts':[],'qualified_batch':False}
    task.world = reconstruct([event.public_input() for event in history.events],task.public)
    task.rubric = {'score':'correct measurement: 100*covered current function/capacity/error fields/3; correct hold: 50 per covered device proved unable; wrong 0'}
    return history.finish(task)


FUNCTION_NAME = r'(粒度|挥发组分|温度|磁性)(?:测量)?'
FUNCTION_KEYS = {label.removesuffix('测量'):key for key,label in FUNCTIONS.items()}


def _numbers(text):
    fields = {}
    if match := re.search(r'容量(?:现为|仍为|仍|实际降为)?(\d+)组',text):
        fields['capacity'] = int(match[1])
    if match := re.search(r'误差(?:界限仍|界限|由\d+降为|升至|升为|仍)?(\d+)',text):
        fields['error'] = int(match[1])
    return fields


def _measurement_facts(text):
    """Read actual changes separately from explicit confirmations and plans."""
    if match := re.match(rf'^{FUNCTION_NAME}(?:功能)?(?:实际故障(?:失效|不可用)?|失效|实际失效(?:禁用)?|随后再次实际故障)',text):
        fields = {FUNCTION_KEYS[match[1]]:False}
        return fields,fields
    if match := re.fullmatch(rf'{FUNCTION_NAME}实际修复并验证恢复，容量\d+组、误差\d+。',text):
        fields = {FUNCTION_KEYS[match[1]]:True,**_numbers(text)}
        return fields,fields
    if match := re.fullmatch(rf'附件实际装好并验证，新增{FUNCTION_NAME}功能，误差\d+，容量不变。',text):
        fields = {FUNCTION_KEYS[match[1]]:True,**_numbers(text)}
        return fields,fields
    if re.fullmatch(r'样槽实际调整并验收，容量\d+组，功能与误差不变。|实际隔离样槽，容量现为\d+组，精度不变。|容量实际降为\d+组。',text):
        fields = _numbers(text)
        return fields,fields
    if re.fullmatch(r'实际复标，误差界限\d+，功能与容量不变。|精密部件再次漂移，实测误差\d+。',text):
        fields = _numbers(text)
        return fields,fields
    if match := re.fullmatch(rf'{FUNCTION_NAME}(?:功能)?实际复标，误差(?:由\d+降为)?\d+(?:、容量仍\d+组)?。',text):
        function = match[1]
        numbers = _numbers(text)
        return {'error':numbers['error']},{FUNCTION_KEYS[function]:True,**numbers}
    # The measured error may drift while the named measurement function remains available.
    if match := re.fullmatch(rf'{FUNCTION_NAME}(?:功能仍有，实测|实测)误差升(?:至|为)\d+。',text):
        numbers = _numbers(text)
        return {'error':numbers['error']},{FUNCTION_KEYS[match[1]]:True,**numbers}
    if match := re.fullmatch(rf'扩展{FUNCTION_NAME}功能实际验收可用，当前误差\d+；容量不变。|新增{FUNCTION_NAME}功能并实际验收，误差\d+。',text):
        function = next(group for group in match.groups() if group is not None)
        fields = {FUNCTION_KEYS[function]:True,**_numbers(text)}
        return fields,fields
    if match := re.fullmatch(rf'{FUNCTION_NAME}(?:功能实际修复并验证恢复|模块更换并实际验证恢复)，容量\d+组、误差\d+。',text):
        changed = {FUNCTION_KEYS[match[1]]:True}
        return changed,{**changed,**_numbers(text)}
    if match := re.fullmatch(rf'{FUNCTION_NAME}功能实际修复并验证，误差\d+、容量\d+组。',text):
        fields = {FUNCTION_KEYS[match[1]]:True,**_numbers(text)}
        return {key:value for key,value in fields.items() if key != 'capacity'},fields
    if re.fullmatch(r'独立确认当前可用容量仍\d+组。|独立确认同一当前误差界限仍\d+。|[一二三四五六七八九]可用槽已清空，未开放隔离槽，当前可用容量仍为\d+组。|[一二三四五六七八九]槽清空，其余两槽未启用，当前容量仍\d+组。|[一二三四五六七八九]槽清空，降额未解除，当前容量仍\d+组。',text):
        return {},_numbers(text)
    if match := re.fullmatch(rf'独立确认{FUNCTION_NAME}功能仍获准且当前误差\d+。|再次完整确认{FUNCTION_NAME}功能可用、容量\d+组、误差\d+。|{FUNCTION_NAME}功能复检，误差仍\d+。',text):
        function = next(group for group in match.groups() if group is not None)
        return {},{FUNCTION_KEYS[function]:True,**_numbers(text)}
    negative_patterns = (
        rf'复位已完成，{FUNCTION_NAME}尚未通过恢复验证，限制仍在。',
        rf'{FUNCTION_NAME}当前限制明确未解除，其他功能不变。',
        rf'(?:电源|控制器)复位完毕，{FUNCTION_NAME}故障(?:尚未通过验证解除，限制仍在|限制仍在)。',
        rf'维修仅排程，{FUNCTION_NAME}功能尚未恢复，限制仍在。',
        rf'复位已执行，{FUNCTION_NAME}通道仍未验证恢复，本次故障限制尚未解除。',
        rf'{FUNCTION_NAME}模块替换完成，只确认安装、尚未批准测量。',
        rf'不具{FUNCTION_NAME}功能，升级仍计划。',
        rf'(?:维修申请受理|修复申请受理)，{FUNCTION_NAME}(?:功能仍限制|限制仍在)。',
        rf'修复获批，此时{FUNCTION_NAME}功能未恢复。',
    )
    for pattern in negative_patterns:
        if match := re.fullmatch(pattern,text):
            return {},{FUNCTION_KEYS[match[1]]:False}
    if match := re.fullmatch(rf'{FUNCTION_NAME}功能正常，维修单仍只限制{FUNCTION_NAME}功能。|{FUNCTION_NAME}功能正常，{FUNCTION_NAME}故障限制未解除。|{FUNCTION_NAME}测量记录不能解除{FUNCTION_NAME}故障限制。',text):
        positive,negative = (group for group in match.groups() if group is not None)
        return {},{FUNCTION_KEYS[positive]:True,FUNCTION_KEYS[negative]:False}
    if match := re.fullmatch(rf'(?:归档|完成){FUNCTION_NAME}(?:测量)?，(?:仍无|未装){FUNCTION_NAME}功能。',text):
        return {},{FUNCTION_KEYS[match[1]]:True,FUNCTION_KEYS[match[2]]:False}
    if match := re.fullmatch(rf'模块替换结束，{FUNCTION_NAME}待验证尚未获准，{FUNCTION_NAME}记录正常。',text):
        return {},{FUNCTION_KEYS[match[1]]:False,FUNCTION_KEYS[match[2]]:True}
    positive_patterns = (
        rf'完成上批{FUNCTION_NAME}记录，未验证粒度功能。',
        rf'在其他工位完成{FUNCTION_NAME}，覆盖未变。',
        rf'{FUNCTION_NAME}功能正常，不能据此证明粒度恢复。',
        rf'原{FUNCTION_NAME}功能仍可用，新功能未移除旧功能。',
        rf'在另一工位完成{FUNCTION_NAME}复测，未换到X/Y工位。',
        rf'{FUNCTION_NAME}功能正常，本次热测没有新的合格粒度验证；本条未对grain当前许可作状态确认。',
        rf'在另一工位归档{FUNCTION_NAME}，未迁移。',
        rf'{FUNCTION_NAME}记录不能代替温度精度。',
    )
    for pattern in positive_patterns:
        if match := re.fullmatch(pattern,text):
            return {},{FUNCTION_KEYS[match[1]]:True}
    return {},{}


def _initial_measurement(text):
    match = re.fullmatch(r'初始完整能力表：(.+)。三台均不支持磁性测量，Y/Z初始不支持挥发组分测量。',text)
    if match is None:
        return None
    capabilities = {}
    for part in match[1].split('；'):
        row = re.fullmatch(r'([XYZ])获准(.+)测量、容量(\d+)组、误差(\d+)',part)
        if row is None or row[1] in capabilities:
            raise ValueError('The initial table must print each device and its complete capabilities')
        names = row[2].split('/')
        if any(name not in FUNCTION_KEYS for name in names):
            raise ValueError('The initial table must use registered measurement functions')
        capabilities[row[1]] = {**{key:key in {FUNCTION_KEYS[name] for name in names} for key in FUNCTIONS},
            'capacity':int(row[3]),'error':int(row[4])}
    if set(capabilities) != set('XYZ') or any(capabilities[d]['magnetic'] for d in 'XYZ') or any(capabilities[d]['volatile'] for d in 'YZ'):
        raise ValueError('The initial table must agree with its explicit unsupported functions')
    return capabilities


def reconstruct(history,current):
    states,evidence,jobs = {},{},{}
    for paragraph in paragraphs(history):
        numbered = re.fullmatch(r'(H\d{2})：(.+)',paragraph)
        if numbered is None:
            continue
        identifier,text = numbered.groups()
        initial = _initial_measurement(text)
        if initial is not None:
            states = {device:{field:{'value':value,'revision':1} for field,value in cap.items()} for device,cap in initial.items()}
            evidence[identifier] = deepcopy(states)
            continue
        device = None
        if match := re.fullmatch(r'([XYZ])（作业(J[XYZ])）：(.+)',text):
            device,job_id,text = match.groups()
            if job_id in jobs and jobs[job_id] != device:
                raise ValueError('Job identity must match its originally assigned device')
            jobs[job_id] = device
        elif match := re.fullmatch(r'作业(J[XYZ])：(.+)',text):
            job_id,text = match.groups()
            if job_id not in jobs:
                raise ValueError('A job-only receipt requires its printed device assignment')
            device = jobs[job_id]
        elif match := re.fullmatch(r'([XYZ])：?(.+)',text):
            device,text = match.groups()
        if device:
            state = states[device]
            changes,claims = _measurement_facts(text)
            for field,value in changes.items():
                if state[field]['value'] != value:
                    state[field] = {'value':value,'revision':state[field]['revision']+1}
            proofs = {}
            for field,value in claims.items():
                if state[field]['value'] != value:
                    raise ValueError('An explicit capability confirmation must match the actual field')
                proofs[field] = deepcopy(state[field])
            evidence[identifier] = {device:proofs}
        else:
            evidence[identifier] = {}
    return {'states':states,'evidence':evidence,'function':current['required_function'],'quantity':current['quantity'],
            'error_limit':current['error_limit'],'eligible':current['eligible_devices']}


def failing_fields(facts,device):
    fields = facts['states'][device]
    return {field for field,failed in ((facts['function'],not fields[facts['function']]['value']),
        ('capacity',fields['capacity']['value'] < facts['quantity']),('error',fields['error']['value'] > facts['error_limit'])) if failed}


def supported_fields(facts,device,references):
    fields = (facts['function'],'capacity','error')
    return {field for identifier in references for field,proof in facts['evidence'].get(identifier,{}).get(device,{}).items()
            if field in fields and proof == facts['states'][device][field]}


def evaluate(facts,operation,references):
    valid = [device for device in facts['eligible'] if not failing_fields(facts,device)]
    if operation['function'] == 'hold':
        supported = [device for device in facts['eligible'] if failing_fields(facts,device) & supported_fields(facts,device,references)]
        return 50*len(supported) if not valid else 0,not valid,supported
    correct = operation['device'] in valid and operation['function'] == facts['function']
    supported = supported_fields(facts,operation['device'],references)
    return 100*len(supported)/3 if correct else 0,correct,sorted(supported)


class Runtime(TaskRuntime):
    # Retained ArrayEvidence contract keeps the menu after its single legal action.
    def __init__(self,task):
        super().__init__(task)
        self.action_contract = ActionContract(parameters={'select':{'evidence':{'type':'array','required':False,
            'items':{'type':'string','enum':task.public['record_catalog']},
            'description':'可省略或空数组；当前目录编号字符串，重复先去重，最多两个不同编号。'}}})

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or not {'action','option'} <= action.keys() or action.keys()-{'action','option','evidence'} or action['action'] != 'select':
            self.invalid()
            return
        option = next((row for row in self.actions() if isinstance(action['option'],str) and row['option'] == action['option']),None)
        references = action.get('evidence',[])
        if option is None or not isinstance(references,list) or not all(isinstance(n,str) and n in self.task.public['record_catalog'] for n in references) or len(set(references)) > 2:
            self.invalid()
            return
        references = list(dict.fromkeys(references))
        operation = deepcopy(option['operation'])
        score,correct,supported = evaluate(self.task.world,operation,references)
        if operation['function'] != 'hold':
            self.state['measurement_attempts'].append({**operation,'quantity':self.task.public['quantity'],'qualified':correct})
            self.state['qualified_batch'] = correct
        self.facts = {'executed_operation':operation,'operation_correct':correct,'supported':supported,'evidence':references}
        self.feedback = '作业与依据已存档。'
        self.end('completed',score=score,full_credit=score == 100)


def next_action(facts,current):
    for row in current['actions']:
        for count in (1,2):
            for references in combinations(current['record_catalog'],count):
                if evaluate(facts,row['details']['operation'],references)[0] == 100:
                    return {**row['arguments'],'evidence':list(references)}
    raise ValueError('A full-credit batch operation must have at most two sufficient records')


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Capabilities must follow actual changes, explicit confirmations and original job identities')


def audit_cases(task,facts,solution):
    cases = []
    for row in task.public['actions']:
        for count in range(3):
            for references in combinations(task.public['record_catalog'],count):
                command = {'action':'select','option':row['option'],'evidence':list(references)}
                cases.append(([command],evaluate(facts,row['operation'],references)[0]))
    command = solution[0]
    return cases+[([{**command,'evidence':command['evidence']*3}],100),
                  ([{'action':'select','option':command['option']}],0),([{}]*2+solution,100),([{}]*3,0)]
