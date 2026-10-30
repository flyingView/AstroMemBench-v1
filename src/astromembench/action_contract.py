"""Separate executable arguments from public descriptions of their effects."""
from copy import deepcopy


class ActionContract:
    def __init__(self, fields=('action', 'option'), parameters=None):
        self.fields = fields
        self.parameters = parameters or {}

    def inputs(self, name):
        return self.parameters.get(name, self.parameters.get('*', {}))

    def present(self, choices):
        result = []
        for choice in choices:
            item = {'arguments': {key: deepcopy(choice[key]) for key in self.fields if key in choice}}
            if 'description' in choice:
                item['description'] = choice['description']
            details = {key: deepcopy(value) for key, value in choice.items()
                       if key not in {*self.fields, 'description', 'parameters'}}
            if details:
                item['details'] = details
            result.append(item)
        return result

    def parameter_descriptions(self, choices):
        return {name: deepcopy(self.inputs(name)) for name in dict.fromkeys(c['action'] for c in choices)
                if self.inputs(name)}

    def error(self, submitted, choices):
        lead = '提交格式无效；'
        if not isinstance(submitted, dict):
            return lead + 'robot_action 的 action 参数必须是一个对象。'
        same = [c for c in choices if c['action'] == submitted.get('action')]
        if not same:
            return lead + '请使用当前 actions 中 arguments.action 列出的动作名称。details 中的 operation 只说明选项含义，不是提交入口。'
        fixed = {key for key in self.fields if key in same[0]}
        inputs = self.inputs(submitted['action'])
        required = fixed | {key for key, spec in inputs.items() if spec.get('required')}
        missing, extra = required - submitted.keys(), submitted.keys() - (fixed | inputs.keys())
        problems = []
        if missing:
            problems.append('缺少字段：' + '、'.join(sorted(missing)))
        if extra:
            problems.append('不能提交这些字段：' + '、'.join(sorted(extra)))
        if not problems:
            problems.append('字段值或类型不符合当前 arguments 与 action_parameters 的说明')
        return lead + '；'.join(problems) + '。复制当前所选 arguments 作为 action 对象；额外字段仅可填写本题当前 action_parameters 在该动作名称下声明的字段，并遵守其必填性、类型与格式。未声明的 evidence、理由或说明不得添加，不增加 arguments 或 parameters 包装层。'
