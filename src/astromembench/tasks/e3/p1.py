"""FM-E3-P1: recognize the worksite, then recover its case-local registration."""
import re

from ..common import History, clock, task_shell
from ..prose import paragraphs
from ...schema import story_timestamp
from .locations import location, report_options
from .landmarks import (HISTORY_FILES, QUERY_FILES, VISUAL_REVISION, VISUAL_INPUT_NOTE, LandmarkRuntime, attachment, gallery_attachment,
                        check_world, image_identity, next_action, report_cases as audit_cases)

VISUAL_AUDIT = True
NAMES = {'A': (3,8,1,6,2,9,4,7,5), 'B': (7,2,9,4,6,1,8,5,3),
         'C': (5,9,4,1,8,3,6,2,7), 'D': (2,6,8,5,9,7,1,3,4)}
IMAGES = ('I58','I21','I74','I36','I92','I47','I63','I15','I89')
VISITS = ('V43','V86','V19','V65','V28','V71','V54','V92','V37')
PACKAGES = ('B72','B14','B93','B46','B81','B25','B67','B38','B59')
ARRIVALS = {'A': (5,2,8,1,6,9,3,7,4), 'B': (3,9,4,7,1,5,8,2,6),
            'C': (8,6,1,5,9,3,2,4,7), 'D': (6,4,9,2,7,8,5,3,1)}
PACKET_ORDER = {'A': (3,7,1,9,4,6,2,5,8), 'B': (8,2,6,4,9,3,5,1,7),
                'C': (4,1,9,2,7,5,8,6,3), 'D': (9,5,3,8,1,2,7,4,6)}
IMAGE_ORDER = {'A': (8,4,6,2,9,1,5,3,7), 'B': (5,1,7,9,2,6,3,8,4),
               'C': (2,7,3,6,1,8,4,9,5), 'D': (7,3,5,1,8,4,9,6,2)}
# Individually reviewed FM rows: naming book, current object, last visited object.
CONFIGS = (('A',1,2), ('B',2,2), ('C',3,8), ('D',4,1), ('C',1,6), ('A',2,7),
           ('D',3,3), ('B',4,9), ('B',1,6), ('D',2,1), ('A',3,8), ('C',4,4),
           ('D',1,5), ('C',2,7), ('B',3,3), ('A',4,9))


def build(index):
    book, query, last = CONFIGS[index]
    names = NAMES[book]
    history = History(times=[clock(f'08:{r:02d}:59',42) for r in range(1,31)])
    history.add(1, '本次勘察有九个地标作业区N01—N09，各区均已实际到达，地标与N的登记保持不变，编号没有几何顺序。'
        '访问号V、采集包号B和图号I分别标识访问、图像采集包和环境影像，后缀不编码位置；'
        '档案可乱序收到，只有完整相同ID才指同一登记，归档顺序不是航迹。'
        '本次只恢复地标作业区身份，不估计相机坐标，不分析岩性；设备正常，能源足够。'
        'A—I分别报告N01—N09，J报告无法确定；提交action=select及option字母，或action=end放弃。'
        '只准一次调用，合法、非法或主动结束都终止，报告不移动平台；看图、推理及原生记忆检索不计调用。',
        event='worksite_registration_protocol')
    for j, b in enumerate(ARRIVALS[book]):
        visit, image, name = VISITS[b-1], IMAGES[b-1], location(names[b-1])
        arrived = clock('08:00',41) + j*1200
        text = f'{visit}于{story_timestamp(arrived)}抵达{name}，已驻留完成采集。'
        facts = {'event':'worksite_arrival', 'visit':visit, 'location':name, 'arrived_s':arrived}
        if index < 6:
            text += f'环境图{image}如下。'
            facts['images'] = [attachment(image,HISTORY_FILES[b-1])]
        history.add(j+2,text,**facts)
    for j, b in enumerate(PACKET_ORDER[book]):
        if index >= 12:
            history.add(j+11,f'本次归档：采集包{PACKAGES[b-1]}归属访问{VISITS[b-1]}；采集日为第41日。',
                event='package_index', package=PACKAGES[b-1], visit=VISITS[b-1])
        else:
            history.add(j+11,('已完成勘察的存储自检通过。','归档时钟检查正常。','已结束作业的载荷日志归档完成。')[j%3],
                event='closed_survey_archive')
    for j, b in enumerate(IMAGE_ORDER[book]):
        image = IMAGES[b-1]
        if index >= 6:
            binding = f'访问{VISITS[b-1]}的环境图' if index < 12 else f'采集包{PACKAGES[b-1]}所载的环境图'
            history.add(j+20,f'本次归档：{image}为{binding}；采集日为第41日。',
                event='image_archive', images=[attachment(image,HISTORY_FILES[b-1])])
        else:
            history.add(j+20,('设备自检正常。','归档介质检查通过。','已完成勘察的文件传输结束。')[j%3],
                event='survey_health')
    history.add(29,f'已实际重访{location(names[last-1])}，短测正常，没有新图片。',event='recent_worksite')
    history.add(30,'此后自主转位已经结束，平台静止；完整转位日志与当前N缺失，'
        '最终可在任意已登记作业区，也可回到刚访问过的区。',event='worksite_parked')
    task = task_shell('FM-E3-P1',index,group=f'FM-E3-P1:registration-{book}')
    images = [attachment('C01',QUERY_FILES[query-1])]
    if index < 12:
        images += [gallery_attachment(IMAGES[b-1],HISTORY_FILES[b-1]) for b in IMAGE_ORDER[book]]
    task.public = {'time_s':clock('09:00',42), 'max_steps':1, 'state_fields':[], 'actions':report_options(),
        'instruction':'勘察平台已静止，定位流暂不可用。当前地标影像C01如下。请报告当前地标作业区编号。',
        'images':images}
    task.initial = {'time_s':clock('09:00',42),'reported_location':None}
    task.world = {'current_location':location(names[query-1]),
        'registrations':{IMAGES[b]:location(names[b]) for b in range(9)}}
    task.rubric = {'score':'100 iff the first report is the exact current worksite, otherwise 0'}
    task.design.update(visual_revision=VISUAL_REVISION,visual_source_group='NASA-landmarks-P1-P2',
                       visual_input_note=VISUAL_INPUT_NOTE,
                       scoring_version='fm-e3-p1/6')
    return history.finish(task)


class Runtime(LandmarkRuntime):
    receipt = '作业区位置报告已记录。'


def reconstruct(history,current,*,assets):
    visual = image_identity(history,current,assets,gallery_derivatives=True)
    arrivals, packages, image_visits, image_packages = {}, {}, {}, {}
    for text in paragraphs(history):
        if match := re.fullmatch(r'(V\d+)于任务第41日\d{2}:\d{2}:\d{2}抵达(N\d{2})，已驻留完成采集。(?:环境图(I\d{2})如下。)?',text):
            visit,name,image = match.groups()
            arrivals[visit] = name
            if image:
                image_visits[image] = visit
        elif match := re.fullmatch(r'本次归档：采集包(B\d+)归属访问(V\d+)；采集日为第41日。',text):
            packages[match[1]] = match[2]
        elif match := re.fullmatch(r'本次归档：(I\d{2})为访问(V\d+)的环境图；采集日为第41日。',text):
            image_visits[match[1]] = match[2]
        elif match := re.fullmatch(r'本次归档：(I\d{2})为采集包(B\d+)所载的环境图；采集日为第41日。',text):
            image_packages[match[1]] = match[2]
    if image_packages:
        if len(packages) != 9 or set(image_packages.values()) != packages.keys():
            raise ValueError('Nine complete package-to-visit links are required')
        image_visits.update({image:packages[package] for image,package in image_packages.items()})
    if (len(arrivals) != 9 or len(set(arrivals.values())) != 9
            or image_visits.keys() != visual['history_images'].keys()
            or set(image_visits.values()) != arrivals.keys()):
        raise ValueError('Nine complete image-to-visit-to-location registrations are required')
    registrations = {image:arrivals[visit] for image,visit in image_visits.items()}
    return {**visual,'registrations':registrations,'current_location':registrations[visual['matched_image']]}
