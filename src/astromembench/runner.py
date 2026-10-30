"""Read prescribed history inputs, apply the native session boundary, then test."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import time

from . import __version__, PROTOCOL_VERSION
from .environment import Environment
from .history import HistoryFailure, HistoryLedger
from .payloads import attach_images, check_packet
from .protocol import AgentError, DOMAIN_PROMPT, InfrastructureError, UnsupportedCapability, RunInterrupted
from .protocol import observe_operation
from .timing import StageClock
from .usage import STAGES, UsageLedger
from .schema import MODES, Task, json_text
from .persistence import write_json


def run_task(task: Task, participant, mode: str, *, asset_root: Path, output: Path | None = None,
             instructions: str = DOMAIN_PROMPT, cancelled=None, finalize_result=None, timing=None) -> dict:
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")
    timing = timing or StageClock(mode, path=output / 'timing-events.jsonl' if output else None)
    if timing.active is None:
        timing.start('setup')
    env, ledger = Environment(task), HistoryLedger(task)
    started = time.monotonic()
    events, warnings, operation_errors = [], [], []
    phase, status, error, outcome = "history", "completed", None, None
    error_layer = None
    failure = None
    service_role = None
    context = {'observed': False, 'operations': {key: 0 for key in STAGES}, 'events': [],
               'coverage': {key: {'calls': 0, 'observed_calls': 0, 'unresolved_interval': False} for key in STAGES},
               'unattributed_operations': 0}
    completed_operations = {stage: 0 for stage in STAGES}
    usage = UsageLedger()
    native_counts = {}
    pending_counter_stages = set()
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
    trace = (output / "events.jsonl").open("w", encoding="utf-8") if output else None

    def progress(operation, waiting):
        if output:
            value = {"operation": operation, "phase": phase, "waiting": waiting,
                     "history_processed": ledger.index, "history_total": len(task.history),
                     "action_steps": env.steps, "action_limit": task.public["max_steps"],
                     "stage": timing.active, "timing": timing.snapshot(),
                     "completed_operations": dict(completed_operations),
                     "elapsed_s": time.monotonic() - started,
                     "updated_utc": datetime.now(timezone.utc).isoformat(),
                     "state": None if phase == "history" else env.public_state()}
            write_json(output / "runtime.json", value)

    def call(operation: str, payload: dict) -> dict:
        if cancelled and cancelled():
            raise RunInterrupted("用户已终止当前实例")
        # Source references stay in the evaluator trace, never in the wire text.
        observation = {**timing.begin_operation(operation, len(events) + 1),
                       'history_round': ledger.index+1 if operation == 'history' else None}
        entry = {"operation": operation, **observation, "input": deepcopy(payload)}
        events.append(entry)
        if trace:
            trace.write(json_text({"event": "request", **entry, "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")
            trace.flush()
        progress(operation, True)
        if operation != 'reset':
            context['coverage'][timing.active]['calls'] += 1
            pending_counter_stages.add(timing.active)
        try:
            wire = attach_images(payload, asset_root)
            check_packet(wire)
            with observe_operation(observation):
                reply = participant.call(operation, wire)
            if not isinstance(reply, dict):
                raise InfrastructureError("Adapter result must be an object")
        except (InfrastructureError, AgentError, UnsupportedCapability, RunInterrupted, OSError) as exc:
            detail = {'kind': ('agent' if isinstance(exc, AgentError) else 'unsupported' if isinstance(exc, UnsupportedCapability)
                               else 'interrupted' if isinstance(exc, RunInterrupted) else 'infrastructure'),
                      'message': str(exc)}
            for key in ('service_role', 'failure', 'failure_phase', 'partial_reply'):
                if (value := getattr(exc, key, None)) is not None:
                    detail[key] = deepcopy(value)
            entry['error'] = detail
            # Keep full text and tool arguments in the event trace only. The
            # result/row carries the completion state, never a substitute reply.
            summary = {key: deepcopy(value) for key, value in detail.items() if key != 'partial_reply'}
            if 'partial_reply' in detail:
                summary['partial_reply'] = {key: deepcopy(detail['partial_reply'][key]) for key in (
                    'processed', 'model_turn_completed', 'action_attempted', 'action_submitted', 'action_executed')
                    if key in detail['partial_reply']}
            operation_errors.append({'operation': operation, **observation, **summary})
            timing.end_operation(observation, status=detail['kind'], failure={key: deepcopy(value) for key, value in
                detail.items() if key in ('failure', 'failure_phase', 'service_role')})
            if trace:
                trace.write(json_text({'event': 'error', 'operation': operation, **observation, 'error': detail,
                                       'timestamp': datetime.now(timezone.utc).isoformat()}) + '\n')
                trace.flush()
            progress(operation, False)
            raise
        timing.end_operation(observation)
        completed_operations[timing.active] += 1
        usage_warning = usage.observe(reply, timing.active)
        if usage_warning and not any(item.get('error') == usage_warning for item in warnings):
            warnings.append({'operation': operation, 'error': usage_warning})
        entry["reply"] = deepcopy(reply)
        count = reply.get('native_compactions')
        if type(count) is int and count >= 0:
            session = reply.get('conversation_id')
            context.update(observed=True, mechanism=reply.get('context_management'),
                           context_window=reply.get('context_window'),
                           native_token_window_configured=reply.get('native_token_window_configured', True))
            increment = max(0, count - native_counts.get(session, 0))
            coverage = context['coverage'][timing.active]
            if operation != 'reset':
                coverage['observed_calls'] += 1
            attributed = len(pending_counter_stages) <= 1
            if attributed:
                context['operations'][timing.active] += increment
            else:
                context['unattributed_operations'] += increment
                for stage in pending_counter_stages:
                    context['coverage'][stage]['unresolved_interval'] = True
            if increment:
                context['events'].append({**observation, 'stage': timing.active if attributed else 'unknown', 'conversation_id': session,
                                          'mechanism': reply.get('context_management'), 'count': increment,
                                          'trigger_tokens': None, 'trigger_token_source': 'unavailable',
                                          'source': 'native_receipt_counter'})
            native_counts[session] = count
            pending_counter_stages.clear()
        if trace:
            trace.write(json_text({"event": "reply", "operation": operation, **observation, "reply": reply,
                                   "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")
            trace.flush()
        progress(operation, False)
        return reply

    def best_effort(operation, payload):
        # A physically terminal outcome remains valid even if final processing
        # or native cleanup fails. Never purchase another scored attempt for it.
        try:
            return call(operation, payload)
        except (InfrastructureError, AgentError, UnsupportedCapability, RunInterrupted, OSError) as exc:
            warnings.append({"operation": operation, "error": str(exc),
                             **({'failure': deepcopy(exc.failure)} if getattr(exc, 'failure', None) else {})})
            return None

    def begin_finalization(*, complete=False, scored=False):
        if timing.active != 'finalization':
            timing.transition('finalization', complete=complete, terminal_phase=phase if scored else None)

    def save_result(*, finalization_complete):
        result = {
            "benchmark_version": __version__, "protocol": PROTOCOL_VERSION, "case_id": task.case_id,
            "template": task.template, "difficulty": task.difficulty, "mode": mode,
            "status": status, "phase": phase, "history_steps": ledger.index,
            "elapsed_s": time.monotonic() - started, "error": error, "error_layer": error_layer,
            "failure": deepcopy(failure),
            "service_role": service_role, "context_management": deepcopy(context), "warnings": deepcopy(warnings),
            "operation_errors": deepcopy(operation_errors),
            "timing": timing.snapshot(),
            "usage": usage.snapshot(),
            "outcome": deepcopy(outcome), "history_acknowledgments": deepcopy(ledger.acknowledgments),
            "lifecycle": [deepcopy(event) for event in events if event["operation"] in {"reset", "new_session", "end"}],
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "finalization_complete": finalization_complete,
        }
        if finalize_result:
            result = finalize_result(result)
        if output:
            write_json(output / 'result.json', result)
        return result

    try:
        if call("reset", {}).get("cleared") is not True:
            raise InfrastructureError("Adapter did not confirm clearing the test subject")
        before = call("new_session", {"instructions": instructions})
        if not before.get("conversation_id"):
            raise InfrastructureError("Conversation identity was not reported")
        timing.transition('history', complete=True)
        for _ in task.history:
            payload = ledger.begin()
            reply = call("history", payload)
            ledger.finish(processed=reply.get("processed") is True,
                          assistant_text=reply.get("assistant_text"),
                          action_attempted=reply.get("action_attempted") or reply.get("action") is not None)
            progress("history", False)
        ledger.check_boundary(task)
        if mode == "new_session":
            phase = "session_boundary"
            timing.transition('session_boundary', complete=True)
            after = call("new_session", {"instructions": instructions})
            if not after.get("conversation_id") or after["conversation_id"] == before["conversation_id"]:
                raise InfrastructureError("new_session did not create a different conversation")
        phase = "current"
        timing.transition('current', complete=True)
        while not env.done:
            try:
                reply = call("observe", env.observation())
            except AgentError as exc:
                if getattr(exc, 'failure_phase', None) in {'memory_capture', 'memory_recall', 'memory_finish_history'}:
                    # Failed memory maintenance is not a missing robot_action.
                    # End this subject failure without spending format attempts.
                    raise
                warnings.append({"operation": "observe", "model_error": str(exc)})
                reply = {}
            env.step(reply.get("action") if reply.get("action_submitted") is True else None)
            if env.done:
                begin_finalization(complete=True, scored=True)
                outcome = env.result()
                # Commit the physical decision before progress, feedback, learning
                # or transport teardown can fail or the process can be killed.
                save_result(finalization_complete=False)
            progress("observe", False)
        outcome = env.result()
        best_effort("feedback", {"stage": "current", "terminal": True, "observation": env.observation()})
        best_effort("end", {})
    except HistoryFailure as exc:
        error = str(exc)
        env.end("agent_failure", score=0.0, full_credit=False)
        outcome = {**env.result(), "phase": "history", "failure": "native_processing_incomplete"}
        begin_finalization(scored=True)
        save_result(finalization_complete=False)
        best_effort("end", {})
    except RunInterrupted as exc:
        if outcome is None:
            status, error = "interrupted", str(exc)
        else:
            warnings.append({'operation': 'finalization', 'error': str(exc)})
    except UnsupportedCapability as exc:
        status, error = "unsupported", str(exc)
        failure = getattr(exc, 'failure', None)
        error_layer = getattr(exc, 'layer', None) or (failure or {}).get('layer')
        service_role = getattr(exc, 'service_role', None)
    except (InfrastructureError, OSError) as exc:
        if outcome is None:
            status, error = "infrastructure_error", str(exc)
            error_layer = getattr(exc, 'layer', None)
            failure = getattr(exc, 'failure', None)
            service_role = getattr(exc, 'service_role', None)
        else:
            warnings.append({'operation': 'finalization', 'error': str(exc)})
    except AgentError as exc:
        error = str(exc)
        env.end("agent_failure")
        outcome = env.result()
        begin_finalization(complete=phase == 'current', scored=True)
        save_result(finalization_complete=False)
        best_effort("end", {})
    finally:
        begin_finalization()
        try:
            participant.close()
        except Exception as exc:
            warnings.append({"operation": "close", "error": str(exc)})
            if outcome is None:
                status = "infrastructure_error"
                error = (error + "; " if error else "") + f"Native cleanup failed: {exc}"
        finally:
            if trace:
                trace.close()
    timing.finish(complete=True)
    return save_result(finalization_complete=True)
