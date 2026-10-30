"""Offline protocol example: sample public actions, with no access to answers.

This demonstrates the interface, not useful agent performance. Replace the
operation handlers with your own agent/model/memory calls. stdout is JSONL only;
send diagnostics to stderr. No benchmark package or task files are imported.
"""
import json
import os
import random
import sys
from uuid import uuid4


class RandomAdapter:
    def __init__(self, config):
        self.seed = config.get('seed', 1729)
        self.random = random.Random(self.seed)
        self.conversation_id = None

    def handle(self, operation, payload):
        if operation == 'reset':
            self.random.seed(self.seed)
            self.conversation_id = None
            return {'cleared': True}
        if operation == 'new_session':
            self.conversation_id = uuid4().hex
            return {'conversation_id': self.conversation_id}
        if operation == 'history':
            # A real adapter must finish its model/memory work before acknowledging.
            return {'processed': True, 'assistant_text': '收到', 'action_attempted': False}
        if operation == 'observe':
            actions = payload.get('actions', [])
            if not actions:
                return {'action_submitted': True, 'action': {'action': 'end'}}
            selected = self.random.choice(actions)
            # Optional task-specific fields may be required. This deliberately
            # naive example does not infer them, and may receive a zero score.
            return {'action_submitted': True, 'action': selected['arguments']}
        if operation in {'feedback', 'end'}:
            return {'processed': True}
        raise ValueError(f'Unknown operation: {operation}')


def main():
    adapter = RandomAdapter(json.loads(os.environ.get('ASTROMEMBENCH_CONFIG', '{}')))
    for line in sys.stdin:
        message = json.loads(line)
        try:
            if message.get('protocol') != 'astromembench/2':
                raise ValueError('Unsupported protocol')
            result = adapter.handle(message['operation'], message['payload'])
            reply = {'id': message['id'], 'result': result}
        except Exception as exc:
            reply = {'id': message['id'], 'error': {'kind': 'agent', 'message': str(exc)}}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
