"""Own the complete stdio process family, including children outliving its root.

Windows creates the adapter inside a named Job with KILL_ON_JOB_CLOSE, atomically,
then resumes it after durable identity recording. POSIX adapters
already start in their own session; their process group is the cleanup boundary.
"""
import ctypes
from ctypes import wintypes as w
import os
import subprocess
import time
from uuid import uuid4


class _Limits(ctypes.Structure):
    _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', w.DWORD),
                ('min_working_set', ctypes.c_size_t), ('max_working_set', ctypes.c_size_t),
                ('active_limit', w.DWORD), ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]


class _IO(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class _Extended(ctypes.Structure):
    _fields_ = [('basic', _Limits), ('io', _IO), ('process_memory', ctypes.c_size_t), ('job_memory', ctypes.c_size_t),
                ('peak_process_memory', ctypes.c_size_t), ('peak_job_memory', ctypes.c_size_t)]


class _Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, w.DWORD) for name in ('page_faults', 'total', 'active', 'terminated')]


class _Startup(ctypes.Structure):
    _fields_ = [('size', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR), ('title', w.LPWSTR)] + [
        (name, w.DWORD) for name in ('x', 'y', 'width', 'height', 'columns', 'rows', 'fill', 'flags')] + [
        ('show', w.WORD), ('reserved_size', w.WORD), ('reserved_bytes', ctypes.c_void_p),
        ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]


class _StartupEx(ctypes.Structure):
    _fields_ = [('startup', _Startup), ('attributes', ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [('process', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]


def _api():
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateJobObjectW': ([ctypes.c_void_p, w.LPCWSTR], w.HANDLE),
        'OpenJobObjectW': ([w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE),
        'SetInformationJobObject': ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD], w.BOOL),
        'QueryInformationJobObject': ([w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p], w.BOOL),
        'TerminateJobObject': ([w.HANDLE, w.UINT], w.BOOL),
        'CloseHandle': ([w.HANDLE], w.BOOL),
        'ResumeThread': ([w.HANDLE], w.DWORD),
        'InitializeProcThreadAttributeList': ([ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t)], w.BOOL),
        'UpdateProcThreadAttribute': ([ctypes.c_void_p, w.DWORD, ctypes.c_size_t, ctypes.c_void_p,
                                      ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p], w.BOOL),
        'DeleteProcThreadAttributeList': ([ctypes.c_void_p], None),
        'CreateProcessW': ([w.LPCWSTR, w.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, w.BOOL, w.DWORD,
                           ctypes.c_void_p, w.LPCWSTR, ctypes.POINTER(_StartupEx), ctypes.POINTER(_ProcessInfo)], w.BOOL),
        'WaitForSingleObject': ([w.HANDLE, w.DWORD], w.DWORD),
        'GetExitCodeProcess': ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        'TerminateProcess': ([w.HANDLE, w.UINT], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        getattr(api, name).argtypes, getattr(api, name).restype = args, result
    return api


def _check(result):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return result


class WindowsJob:
    def __init__(self, name=None, *, existing=False):
        self.api = _api()
        self.name = name or 'Local\\AstroMemBench-' + uuid4().hex
        if existing:
            self.handle = self.api.OpenJobObjectW(0x0004 | 0x0008, False, self.name)  # QUERY | TERMINATE
            if not self.handle and ctypes.get_last_error() == 2:
                return  # Last handle closed: KILL_ON_JOB_CLOSE has terminated the family.
            _check(self.handle)
        else:
            self.handle = _check(self.api.CreateJobObjectW(None, self.name))
            limits = _Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway flags.
            try:
                _check(self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            except BaseException:
                self.close()
                raise

    def spawn(self, argv, *, cwd, env, stderr):
        return _WindowsProcess(self, argv, cwd=cwd, env=env, stderr=stderr)

    def resume(self, process):
        if self.api.ResumeThread(process._thread) == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        _check(self.api.CloseHandle(process._thread))
        process._thread = None

    def terminate(self):
        if not self.handle:
            return
        _check(self.api.TerminateJobObject(self.handle, 1))
        deadline = time.monotonic() + 10
        while True:
            state = _Accounting()
            _check(self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(state), ctypes.sizeof(state), None))
            if state.active == 0:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError('Native process family has not exited')
            time.sleep(.02)

    def close(self):
        if self.handle:
            _check(self.api.CloseHandle(self.handle))
            self.handle = None


class _WindowsProcess:
    """The small Popen surface used by JSONL, with atomic Job assignment.

    PROC_THREAD_ATTRIBUTE_JOB_LIST removes the create/assign crash window:
    https://devblogs.microsoft.com/oldnewthing/20230209-00/?p=107812
    The child inherits only its three explicitly listed standard handles.
    """
    def __init__(self, job, argv, *, cwd, env, stderr):
        import msvcrt
        from contextlib import ExitStack
        self.api, self.args, self.returncode = job.api, argv, None
        self._handle = self._thread = None
        with ExitStack() as streams:
            streams.callback(self._close_handles)
            with ExitStack() as cleanup:
                child_in, parent_in = os.pipe()
                cleanup.callback(os.close, child_in)
                self.stdin = os.fdopen(parent_in, 'w', buffering=1, encoding='utf-8')
                streams.callback(self.stdin.close)
                parent_out, child_out = os.pipe()
                cleanup.callback(os.close, child_out)
                self.stdout = os.fdopen(parent_out, 'r', encoding='utf-8')
                streams.callback(self.stdout.close)
                handles = (w.HANDLE * 3)(msvcrt.get_osfhandle(child_in), msvcrt.get_osfhandle(child_out),
                                         msvcrt.get_osfhandle(stderr.fileno()))
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                    cleanup.callback(os.set_handle_inheritable, handle, False)
                size = ctypes.c_size_t()
                self.api.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
                attributes = ctypes.create_string_buffer(size.value)
                _check(self.api.InitializeProcThreadAttributeList(attributes, 2, 0, ctypes.byref(size)))
                cleanup.callback(self.api.DeleteProcThreadAttributeList, attributes)
                jobs = (w.HANDLE * 1)(job.handle)
                for key, value in ((0x00020002, handles), (0x0002000D, jobs)):
                    _check(self.api.UpdateProcThreadAttribute(attributes, 0, key, value, ctypes.sizeof(value), None, None))
                startup = _StartupEx()
                startup.startup.size = ctypes.sizeof(startup)
                startup.startup.flags = 0x100  # STARTF_USESTDHANDLES
                startup.startup.stdin, startup.startup.stdout, startup.startup.stderr = handles
                startup.attributes = ctypes.cast(attributes, ctypes.c_void_p)
                process = _ProcessInfo()
                command = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
                environment = ctypes.create_unicode_buffer('\0'.join(f'{k}={v}' for k, v in sorted(env.items())) + '\0\0')
                flags = 0x08000000 | 0x00000004 | 0x00000400 | 0x00080000
                _check(self.api.CreateProcessW(None, command, None, None, True, flags, environment, str(cwd),
                                              ctypes.byref(startup), ctypes.byref(process)))
                self._handle, self._thread, self.pid = process.process, process.thread, process.pid
            streams.pop_all()

    def poll(self):
        if self.returncode is None:
            status = self.api.WaitForSingleObject(self._handle, 0)
            if status == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
            if status == 0:
                code = w.DWORD()
                _check(self.api.GetExitCodeProcess(self._handle, ctypes.byref(code)))
                self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        if self.returncode is not None:
            return self.returncode
        status = self.api.WaitForSingleObject(self._handle, 0xFFFFFFFF if timeout is None else max(0, int(timeout * 1000)))
        if status == 0x102:
            raise subprocess.TimeoutExpired(self.args, timeout)
        if status == 0xFFFFFFFF:
            raise ctypes.WinError(ctypes.get_last_error())
        return self.poll()

    def kill(self):
        if self.poll() is None:
            _check(self.api.TerminateProcess(self._handle, 1))

    def _close_handles(self):
        for name in ('_thread', '_handle'):
            if handle := getattr(self, name):
                _check(self.api.CloseHandle(handle))
                setattr(self, name, None)
    def close(self):
        self._close_handles()
        self.stdin.close()
        self.stdout.close()


def terminate_posix_group(group):
    import signal
    import psutil
    try:
        os.killpg(group, signal.SIGKILL)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 10
    while True:
        alive = []
        for process in psutil.process_iter(['pid', 'status']):
            try:
                if os.getpgid(process.pid) == group and process.info['status'] != psutil.STATUS_ZOMBIE:
                    alive.append(process.pid)
            except (ProcessLookupError, psutil.NoSuchProcess):
                pass
        if not alive:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError('Native POSIX process group has not exited')
        time.sleep(.02)
