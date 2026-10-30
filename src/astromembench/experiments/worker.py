"""Detached experiment worker. No imports from the HTTP or UI layer."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import argparse
import os
from pathlib import Path
from threading import Event, Thread
import time

import psutil

from ..catalog import PreparedBank
from ..evaluation import run_evaluation, _run_lock, _runtime_identity, utcnow
from ..persistence import read_json
from .store import Store


def run(workspace, experiment_id, epoch):
    store = Store(workspace)
    directory = store.root / 'experiments' / experiment_id
    directory.mkdir(parents=True, exist_ok=True)
    with _run_lock(directory):
        record = store.get(experiment_id)
        if record['epoch'] != epoch:
            return
        definition = record['definition']
        stopped, paused, done = Event(), Event(), Event()
        monitor_errors = []

        def monitor():
            last_heartbeat = 0
            try:
                while not done.is_set():
                    state = store.state(experiment_id)
                    if state['epoch'] != epoch:
                        stopped.set()
                        return
                    if state['desired'] != 'run':
                        paused.set()
                    if state['desired'] == 'stop':
                        stopped.set()
                    if time.monotonic() - last_heartbeat > 2:
                        with store.connect(write=True) as db:
                            db.execute('UPDATE experiments SET heartbeat=? WHERE id=? AND epoch=?', (utcnow(), experiment_id, epoch))
                        last_heartbeat = time.monotonic()
                    done.wait(.15)
            except BaseException as exc:
                monitor_errors.append(exc)
                stopped.set()

        if not store.claim_worker(experiment_id, epoch, os.getpid(), psutil.Process().create_time()):
            return
        watcher = Thread(target=monitor, name='experiment-control', daemon=True)
        watcher.start()
        error = None
        try:
            if definition['runtime_identity'] != _runtime_identity():
                raise ValueError('Evaluator identity changed after the experiment was saved')
            bank = PreparedBank(definition['data'], store.root / 'cache')
            if bank.identity != definition['data_identity']:
                raise ValueError('Dataset identity changed after the experiment was saved')
            units = iter((group, repetition) for group in definition['groups'] for repetition in range(1, group['repetitions'] + 1))

            def evaluate(group, repetition):
                output = directory / 'groups' / group['id'] / f'{repetition:04d}'

                def progress(event):
                    if event['event'] == 'run_started':
                        with store.connect() as db:
                            projected = {row['case_id']: dict(row) for row in db.execute('''SELECT case_id,status,score,attempt
                                FROM results WHERE experiment_id=? AND group_id=? AND repetition=?''', (experiment_id,group['id'],repetition))}
                        for row in event['summary']['cases']:
                            if row.get('result_path'):
                                saved = projected.get(row['case_id'], {})
                                if (saved.get('score') is not None or saved.get('status') == 'unsupported'
                                        or (saved.get('status') == row['status'] and saved.get('attempt') == row['attempt'])):
                                    continue
                                path = output / row['result_path']
                                store.record(experiment_id, group['id'], repetition, row['case_id'], result=read_json(path),
                                             attempt=row['attempt'], result_path=path.relative_to(directory).as_posix())
                    elif event['event'] in {'case_started', 'case_finished'}:
                        path = output / event['result_path']
                        store.record(experiment_id, group['id'], repetition, event['case_id'], result=event.get('result'),
                                     attempt=event['attempt'], result_path=path.relative_to(directory).as_posix())

                if stopped.is_set() or paused.is_set():
                    return
                return run_evaluation(data=bank.data, output=output, adapter=group['adapter'], case_ids=group['case_ids'],
                                      mode=group['mode'], resume=(output / 'run.json').exists(),
                                      cancelled=stopped.is_set, pause_requested=paused.is_set,
                                      progress=progress, prepared_bank=bank)

            with ThreadPoolExecutor(max_workers=definition['concurrency'], thread_name_prefix='evaluation') as pool:
                pending = set()
                exhausted = False
                while pending or not exhausted:
                    while len(pending) < definition['concurrency'] and not exhausted and not paused.is_set() and not stopped.is_set():
                        unit = next(units, None)
                        if unit is None:
                            exhausted = True
                            break
                        pending.add(pool.submit(evaluate, *unit))
                    if not pending:
                        break
                    finished, pending = wait(pending, timeout=.2, return_when=FIRST_COMPLETED)
                    for future in finished:
                        try:
                            future.result()
                        except BaseException:
                            stopped.set()
                            raise
            if monitor_errors:
                raise RuntimeError(f'Worker control failed: {monitor_errors[0]}')
        except BaseException as exc:
            stopped.set()
            error = f'{type(exc).__name__}: {exc}'
        finally:
            done.set()
            watcher.join(timeout=3)
    # Publish a resumable state only after relinquishing the process lock.
    store.finish_worker(experiment_id, epoch, error=error)


def main():
    parser = argparse.ArgumentParser(description='Internal detached experiment worker')
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--epoch', required=True)
    args = parser.parse_args()
    if (len(args.experiment) != 32 or any(c not in '0123456789abcdef' for c in args.experiment)
            or len(args.epoch) != 32 or any(c not in '0123456789abcdef' for c in args.epoch)):
        parser.error('Invalid worker identity')
    run(args.workspace, args.experiment, args.epoch)


if __name__ == '__main__':
    main()
