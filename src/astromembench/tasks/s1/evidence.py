"""One irreversible menu operation with explicitly declared finite evidence."""
from copy import deepcopy

from ...action_contract import ActionContract
from ...environment import TaskRuntime

CATALOG = tuple(f'N{i:02d}' for i in range(1,21))


def evidence_contract(slots,description):
    return ActionContract(parameters={'select':{'evidence':{'type':'object','required':False,
        'description':description,'properties':{slot:{'type':['string','null'],'enum':[*CATALOG,None,'']} for slot in slots},
        'additionalProperties':False}}})


def evidence_list_contract(description,limit=3):
    return ActionContract(parameters={'select':{'evidence':{'type':'array','required':False,
        'description':description,'items':{'type':'string','enum':list(CATALOG)},'maxItems':limit,'uniqueItems':True}}})


class EvidenceRuntime(TaskRuntime):
    evidence_slots = ()
    accepted_feedback = ''

    def actions(self):
        return [] if self.done else super().actions()

    def execute(self,operation,evidence):
        raise NotImplementedError

    def empty_evidence(self):
        return {}

    def valid_evidence(self,evidence):
        return isinstance(evidence,dict) and not evidence.keys()-set(self.evidence_slots) and all(
            value is None or isinstance(value,str) and value in (*CATALOG,'') for value in evidence.values())

    def submit(self,action):
        if action == {'action':'end'}:
            self.end('ended')
            return
        if not isinstance(action,dict) or not {'action','option'} <= action.keys() or action.keys()-{'action','option','evidence'} or action['action'] != 'select':
            self.feedback = '格式不符'
            return
        option = next((row for row in self.actions() if isinstance(action['option'],str) and row['option'] == action['option']),None)
        evidence = action.get('evidence',self.empty_evidence())
        if option is None or not self.valid_evidence(evidence):
            self.feedback = '格式不符'
            return
        score = self.execute(deepcopy(option['operation']),evidence)
        self.feedback = self.accepted_feedback
        self.end('completed',score=score,full_credit=score == 100)


class EvidenceListRuntime(EvidenceRuntime):
    evidence_limit = 3

    def empty_evidence(self):
        return []

    def valid_evidence(self,evidence):
        return isinstance(evidence,list) and len(evidence) <= self.evidence_limit and all(
            isinstance(identifier,str) and identifier in CATALOG for identifier in evidence) and len(set(evidence)) == len(evidence)
