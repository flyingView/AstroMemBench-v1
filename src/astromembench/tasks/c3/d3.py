"""FM-C3-D3: native thirty-round transmission, acknowledgment and cleanup."""
from copy import deepcopy
import re

from ..common import History, clock, round_times, task_shell
from ..receipts import ReceiptRuntime
from ..prose import paragraphs, record_paragraphs
from ...action_contract import ActionContract

CONFIGS = (
    ('清待留留+-',3),('待留清留-+',3),('清异待留+-',3),('异清待待-+',4),
    ('待迟清留-+',4),('迟留待+--',5),('清待留清留待+-',4),('待清待留待清+-',5),
    ('清待待留待-++',6),('异待清异待-+-',5),('清待留清迟待+-',5),('迟待清留迟-+-',6),
    ('留待清留待留-+-+',6),('待留待清待待-+-+',8),('异待清留待异-+-+',6),('迟待清留迟待-+-+',8),
)


def _event(kind,data_id,*,batch='B17'):
    result = {'event':kind,'batch':batch,'data_id':data_id}
    if kind == 'complete':
        result.update(source='ground',recipient='ground',complete=True,
                      text=f'地面接收端完整确认：作业{batch}数据{data_id}已完整接收。')
    elif kind == 'sent':
        result.update(source='local',recipient='ground',text=f'星载发送完成：作业{batch}数据{data_id}已向地面接收端发送。')
    elif kind == 'request':
        result.update(source='local',recipient='ground',text=f'本地发送请求已受理：作业{batch}数据{data_id}，目的地面接收端。')
    else:
        result.update(source='local',text=f'本地删除完成：作业{batch}数据{data_id}唯一星上副本已删除。')
    return result


def build(index):
    codes,denominator = CONFIGS[index]
    states,work,events = {},{},[]
    anchors = {1:clock('08:01'),30:clock('08:50')}

    def record(at,minute,kind,data_id,*,second=0,batch='B17'):
        stamp = clock(f'08:{minute:02d}:{second:02d}')
        anchors[at] = max(anchors.get(at,stamp),stamp)
        events.append((at,stamp,_event(kind,data_id,batch=batch)))

    for position,code in enumerate(codes):
        data_id = f'D{position+1:02d}'
        states[data_id] = {'sent':code not in '+-','confirmed':code in '清待','exists':code != '清'}
        if code in '待迟+-':
            work[data_id] = {'待':'cleanup','迟':'cleanup','+':'new_confirmed','-':'new_retained'}[code]
        if code in '+-':
            continue
        if index < 6:
            sent,ack,deleted = 5+8*position,6+8*position,7+8*position
        elif index < 12:
            sent,ack,deleted = 5+6*position,8+6*position,9+6*position
        else:
            sent,ack,deleted = 4+5*position,6+5*position,8+5*position
        if index == 10:
            sent = (5,11,17,22,29,34)[position]
            ack = {0:7,1:14,3:24,5:38}.get(position)
            deleted = {0:8,3:25}.get(position)
        at = 3+3*position
        if index >= 12:
            record(at,sent,'request',data_id)
        record(at,sent,'sent',data_id,second=1 if index >= 12 else 0)
        if code in '清待异':
            record(at+1,ack,'complete',data_id,batch='B18' if code == '异' else 'B17')
        if code == '清':
            record(at+2,deleted,'deleted',data_id)
    history = History(times=round_times(anchors))
    catalog = list(states)
    history.add(1,'B17本轮数据回传清单中各项在作业开始时均已有唯一星上副本。按清单编号顺序每项首次发送一次，'
                '已发未确认不重发。通信、编码及设备正常，不考重传；B18是此前独立作业，可复用编号。'
                '只有地面接收端对同B17同编号的明确完整确认允许删除唯一副本，本地受理或发送完成不能替代。'
                '已确认最迟结束前清理，未确认保留；无确认不等于地面未收到。完成全部首次发送、已确认清理后结束，不无限等待。'
                '发送已发或无副本项、重复删除各记一次冗余；跳过更早未发项也记一次，但本次发送仍真实完成。'
                '每步最多记一次，错误处理不反馈隐私状态；避免上述冗余。删除仍存在而未确认的副本会丢失数据并立即终止任务，未来确认不补救。'
                '尚未发送的项须完成首次发送，已有完整确认或后来获得完整确认的现存副本须清理；其余已发但未确认副本继续保留。历史已清理项不重复处理。'
                '总环境额度3N+2，包括结束与格式错误；没有另设累计三次格式错误终止。记忆访问不计环境提交。',
                event='downlink_protocol',batch='B17',catalog=catalog,recipient='ground')
    for at,stamp,event in sorted(events,key=lambda row:(row[0],row[1])):
        history.add(at,event.pop('text'),occurred=stamp,received=stamp,**event)
    history.add(30,'巡航例行检查结束。',event='routine_check')
    task = task_shell('FM-C3-D3',index,current_input_group=f'FM-C3-D3-N{len(codes)}')
    task.public = {'time_s':clock('09:00'),'batch':'B17','catalog':catalog,'recipient':'ground',
                   'instruction':'继续执行B17本轮数据回传作业。','max_steps':3*len(codes)+2,'state_fields':[],
                   'actions':[{'action':action,'data_id':data_id,'description':
                               f'向地面接收端首次发送{data_id}。' if action == 'send' else f'删除{data_id}唯一星上副本。'}
                              for action in ('send','delete') for data_id in catalog]+[{'action':'end','description':'结束本轮回传。'}]}
    missing = [f for f,s in states.items() if not s['sent']]
    task.initial = {'files':states,'errors':0,'unsafe':False,'late_released':False}
    task.world = {'work':work,'denominator':denominator,'initial_missing':missing,'late_trigger':missing[0],
                  'new_receipts':[f'D{i+1:02d}' for i,c in enumerate(codes) if c == '+'],
                  'late_receipts':[f'D{i+1:02d}' for i,c in enumerate(codes) if c == '迟'],
                  'cleanup':[f'D{i+1:02d}' for i,c in enumerate(codes) if c in '待迟+']}
    task.rubric = {'score':'max(0,100*(completed_work_shares-redundancies)/fixed_K)',
                   'unsafe_delete':'immediate zero','new_confirmed_sent_retained_share':0.5}
    return history.finish(task)


class Runtime(ReceiptRuntime):
    action_contract = ActionContract(fields=('action','data_id'))
    event_builder = staticmethod(_event)
    format_error_limit = None

    def grade(self):
        if self.state['unsafe']:
            return 0
        half_shares = 0
        for data_id,kind in self.task.world['work'].items():
            item = self.state['files'][data_id]
            if kind == 'cleanup':
                half_shares += 2*int(item['confirmed'] and not item['exists'])
            elif kind == 'new_confirmed' and item['sent'] and item['confirmed']:
                half_shares += 1 if item['exists'] else 2
            elif kind == 'new_retained':
                half_shares += 2*int(item['sent'] and item['exists'])
        return max(0,100*(half_shares-2*self.state['errors'])/(2*self.task.world['denominator']))

    def submit(self,action):
        self.feedback_events = []
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or set(action) != {'action','data_id'} or not isinstance(action['data_id'],str) or action['data_id'] not in self.state['files']:
            return self.invalid()
        data_id,item = action['data_id'],self.state['files'][action['data_id']]
        if action['action'] == 'send':
            if item['sent'] or not item['exists']:
                self.state['errors'] += 1
                self.feedback = '操作处理结束。'
                return
            first_missing = next(f for f,s in self.state['files'].items() if not s['sent'])
            if first_missing != data_id:
                self.state['errors'] += 1
            item['sent'] = True
            self._emit('sent',data_id)
            confirmations = []
            if data_id == self.task.world['late_trigger'] and not self.state['late_released']:
                self.state['late_released'] = True
                confirmations.extend(self.task.world['late_receipts'])
            if data_id in self.task.world['new_receipts']:
                confirmations.append(data_id)
            for confirmed in confirmations:
                self.state['files'][confirmed]['confirmed'] = True
                self._emit('complete',confirmed)
        elif action['action'] == 'delete':
            if not item['exists']:
                self.state['errors'] += 1
                self.feedback = '操作处理结束。'
                return
            item['exists'] = False
            self._emit('deleted',data_id)
            if not item['confirmed']:
                self.state['unsafe'] = True
                self.end('unsafe_delete')
        else:
            self.invalid()


def _absorb(states,texts,batch):
    scope = re.escape(batch)
    for text in texts:
        sent = re.fullmatch(rf'星载发送完成：作业{scope}数据(D\d+)已向地面接收端发送。',text)
        complete = re.fullmatch(rf'地面接收端完整确认：作业{scope}数据(D\d+)已完整接收。',text)
        deleted = re.fullmatch(rf'本地删除完成：作业{scope}数据(D\d+)唯一星上副本已删除。',text)
        matched = sent or complete or deleted
        if not matched or matched[1] not in states:
            continue
        item = states[matched[1]]
        if sent:
            item['sent'] = True
        elif complete:
            if not item['sent']:
                raise ValueError('Ground receipt before transmission')
            item['confirmed'] = True
        elif deleted:
            item['exists'] = False


def reconstruct(history,current):
    states = {f:{'sent':False,'confirmed':False,'exists':True} for f in current['catalog']}
    _absorb(states,paragraphs(history),current['batch'])
    return {'files':states,'initial_files':deepcopy(states)}


def next_action(facts,current):
    _absorb(facts['files'],record_paragraphs(current.get('feedback_events',[])),current['batch'])
    for data_id,item in facts['files'].items():
        if item['exists'] and item['confirmed']:
            return {'action':'delete','data_id':data_id}
    for data_id,item in facts['files'].items():
        if not item['sent']:
            return {'action':'send','data_id':data_id}
    return {'action':'end'}


def check_world(task,facts):
    initial = facts['initial_files']
    if initial != task.initial['files']:
        raise ValueError('Downlink initial state differs from public scoped facts')
    missing = [f for f,s in initial.items() if not s['sent']]
    deleted = [f for f,s in facts['files'].items() if initial[f]['exists'] and not s['exists']]
    work = set(missing)|set(deleted)
    if missing != task.world['initial_missing'] or deleted != task.world['cleanup'] or len(work) != task.world['denominator']:
        raise ValueError('Downlink work shares differ from publicly reachable completion')


def audit_cases(task,facts,solution):
    k = task.world['denominator']
    sends = [a for a in solution if a['action'] == 'send']
    sent_value = sum(0.5 if a['data_id'] in task.world['new_receipts'] else 1 for a in sends)
    cases = [(sends+[{'action':'end'}],100*sent_value/k),([{}]*3+solution,100)]
    for data_id,item in facts['initial_files'].items():
        if item['exists'] and not item['confirmed']:
            cases.append(([{'action':'delete','data_id':data_id}],0))
        if item['sent']:
            cases.append(([{'action':'send','data_id':data_id}]+solution,100*(k-1)/k))
    cases.append(([sends[1]]+[a for a in solution if a != sends[1]],100*(k-1)/k))
    return cases
