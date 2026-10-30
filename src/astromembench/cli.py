"""Command-line access to the released fixed benchmark and adapter protocol."""
import argparse
import json
from pathlib import Path
import sys

from . import __version__


def _print(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='astromembench', description='Evaluate a memory-enabled agent against the fixed AstroMemBench dataset.')
    parser.add_argument('--version', action='version', version=__version__)
    commands = parser.add_subparsers(dest='command', required=True)
    validate = commands.add_parser('validate', help='Verify the fixed dataset and image checksums')
    listing = commands.add_parser('list', help='List available cases without running an adapter')
    run = commands.add_parser('run', help='Run selected cases through a user adapter, serially')
    web = commands.add_parser('webui', help='Open the local benchmark interface')
    for command in (validate, listing, run, web):
        command.add_argument('--data', type=Path, default=Path('data/benchmark'), help='Extracted benchmark dataset directory')
    listing.add_argument('--template', action='append', help='Limit to a template; repeat to select several')
    listing.add_argument('--limit', type=int, default=20)
    run.add_argument('--adapter', type=Path, required=True, help='Adapter JSON configuration')
    run.add_argument('--output', type=Path, required=True, help='New output directory, or saved run with --resume')
    run.add_argument('--case', action='append', dest='case_ids', help='Case ID; repeat to select several. Omit for the whole bank.')
    run.add_argument('--mode', choices=('same_session', 'new_session'), default='same_session')
    run.add_argument('--resume', action='store_true', help='Reuse terminal results; retry only unscored failed/interrupted cases')
    summary = commands.add_parser('summarize', help='Rebuild a summary from saved results without model calls')
    summary.add_argument('output', type=Path)
    web.add_argument('--host', default='127.0.0.1')
    web.add_argument('--port', type=int, default=8765)
    web.add_argument('--workspace', type=Path, default=Path('runs/workbench'), help='Persistent experiments and saved adapters')
    web.add_argument('--open', action=argparse.BooleanOptionalAction, default=True,
                     help='Open the browser automatically (default: enabled)')
    adapters = commands.add_parser('adapters', help='Manage user-owned adapter configurations')
    adapters.add_argument('--workspace', type=Path, default=Path('runs/workbench'))
    adapter_actions = adapters.add_subparsers(dest='action', required=True)
    adapter_actions.add_parser('list')
    importing = adapter_actions.add_parser('import')
    importing.add_argument('path', type=Path)
    importing.add_argument('--parallel-safe', action='store_true', help='Confirm each process isolates its external session and memory')
    checking = adapter_actions.add_parser('check')
    checking.add_argument('id')
    experiment = commands.add_parser('experiment', help='Design and control durable experiments without a browser')
    experiment.add_argument('--workspace', type=Path, default=Path('runs/workbench'))
    actions = experiment.add_subparsers(dest='action', required=True)
    creating = actions.add_parser('create')
    creating.add_argument('spec', type=Path, help='Experiment JSON with saved adapter IDs')
    creating.add_argument('--data', type=Path, default=Path('data/benchmark'))
    actions.add_parser('list')
    opening = actions.add_parser('import')
    opening.add_argument('path', type=Path)
    opening.add_argument('--data', type=Path, default=Path('data/benchmark'))
    for name in ('show', 'start', 'pause', 'stop', 'results', 'export'):
        action = actions.add_parser(name)
        action.add_argument('id')
        if name == 'results':
            action.add_argument('--offset', type=int, default=0)
            action.add_argument('--limit', type=int, default=50)
        if name == 'export':
            action.add_argument('--format', choices=('json', 'csv'), default='json')
            action.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate':
            from .benchmark import validate_bank
            _print(validate_bank(args.data))
        elif args.command == 'list':
            from .benchmark import load_index
            from .metadata import TEMPLATE_SPECS
            if args.limit < 1:
                raise ValueError('--limit must be at least 1')
            unknown = set(args.template or ()) - set(TEMPLATE_SPECS)
            if unknown:
                raise ValueError('Unknown template(s): ' + ', '.join(sorted(unknown)))
            index = load_index(args.data)
            rows = []
            for case in index['cases']:
                if args.template and case['template'] not in args.template:
                    continue
                rows.append({**case, 'history_rounds': index.get('history_rounds', 30)})
                if len(rows) >= args.limit:
                    break
            _print(rows)
        elif args.command == 'run':
            from .evaluation import load_adapter, run_evaluation
            def progress(event):
                if event['event'] == 'case_started':
                    print(f"Running {event['case_id']} ({event['completed']}/{event['total']} finished)", file=sys.stderr, flush=True)
            result = run_evaluation(data=args.data, output=args.output, adapter=load_adapter(args.adapter),
                                    case_ids=args.case_ids, mode=args.mode,
                                    resume=args.resume, progress=progress)
            _print({key: value for key, value in result.items() if key != 'cases'})
            return 0 if result['status'] == 'completed' else 1
        elif args.command == 'summarize':
            from .evaluation import summarize
            _print({key: value for key, value in summarize(args.output).items() if key != 'cases'})
        elif args.command == 'webui':
            from .webui import serve
            serve(args.data, host=args.host, port=args.port, open_browser=args.open, workspace=args.workspace)
        elif args.command in {'adapters', 'experiment'}:
            from .experiments import ExperimentService
            service = ExperimentService(args.workspace, getattr(args, 'data', None))
            if args.command == 'adapters':
                if args.action == 'list':
                    _print(service.store.adapters())
                elif args.action == 'import':
                    _print(service.import_adapter(args.path, parallel_safe=args.parallel_safe))
                else:
                    _print(service.check_adapter(args.id))
            elif args.action == 'create':
                _print(service.save(json.loads(args.spec.read_text(encoding='utf-8'))))
            elif args.action == 'import':
                _print(service.import_run(args.path))
            elif args.action == 'list':
                service.reconcile(force=True)
                _print(service.store.list())
            elif args.action == 'show':
                _print(service.detail(args.id))
                _print(service.snapshot(args.id))
            elif args.action == 'start':
                _print(service.start(args.id))
            elif args.action in {'pause', 'stop'}:
                _print(service.control(args.id, args.action))
            elif args.action == 'results':
                _print(service.store.results(args.id, offset=args.offset, limit=args.limit))
            elif args.action == 'export':
                content, _ = service.export(args.id, args.format)
                with args.output.open('xb') as stream:
                    stream.write(content)
                _print({'output': str(args.output.resolve())})
    except KeyboardInterrupt:
        print('Stopped. Saved terminal results are preserved; use --resume to continue.', file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2
    return 0
