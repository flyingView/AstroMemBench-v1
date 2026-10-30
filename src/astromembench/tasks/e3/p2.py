"""FM-E3-P2: join visual worksite identity to surveyed rail positions and endpoints."""
import re

from ..common import History, clock, task_shell
from ..prose import paragraphs
from .locations import location, report_options
from .landmarks import (HISTORY_FILES, QUERY_FILES, VISUAL_REVISION, VISUAL_INPUT_NOTE, LandmarkRuntime, attachment,
                        check_world, image_identity, next_action, report_cases as audit_cases)

VISUAL_AUDIT = True
# Per worksite: left-distance 6/15/24 names, u endpoint, installed range assembly.
SURVEYS = {
    'A': (((4,7,1),'L','T28'), ((8,2,6),'R','T61'), ((3,9,5),'L','T43')),
    'B': (((9,3,6),'R','T43'), ((1,5,7),'L','T28'), ((8,4,2),'R','T61')),
    'C': (((2,8,5),'L','T61'), ((6,9,3),'L','T43'), ((7,1,4),'R','T28')),
    'D': (((5,1,9),'R','T28'), ((3,7,4),'R','T43'), ((2,6,8),'L','T61')),
}
IMAGES = {'A': ('I64','I27','I85'), 'B': ('I27','I85','I64'),
          'C': ('I85','I64','I27'), 'D': ('I64','I85','I27')}
VISITS = ('V52','V18','V73')
ARRIVALS = {'A': (2,1,3), 'B': (3,2,1), 'C': (1,3,2), 'D': (3,1,2)}
IMAGE_ORDER = {'A': (1,3,2), 'B': (2,1,3), 'C': (3,2,1), 'D': (2,3,1)}
GEOMETRY_ORDER = {'A': (3,2,1), 'B': (1,3,2), 'C': (2,1,3), 'D': (1,2,3)}
# Individually reviewed FM rows: book, current worksite, actual u/v measurements.
CONFIGS = (('A',1,6,24), ('B',2,24,6), ('C',3,6,24), ('D',1,15,15),
           ('A',2,6,24), ('B',3,24,6), ('C',1,15,15), ('D',2,24,6),
           ('A',3,24,6), ('B',1,6,24), ('C',2,15,15), ('D',3,6,24),
           ('D',1,24,6), ('C',2,24,6), ('B',2,6,24), ('C',3,6,24))
ENDPOINTS = {'L':'左','R':'右'}


def geometry(names):
    return '、'.join(f'{distance}cm为{location(n)}' for distance,n in zip((6,15,24),names,strict=True))


def build(index):
    book,b,u,v = CONFIGS[index]
    survey,images = SURVEYS[book],IMAGES[book]
    history = History(times=[clock(f'08:{r:02d}:59',62) for r in range(1,31)])
    history.add(1,'本次采样仿真有三个地标作业区，各有三个测绘子位，共N01—N09，名称没有空间顺序。'
        '环境图仅表示地标身份；导轨是题内工装，不在照片中测厘米。各区导轨基线30cm，'
        '三个台位距装配左端分别6、15、24cm，装配左端不是照片左侧。'
        'u、v来自固定的两个端点，精确满足u+v=30；u接装配左端时左距为u，u接右端时左距为v。'
        '各区三个子位均已实际到达并核验；地标、端序及N登记保持不变，组件没有交换。'
        '访问V、图I、组件T按完整ID连接，数字不编码位置，档案可乱序归档，不按相邻行相连。'
        'A—I分别报告N01—N09，J报告无法确定；提交action=select及option字母，或action=end放弃。'
        '只准一次调用，合法、非法或主动结束都终止；不提供移动试探、定位查询或额外测距。'
        '看图、推理及原生记忆检索不计调用。本次只报告子位，不实际钻进或评价岩性。',event='sampling_localization_protocol')
    for j,slot in enumerate(ARRIVALS[book]):
        names,end,component = survey[slot-1]
        text = f'{VISITS[slot-1]}已于第61日完成{ "、".join(location(n) for n in sorted(names))}三个子位停靠。'
        facts = {'event':'survey_visit'}
        if index < 6:
            image = images[slot-1]
            text += f'环境图{image}如下；装配左距登记：{geometry(names)}；u接装配{ENDPOINTS[end]}端，v接另一端。'
            facts['images'] = [attachment(image,HISTORY_FILES[slot-1])]
        history.add(2+j*6,text,**facts)
    for j,slot in enumerate(IMAGE_ORDER[book]):
        if index >= 6:
            history.add(3+j*6,f'本次归档：{images[slot-1]}为访问{VISITS[slot-1]}的环境图；采集日为第61日。',
                event='survey_image',images=[attachment(images[slot-1],HISTORY_FILES[slot-1])])
        else:
            history.add(3+j*6,'图像归档正常。',event='archive_health')
    for j,slot in enumerate(GEOMETRY_ORDER[book]):
        if index >= 6:
            names,end,component = survey[slot-1]
            detail = f'u接装配{ENDPOINTS[end]}端，v接另一端' if index < 12 else f'已安装组件{component}'
            history.add(5+j*6,f'本次归档：{VISITS[slot-1]}的装配左距登记：{geometry(names)}；{detail}；测绘日为第61日。',
                event='rail_geometry')
        else:
            history.add(5+j*6,'工装归档完成。',event='archive_health')
    for at,component in zip((20,21,22),('T61','T28','T43'),strict=True):
        if index >= 12:
            end = next(end for _,end,identifier in survey if identifier == component)
            history.add(at,f'本次归档：{component}稳定校准为u接装配{ENDPOINTS[end]}端，v接另一端；校准日为第61日。',
                event='range_calibration')
        else:
            history.add(at,'传感器健康检查正常。',event='sensor_health')
    for at in (4,6,7,10,12,13,16,18,19,23,25):
        history.add(at,('已结束采样的存档校验通过。','设备常规自检正常。','已归档数据备份完成。')[at%3],event='closed_sampling_archive')
    for at in (24,26):
        history.add(at,'已确认停靠N09，工具收回，未新拍环境图。',event='recent_stop')
    history.add(27,'已确认停靠N04，随后开始自主转位，没有记录未来目的地。',event='departed_stop')
    history.add(28,'转位过程完成，但完整运动量和终点定位记录缺失。',event='movement_log_incomplete')
    history.add(29,'相机、组件及导轨正常，组件没有交换，端序和N登记保持不变。',event='rail_health')
    history.add(30,'取样头已经静止，尚未接触新样品；最终可在任一已登记子位，也可回到N04或N09。',event='sampling_parked')
    names,end,_ = survey[b-1]
    x = u if end == 'L' else v
    task = task_shell('FM-E3-P2',index,group=f'FM-E3-P2:registration-{book}')
    attachments = [attachment('C01',QUERY_FILES[b-1])]
    if index < 12:
        attachments += [attachment(identifier,HISTORY_FILES[images.index(identifier)]) for identifier in sorted(images)]
    task.public = {'time_s':clock('09:00',62), 'max_steps':1, 'state_fields':[], 'actions':report_options(),
        'instruction':f'取样头已静止，位置登记暂不可用。环境图C01如下；测距u={u}cm，v={v}cm。请报告当前采样子位编号。',
        'range_cm':{'u':u,'v':v}, 'images':attachments}
    task.initial = {'time_s':clock('09:00',62),'reported_location':None}
    task.world = {'current_location':location(names[(6,15,24).index(x)]),
        'registrations':{images[j]:{'names':[location(n) for n in ns], 'u_endpoint':endpoint}
                         for j,(ns,endpoint,_) in enumerate(survey)}}
    task.rubric = {'score':'100 iff the first report is the exact current sampling subposition, otherwise 0'}
    task.design.update(visual_revision=VISUAL_REVISION, visual_input_note=VISUAL_INPUT_NOTE, visual_source_group='NASA-landmarks-P1-P2',
                       scoring_version='fm-e3-p2/6')
    return history.finish(task)


class Runtime(LandmarkRuntime):
    receipt = '采样子位报告已记录。'


GEOMETRY = r'6cm为(N\d{2})、15cm为(N\d{2})、24cm为(N\d{2})'


def reconstruct(history,current,*,assets):
    visual = image_identity(history,current,assets)
    arrivals,image_visits,positions,endpoints,installed,calibrations = {},{},{},{},{},{}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(V\d+)已于第61日完成(N\d{2}、N\d{2}、N\d{2})三个子位停靠。'
                rf'(?:环境图(I\d{{2}})如下；装配左距登记：{GEOMETRY}；u接装配(左|右)端，v接另一端。)?',text):
            visit,visited,image,*detail = match.groups()
            arrivals[visit] = set(visited.split('、'))
            if image:
                image_visits[image] = visit
                positions[visit] = detail[:3]
                endpoints[visit] = {'左':'L','右':'R'}[detail[3]]
        elif match := re.fullmatch(r'本次归档：(I\d{2})为访问(V\d+)的环境图；采集日为第61日。',text):
            image_visits[match[1]] = match[2]
        elif match := re.fullmatch(rf'本次归档：(V\d+)的装配左距登记：{GEOMETRY}；'
                r'(?:u接装配(左|右)端，v接另一端|已安装组件(T\d+))；测绘日为第61日。',text):
            visit,*detail = match.groups()
            positions[visit] = detail[:3]
            if detail[3]:
                endpoints[visit] = {'左':'L','右':'R'}[detail[3]]
            else:
                installed[visit] = detail[4]
        elif match := re.fullmatch(r'本次归档：(T\d+)稳定校准为u接装配(左|右)端，v接另一端；校准日为第61日。',text):
            calibrations[match[1]] = {'左':'L','右':'R'}[match[2]]
    if installed:
        if len(calibrations) != 3 or set(installed.values()) != calibrations.keys():
            raise ValueError('Every installed range assembly needs its own calibration')
        endpoints.update({visit:calibrations[component] for visit,component in installed.items()})
    if (len(arrivals) != 3 or positions.keys() != arrivals.keys() or endpoints.keys() != arrivals.keys()
            or image_visits.keys() != visual['history_images'].keys() or set(image_visits.values()) != arrivals.keys()
            or len(set().union(*arrivals.values())) != 9
            or any(set(positions[visit]) != names for visit,names in arrivals.items())):
        raise ValueError('Every visual worksite needs its complete surveyed positions and endpoint direction')
    registrations = {image:{'names':positions[visit], 'u_endpoint':endpoints[visit]} for image,visit in image_visits.items()}
    selected = registrations[visual['matched_image']]
    u,v = (current['range_cm'][key] for key in ('u','v'))
    if u+v != 30 or u not in (6,15,24) or v not in (6,15,24):
        raise ValueError('Measured endpoint distances must identify a surveyed subposition')
    x = u if selected['u_endpoint'] == 'L' else v
    return {**visual,'registrations':registrations,'current_location':selected['names'][(6,15,24).index(x)]}
