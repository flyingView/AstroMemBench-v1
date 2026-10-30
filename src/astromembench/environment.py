"""Execute one submitted operation and preserve full-precision task outcomes."""
from copy import deepcopy
from math import isfinite

from .tasks import template_module
from .schema import story_timestamp
from .action_contract import ActionContract


class TaskRuntime:
    """Shared protocol mechanics; physical transitions belong to each template."""
    action_contract = ActionContract()
    def __init__(self, task):
        self.task = task
        self.state = deepcopy(task.initial)
        self.steps = 0
        self.done = False
        self.score = 0.0
        self.full_credit = False
        self.termination = ""
        self.feedback = ""
        self.answer = None
        self.trace = []
        self.facts = {}

    def actions(self):
        return deepcopy(self.task.public["actions"])

    def public_state(self):
        return {key: deepcopy(self.state[key]) for key in self.task.public.get("state_fields", [])}

    def observation(self):
        public = {key: deepcopy(value) for key, value in self.task.public.items()
                  if key not in {"actions", "state_fields", "options_by_step"}}
        state = self.public_state()
        if "time_s" in state:
            state["current_time"] = story_timestamp(state["time_s"])
        if "time_s" in public:
            public["current_time"] = story_timestamp(public["time_s"])
        choices = self.actions()
        parameters = self.action_contract.parameter_descriptions(choices)
        return {**public, "state": state, "actions": self.action_contract.present(choices),
                **({'action_parameters': parameters} if parameters else {}),
                "feedback": self.feedback, "remaining_actions": self.task.public["max_steps"] - self.steps}

    def end(self, reason, *, score=None, full_credit=None):
        if score is not None:
            self.score = score
        if full_credit is not None:
            self.full_credit = full_credit
        self.done = True
        self.termination = reason

    def invalid(self):
        self.feedback = self.action_contract.error(self.answer, self.actions())

    def submit(self, action):
        raise NotImplementedError

    def step(self, action):
        if self.done:
            raise RuntimeError("Task has already ended")
        self.steps += 1
        self.feedback = ""
        self.answer = deepcopy(action)
        self.submit(action)
        self.trace.append({"step": self.steps, "action": deepcopy(action), "feedback": self.feedback})
        if not self.done and self.steps >= self.task.public["max_steps"]:
            self.end("step_limit")
        return self.observation()

    def result(self):
        if not self.done:
            raise RuntimeError("Cannot grade an unfinished task")
        if not isfinite(self.score) or not 0 <= self.score <= 100 or self.full_credit != (self.score == 100):
            raise ValueError("Invalid unrounded task outcome")
        return {"score": self.score, "full_credit": self.full_credit, "success": self.full_credit,
                "termination": self.termination, "steps": self.steps, "answer": deepcopy(self.answer),
                "final_state": deepcopy(self.state), "terminal_facts": deepcopy(self.facts),
                "actions": deepcopy(self.trace), "scoring_version": self.task.design["scoring_version"]}


def Environment(task):
    """Only task public inputs and explicit runtime projections reach the agent."""
    task.validate()
    return template_module(task.template).Runtime(task)


class SingleChoiceRuntime(TaskRuntime):
    """One actual operation is final; malformed submissions use only format budget."""
    def grade(self, option):
        correct = option["operation"] == self.task.world["correct_operation"]
        return (100 if correct else 0), correct

    def submit(self, action):
        from .tasks.common import selected_option
        if action == {"action": "end"}:
            self.end("ended")
            return
        option = selected_option(self.actions(), action)
        if option is None:
            self.invalid()
            return
        score, full_credit = self.grade(option)
        self.facts["executed_operation"] = deepcopy(option["operation"])
        self.feedback = "操作已执行，记录已存档。"
        self.end("completed", score=score, full_credit=full_credit)
