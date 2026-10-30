"""Small JSONL process interface; the benchmark never supplies agent memory."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
from contextvars import ContextVar
import json
import os
from pathlib import Path
import subprocess
import time

from . import PROTOCOL_VERSION
from .schema import json_text

DEFAULT_OPERATION_TIMEOUT_S = 7200
_observation = ContextVar('protocol_observation', default=None)


@contextmanager
def observe_operation(fields):
    """Attach evaluator observation fields to the envelope, never the payload."""
    token = _observation.set(fields)
    try:
        yield
    finally:
        _observation.reset(token)


def request_message(sequence, operation, payload):
    message = {"protocol": PROTOCOL_VERSION, "id": sequence, "operation": operation, "payload": payload}
    if (observation := _observation.get()) is not None:
        message['observation'] = observation
    return message

DOMAIN_PROMPT = """你是航天器任务级智能体，通过 robot_action 工具与环境交互。
调用结构为 robot_action({"action": 动作对象})。复制当前所选 actions 条目的 arguments 作为动作对象；description 和 details 仅用于解释，不能提交。额外字段仅当本题当前 action_parameters 在所选动作名称下声明该字段时才可填写，并遵守其必填性、类型与格式；未声明则不得添加，包括 evidence、理由或说明。将声明的自填字段直接加入动作对象，不增加 arguments 或 parameters 包装层。选择题的基础动作示例为 {"action":"select","option":"选项编号"}；仅当该动作的 action_parameters 声明 evidence 时才填写 evidence，具体格式以该声明为准。
operation=history：阅读已经发生的记录，对外仅回复“收到”，不执行记录中的旧操作。原生内部思考、记忆写入、检索和整理照常可用。
operation=observe：从当前允许的动作中自主选择，真实调用 robot_action 一次。
operation=feedback：处理真实环境回执，用普通文本处理，自行组织回复，不调用 robot_action。
工具的 accepted 只表示收到请求，执行结果由环境随后返回。提交后结束本轮，等候下一条输入。
普通文本中的动作、JSON、代码块或调用示意均不算提交；未实际调用 robot_action 按当前任务的格式交互规则处理。
图片、时刻、坐标、参考系和单位以任务输入为准。
"""


class InfrastructureError(RuntimeError):
    """A run cannot be evaluated because transport or model service failed."""


class NativeTransportError(InfrastructureError):
    """Native process/container transport; model API probes cannot repair it."""
    layer = 'native_transport'


class AgentError(RuntimeError):
    """The agent ended without an operational answer after receiving input."""


class UnsupportedCapability(RuntimeError):
    """The adapter cannot perform a required native lifecycle operation."""


class RunInterrupted(RuntimeError):
    """The operator stopped an unfinished instance; it has no score."""


class OperationTimeout(TimeoutError):
    """The whole native operation exceeded its configured wall-clock budget."""


class NativeOperationTimeout(InfrastructureError):
    """An evaluator deadline observes missing completion, not an API outage."""
    layer = 'native_operation'

    def __init__(self, operation, timeout_s):
        super().__init__(f"Adapter operation {operation} exceeded {timeout_s:g}s; inspect adapter.log")
        self.failure = {'layer': self.layer, 'code': 'operation_timeout', 'attribution': 'unknown',
                        'attribution_confidence': 'unresolved', 'operation': operation,
                        'operation_id': (_observation.get() or {}).get('operation_id'),
                        'timeout_s': timeout_s, 'evidence': {'source': 'evaluator_operation_deadline'}}


def decode_reply(line, sequence):
    try:
        reply = json.loads(line)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise InfrastructureError("Adapter emitted non-JSON protocol output") from exc
    if not isinstance(reply, dict) or type(reply.get("id")) is not int or reply["id"] != sequence:
        raise InfrastructureError("Adapter reply does not correspond to the pending request")
    if "error" in reply:
        error = reply["error"]
        if "result" in reply or not isinstance(error, dict) or not isinstance(error.get("message"), str):
            raise InfrastructureError("Malformed adapter error response")
        error_type = {"unsupported": UnsupportedCapability, "agent": AgentError}.get(error.get("kind"), InfrastructureError)
        exception = error_type(error["message"])
        exception.service_role = error.get('service_role')
        if 'failure' in error:
            if not isinstance(error['failure'], dict):
                raise InfrastructureError('Malformed adapter failure details')
            exception.failure = error['failure']
            exception.layer = error['failure'].get('layer')
        for key, expected in (('failure_phase', str), ('partial_reply', dict)):
            if key in error:
                if not isinstance(error[key], expected):
                    raise InfrastructureError(f'Malformed adapter {key}')
                setattr(exception, key, error[key])
        raise exception
    if not isinstance(reply.get("result"), dict):
        raise InfrastructureError("Adapter result must be a JSON object")
    return reply["result"]


def await_reply(future, timeout_s, cancelled=None):
    deadline = time.monotonic() + timeout_s
    while True:
        if cancelled and cancelled():
            raise RunInterrupted("用户已终止当前实例")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OperationTimeout()
        try:
            return future.result(timeout=min(.25, remaining))
        except FutureTimeout:
            if future.done():
                return future.result()
            continue


def exchange_json(stdin, stdout, message):
    """The entire blocking wire operation belongs inside the cancellable wait."""
    stdin.write(json_text(message) + '\n')
    stdin.flush()
    return stdout.readline()


class JsonProcess:
    """One trusted adapter process, with a private working directory and HOME.

    This is a process lifecycle boundary, not a filesystem or network sandbox.
    Only explicitly named credential variables are inherited.
    """

    def __init__(self, argv, workspace, config, *, timeout_s=DEFAULT_OPERATION_TIMEOUT_S,
                 pass_env=(), credential_env=None, cancelled=None):
        from .persistence import write_json
        from .process_group import WindowsJob
        import psutil

        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        home = self.workspace / 'home'
        home.mkdir(exist_ok=True)
        allowed = set(pass_env)
        if credential_env:
            allowed.add(credential_env)
        env = {key: value for key, value in os.environ.items() if key.upper() in {
            'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'LANG', 'LC_ALL',
        } or key in allowed}
        env.update(ASTROMEMBENCH_WORKSPACE=str(self.workspace),
                   ASTROMEMBENCH_CONFIG=json_text(config),
                   ASTROMEMBENCH_OPERATION_TIMEOUT_S=str(timeout_s),
                   PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
                   TMP=str(self.workspace), TEMP=str(self.workspace), TMPDIR=str(self.workspace),
                   HOME=str(home), USERPROFILE=str(home))
        if credential_env and credential_env in os.environ:
            env['ASTROMEMBENCH_API_KEY'] = os.environ[credential_env]
        self.timeout_s, self.cancelled, self.sequence = timeout_s, cancelled, 0
        self.job = self.process = None
        self.closed = False
        self.stderr = (self.workspace / 'adapter.log').open('w', encoding='utf-8')
        self.reader = (ThreadPoolExecutor(max_workers=1, thread_name_prefix='adapter-jsonl')
                       if os.name == 'nt' else None)
        self.stdout_buffer = bytearray()
        try:
            if os.name == 'nt':
                self.job = WindowsJob()
                self.process = self.job.spawn(argv, cwd=self.workspace, env=env, stderr=self.stderr)
            else:
                self.process = subprocess.Popen(argv, cwd=self.workspace, env=env,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                    bufsize=0, start_new_session=True)
                os.set_blocking(self.process.stdin.fileno(), False)
                os.set_blocking(self.process.stdout.fileno(), False)
            write_json(self.workspace / 'process.json', {
                'pid': self.process.pid, 'created': psutil.Process(self.process.pid).create_time(),
                'windows_job': self.job.name if self.job else None,
                'process_group': self.process.pid if self.job is None else None,
                'closed': False,
            })
            if self.job:
                self.job.resume(self.process)
        except BaseException:
            self.close()
            raise

    def call(self, operation, payload):
        self.sequence += 1
        request = request_message(self.sequence, operation, payload)
        try:
            if self.reader is not None:
                future = self.reader.submit(exchange_json, self.process.stdin, self.process.stdout, request)
                line = await_reply(future, self.timeout_s, self.cancelled)
            else:
                line = self._exchange_posix(request)
        except OperationTimeout as exc:
            raise NativeOperationTimeout(operation, self.timeout_s) from exc
        except (BrokenPipeError, OSError, UnicodeError) as exc:
            raise NativeTransportError(f'Adapter disconnected during {operation}') from exc
        if not line:
            raise NativeTransportError(f'Adapter closed stdout during {operation}; inspect adapter.log')
        return decode_reply(line, self.sequence)

    def _exchange_posix(self, request):
        """Poll both pipes without a reader thread that could survive cancellation.

        A detached adapter child may retain stdout after the owned process group
        exits. Closing our nonblocking pipes must not wait for that child's EOF.
        """
        import selectors
        outgoing = memoryview((json_text(request) + '\n').encode('utf-8'))
        sent = 0
        stdin = self.process.stdin.fileno()
        stdout = self.process.stdout.fileno()
        deadline = time.monotonic() + self.timeout_s
        with selectors.DefaultSelector() as selector:
            selector.register(stdin, selectors.EVENT_WRITE)
            selector.register(stdout, selectors.EVENT_READ)
            while True:
                if self.cancelled and self.cancelled():
                    raise RunInterrupted('Evaluation was cancelled')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OperationTimeout()
                newline = self.stdout_buffer.find(b'\n')
                if sent == len(outgoing) and newline >= 0:
                    line = bytes(self.stdout_buffer[:newline + 1])
                    del self.stdout_buffer[:newline + 1]
                    return line.decode('utf-8')
                for key, _ in selector.select(timeout=min(.25, remaining)):
                    if key.fd == stdin:
                        try:
                            sent += os.write(stdin, outgoing[sent:sent + 65536])
                        except BlockingIOError:
                            continue
                        if sent == len(outgoing):
                            selector.unregister(stdin)
                    else:
                        try:
                            chunk = os.read(stdout, 65536)
                        except BlockingIOError:
                            continue
                        if not chunk:
                            line = bytes(self.stdout_buffer)
                            self.stdout_buffer.clear()
                            return line.decode('utf-8')
                        self.stdout_buffer.extend(chunk)

    def close(self):
        if self.closed:
            return
        from .persistence import read_json, write_json
        from .process_group import terminate_posix_group
        try:
            if self.job:
                self.job.terminate()
            elif self.process is not None:
                terminate_posix_group(self.process.pid)
            if self.process is not None:
                self.process.wait(timeout=10)
        finally:
            if self.job:
                self.job.close()
            if self.reader is not None:
                self.reader.shutdown(wait=True, cancel_futures=True)
            if self.process is not None:
                self.process.stdin.close()
                self.process.stdout.close()
                if hasattr(self.process, 'close'):
                    self.process.close()
            self.stderr.close()
        self.closed = True
        path = self.workspace / 'process.json'
        if path.exists():
            write_json(path, {**read_json(path), 'closed': True})


def recover_adapter(workspace):
    """Release only a previously recorded adapter process before explicit resume."""
    from .persistence import read_json, write_json
    from .process_group import WindowsJob, terminate_posix_group
    import psutil
    import re

    path = Path(workspace) / 'process.json'
    if not path.exists():
        return
    identity = read_json(path)
    if identity.get('closed'):
        return
    if os.name == 'nt':
        name = identity.get('windows_job')
        if not isinstance(name, str) or not re.fullmatch(r'Local\\AstroMemBench-[a-f0-9]{32}', name):
            raise ValueError('Unrecognized adapter Job identity; cannot safely resume')
        job = WindowsJob(name, existing=True)
        try:
            job.terminate()
        finally:
            job.close()
    else:
        pid = identity.get('pid')
        if type(pid) is not int or pid != identity.get('process_group') or pid <= 1:
            raise ValueError('Unrecognized adapter process group; cannot safely resume')
        try:
            process = psutil.Process(pid)
            if abs(process.create_time() - identity['created']) > .01:
                raise ValueError('Adapter PID has been reused; refusing to signal it')
        except psutil.NoSuchProcess:
            pass
        terminate_posix_group(pid)
    write_json(path, {**identity, 'closed': True, 'recovered': True})
