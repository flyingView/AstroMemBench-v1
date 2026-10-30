"""FM-S1-O1: visit-bound occupancy and person-wise shared clearance evidence."""
from copy import deepcopy
from itertools import combinations
import re

from ..common import History, clock, fixed_options, task_shell
from ..prose import STORY_STAMP, paragraphs, seconds
from ...schema import story_timestamp
from .evidence import CATALOG, EvidenceListRuntime, evidence_list_contract

# Target, reference layout, actual per-person visit sequence, confirmed persons.
CONFIGS = (
    ('A','a','0',''),('C','b','I','a'),('E','c','E','a'),('B','d','R',''),
    ('F','b','0','a'),('D','a','D','a'),('B','c','0E','a'),('D','a','I0','b'),
    ('F','d','EE','ab'),('C','c','DE','ab'),('A','d','E0','a'),('B','a','RD','a'),
    ('D','c','IER','b'),('F','d','EEE','ac'),('C','c','000','b'),('F','d','RDD','ac'),
)
LAYOUTS = {
    'a':(8,15,3,11,4,18,6,13,20,2,17,9,5,14),
    'b':(17,4,12,6,15,2,19,8,3,14,10,20,5,11),
    'c':(5,18,9,16,2,11,7,20,13,4,8,1,17,12),
    'd':(14,3,17,8,19,6,12,1,11,20,4,15,9,18),
}


def initial_model(zone,people):
    return {'zone':zone,'people':{person:{'visit':0,'ticket':None} for person in people},'tickets':{},'evidence':{}}


def statuses(model,people):
    return {person:{'inside':model['people'][person]['ticket'] is not None,'active_ticket':model['people'][person]['ticket']} for person in people}


def apply_record(model,record):
    event,claims = record['event'],{}
    if event == 'zone_entered':
        person,ticket = record['person'],record['ticket']
        state = model['people'][person]
        if record['zone'] != model['zone'] or state['ticket'] is not None or ticket in model['tickets']:
            raise ValueError('An actual entry needs a fresh ticket and a person currently outside this zone')
        state['visit'] += 1
        state['ticket'] = ticket
        model['tickets'][ticket] = {'person':person,'visit':state['visit'],'entered_s':record['occurred_s'],'left_s':None}
        claims[person] = deepcopy(state)
    elif event == 'zone_exited':
        person,ticket = record['person'],record['ticket']
        visit = model['tickets'][ticket]
        if record['zone'] != model['zone'] or visit['person'] != person:
            raise ValueError('An exit must identify the actual person and their entry ticket')
        if visit['left_s'] is None:
            visit['left_s'] = record['occurred_s']
        if model['people'][person]['ticket'] == ticket:
            model['people'][person]['ticket'] = None
        # A repeated old exit cannot certify a later visit, even when the same name appears.
        claims[person] = {'visit':visit['visit'],'ticket':None}
    elif event == 'zone_status_confirmed' and record['zone'] == model['zone']:
        if record['statuses'] != statuses(model,record['statuses']):
            raise ValueError('An actual clearance receipt must report each named person and active ticket')
        claims = {person:deepcopy(model['people'][person]) for person in record['statuses']}
    if record.get('record_id') in CATALOG:
        model['evidence'][record['record_id']] = {'zone':record['zone'],'event':event,'claims':claims}


def supported_people(model,evidence,start):
    return [person for person,state in model['people'].items() if (state['ticket'] is None) == start and any(
        (record := model['evidence'].get(identifier)) is not None and record['zone'] == model['zone']
        and record['claims'].get(person) == state for identifier in evidence)]


def build(index):
    zone,layout,sequences,confirmed = CONFIGS[index]
    people = list('abc'[:len(sequences)])
    other = 'ABCDEF'[('ABCDEF'.index(zone)+1)%6]
    roles = ('G','a1','b1','c1','a_out','b_out','c_out','a2','b2','c2','Q','Z','other','P')
    identifiers = dict(zip(roles,(f'N{n:02d}' for n in LAYOUTS[layout]),strict=True))
    history,model = History(),initial_model(zone,people)
    people_text = '、'.join(people)
    history.add(1,f'目标被检区{zone}，仅{people_text}获准进入，其他人员无法进入；初始所有人在区外，全部通行记账且日志完整。'
        '每次实际进入产生新票，离场只绑定该人的该张票；已离场旧票的转录或重复确认不再减少人数，也不注销后来新票。'
        '净空证覆盖逐名所列人员，之后只有某人再次进入才使这张证对该人失效；未再入者的证明继续有效，不能全局撤销多人证明。'
        '全部获准人员当前均在区外才启动预置主动透照巡检，否则保持。仪器、屏蔽正常，范围固定，不需设计照射、维修或计算剂量。'
        '未来计划不代表实际通行，10:00后的计划不会自动执行。当前无额外询问或净空检查动作，原生记忆检索不耗环境动作。'
        '菜单1启动A/2保持A/3启动B/4保持B/5启动C/6保持C/7启动D/8保持D/9启动E/10保持E/11启动F/12保持F。'
        '提交仅action=select、菜单字符串option及可选evidence数组；最多3个不同的严格N01—N20编号，可空，缺省为空数组；不接受字典、重复号、多个号合成字符串或额外字段。'
        '操作须引用实际发生的N事件。启动须为每位获准人员提供其当前在外的有效证明，共享证明可支持多名人员。'
        '保持时，任一充分证明某人当前在内的引文即可说明无法启动；全空或未发生编号不能充当事实依据。'
        '退出后的旧进入票不证明当前在内；未注销新票实际入场和同事实当前状态回执都可充分。其他区净空不能证明本区。'
        '最多3次含格式错提交，格式错只反馈格式不符且耗次，第三次耗尽即结束；首次有效选择真实执行后终止，不净空启动不可逆，不能重答。'
        '固定有效反馈巡检操作及引用记录已登记，不报业务真值、得分或证据判断。end仅action=end并直接结束，不猜自然语言意图。',
        event='zone_clearance_protocol',zone=zone,authorized_people=people,evidence_catalog=CATALOG)

    def record(at,role,text,**facts):
        identifier = identifiers[role]
        apply_record(model,{'record_id':identifier,'occurred_s':clock(f'08:{at:02d}'),**facts})
        if facts['event'] in ('zone_entered','zone_exited'):
            text = f'{story_timestamp(clock(f"08:{at:02d}"))}，'+text
        history.add(at,f'{identifier}：'+text,record_id=identifier,**facts)
        return deepcopy(history.events[at-1].records[-1].data)

    record(2,'G',f'实际逐名确认{zone}的获准人员{people_text}全部在外，均无未注销入场票。',
        event='zone_status_confirmed',zone=zone,statuses=statuses(model,people))
    exits = {}
    for at in range(4,21):
        for position,(person,sequence) in enumerate(zip(people,sequences,strict=True)):
            if at == 4+2*position and sequence != '0':
                record(at,person+'1',f'{person}以新票{person}1实际进入{zone}。',
                    event='zone_entered',zone=zone,person=person,ticket=person+'1')
            if at == 10+2*position and sequence in 'ERD':
                exits[person] = record(at,person+'_out',f'{person}的一号入场票{person}1已实际离开{zone}，注销该票。',
                    event='zone_exited',zone=zone,person=person,ticket=person+'1')
            if at == 16+2*position and sequence in 'RD':
                record(at,person+'2',f'{person}以新票{person}2实际再次进入{zone}。',
                    event='zone_entered',zone=zone,person=person,ticket=person+'2')
    if confirmed:
        current = statuses(model,confirmed)
        status_text = '；'.join(f'{person}在区内、未注销入场票{state["active_ticket"]}' if state['inside']
            else f'{person}在区外、无未注销入场票' for person,state in current.items())
        record(22,'Q',f'实际逐名确认{zone}当前人员状态：{status_text}。只确认，不改变通行状态。',
            event='zone_status_confirmed',zone=zone,statuses=current)
    archived = [exits[person] for person,sequence in zip(people,sequences,strict=True) if sequence == 'D']
    if archived:
        quotes = [{key:old[key] for key in ('record_id','person','ticket','occurred_s','occurred_at','text')} for old in archived]
        record(24,'Z','归档转录旧一号票离场原文：'+'；'.join(q['text'] for q in quotes)
            +'。仅重复归档，不是新离场，不注销任何后来新票。',event='zone_exit_archive',zone=zone,archived_exits=quotes)
    record(26,'other',f'另一被检区{other}实际确认获准人员{people_text}全在该区外；这不是{zone}的净空回执。',
        event='zone_status_confirmed',zone=other,statuses={person:{'inside':False,'active_ticket':None} for person in people})
    record(27,'P',f'{zone}下一班入区/离区请求已安排10:10，本轮均尚未发生，不自动执行。',
        event='zone_access_scheduled',zone=zone,scheduled_s=clock('10:10'),executed=False)
    history.add(29,'屏蔽与仪器保持正常，没有新人员通行。',event='zone_instruments_ready')
    history.add(30,'准备结束，等待本阶段巡检指令。',event='zone_inspection_ready')
    task = task_shell('FM-S1-O1',index,current_input_group=f'FM-S1-O1-{zone}')
    task.public = {'instruction':f'继续目标{zone}本阶段巡检，请提交下一项操作及已有凭据。',
        'zone':zone,'time_s':clock('09:00'),'max_steps':3,'state_fields':[],
        'actions':fixed_options({'description':f'{"启动" if start else "保持"}{name}',
            'operation':{'zone':name,'start':start}} for name in 'ABCDEF' for start in (True,False))}
    task.initial = {'time_s':clock('09:00'),'inspections':{name:'ready' for name in 'ABCDEF'}}
    task.world = model
    task.rubric = {'metric':'safe_inspection_with_personwise_visit_bound_clearance','range':[0,100]}
    return history.finish(task)


class Runtime(EvidenceListRuntime):
    accepted_feedback = '巡检操作及引用记录已登记。'
    action_contract = evidence_list_contract('至多3个不同的严格N01—N20原始编号组成的数组；可空或省略，不接受重复编号、null项、字典或额外字段。')

    def execute(self,operation,evidence):
        model,zone = self.task.world,self.task.public['zone']
        start = all(state['ticket'] is None for state in model['people'].values())
        correct = operation == {'zone':zone,'start':start}
        occurred = any(identifier in model['evidence'] for identifier in evidence)
        supported = supported_people(model,evidence,start)
        score = (20+80*len(supported)/len(model['people']) if start else 100 if supported else 20) if correct and occurred else 0
        if operation['start']:
            self.state['inspections'][operation['zone']] = 'started'
        self.facts = {'executed_operation':operation,'operation_correct':correct,'cited_existing_event':occurred,
            'supported_people':supported,'unsafe_target_start':operation['zone'] == zone and operation['start'] and not start}
        return score


def _people_states(text):
    result = {}
    for part in text.split('；'):
        if match := re.fullmatch(r'([abc])在区外、无未注销入场票',part):
            person,state = match[1],{'inside':False,'active_ticket':None}
        elif match := re.fullmatch(r'([abc])在区内、未注销入场票([abc]\d+)',part):
            person,state = match[1],{'inside':True,'active_ticket':match[2]}
        else:
            raise ValueError('A clearance receipt must print each person and their actual ticket status')
        if person in result:
            raise ValueError('A clearance receipt must identify each person once')
        result[person] = state
    return result


def _zone_record(text,zone):
    if match := re.fullmatch(r'实际逐名确认([A-F])的获准人员([abc](?:、[abc])*)全部在外，均无未注销入场票。',text):
        return {'event':'zone_status_confirmed','zone':match[1],
            'statuses':{person:{'inside':False,'active_ticket':None} for person in match[2].split('、')}}
    if match := re.fullmatch(rf'({STORY_STAMP})，([abc])以新票([abc]\d+)实际(?:再次)?进入([A-F])。',text):
        return {'event':'zone_entered','zone':match[4],'person':match[2],'ticket':match[3],'occurred_s':seconds(match[1])}
    if match := re.fullmatch(rf'({STORY_STAMP})，([abc])的一号入场票([abc]\d+)已实际离开([A-F])，注销该票。',text):
        return {'event':'zone_exited','zone':match[4],'person':match[2],'ticket':match[3],'occurred_s':seconds(match[1])}
    if match := re.fullmatch(r'实际逐名确认([A-F])当前人员状态：(.+)。只确认，不改变通行状态。',text):
        return {'event':'zone_status_confirmed','zone':match[1],'statuses':_people_states(match[2])}
    if re.fullmatch(r'归档转录旧一号票离场原文：.+。仅重复归档，不是新离场，不注销任何后来新票。',text):
        return {'event':'zone_exit_archive','zone':zone}
    if match := re.fullmatch(r'另一被检区([A-F])实际确认获准人员([abc](?:、[abc])*)全在该区外；这不是([A-F])的净空回执。',text):
        if match[1] == zone or match[3] != zone:
            raise ValueError('Other-zone clearance must be distinct from the declared target')
        return {'event':'zone_status_confirmed','zone':match[1],
            'statuses':{person:{'inside':False,'active_ticket':None} for person in match[2].split('、')}}
    if match := re.fullmatch(r'([A-F])下一班入区/离区请求已安排\d{2}:\d{2}，本轮均尚未发生，不自动执行。',text):
        return {'event':'zone_access_scheduled','zone':match[1]}
    return None


def reconstruct(history,current):
    model = None
    for text in paragraphs(history):
        if match := re.match(r'目标被检区([A-F])，仅([abc](?:、[abc])*)获准进入，其他人员无法进入；初始所有人在区外，全部通行记账且日志完整。',text):
            model = initial_model(match[1],match[2].split('、'))
            if model['zone'] != current['zone']:
                raise ValueError('Inspection must use the registered target zone')
        elif model is not None:
            numbered = re.fullmatch(r'(N\d{2})：(.+)',text)
            record = _zone_record(numbered[2] if numbered else text,model['zone'])
            if record is not None:
                if numbered:
                    record['record_id'] = numbered[1]
                apply_record(model,record)
    return model


def next_action(facts,current):
    start = all(state['ticket'] is None for state in facts['people'].values())
    for count in range(1,4):
        for evidence in combinations(facts['evidence'],count):
            supported = supported_people(facts,evidence,start)
            enough = len(supported) == len(facts['people']) if start else bool(supported)
            if enough:
                arguments = next(row['arguments'] for row in current['actions'] if row['details']['operation'] == {'zone':current['zone'],'start':start})
                return {**arguments,'evidence':list(evidence)}
    raise ValueError('A valid inspection decision needs sufficient public evidence within three references')


def check_world(task,facts):
    if facts != task.world:
        raise ValueError('Clearance must follow each person and actual entry ticket, not repeated archived exits')


def audit_cases(task,facts,solution):
    command = solution[0]
    cases = [([{'action':'select','option':row['option'],'evidence':command['evidence']}],100 if row['option'] == command['option'] else 0)
        for row in task.public['actions']]
    start = all(state['ticket'] is None for state in facts['people'].values())
    useful = [identifier for identifier in facts['evidence'] if supported_people(facts,[identifier],start)]
    references = [[],*([identifier] for identifier in CATALOG),*(list(group) for count in (2,3) for group in combinations(useful,count))]
    for evidence in references:
        occurred = any(identifier in facts['evidence'] for identifier in evidence)
        covered = len(supported_people(facts,evidence,start))
        score = (20+80*covered/len(facts['people']) if start else 100 if covered else 20) if occurred else 0
        cases.append(([{**command,'evidence':evidence}],score))
    return cases+[([{}]*2+solution,100),([{}]*3,0)]
