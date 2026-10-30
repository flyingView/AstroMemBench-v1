"""Thin loopback HTTP boundary; independent workers own experiments."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import gzip
from pathlib import Path
from secrets import compare_digest, token_urlsafe
from urllib.parse import parse_qs, unquote, urlsplit
import webbrowser

from ..catalog import select_cases
from ..experiments import ExperimentService

STATIC = Path(__file__).with_name('static')
MAX_BODY = 2 * 1024 * 1024
TEAM = 'Research Group on Intelligent Technologies for Spacecraft, Zhejiang University'


class Application:
    def __init__(self, data, workspace=None):
        self.token = token_urlsafe(32)
        self.service = ExperimentService(workspace or Path.cwd() / 'runs' / 'workbench')
        self.data = Path(data).expanduser().resolve()
        self.bank_error = None
        try:
            self.service.set_data(self.data)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.bank_error = str(exc)

    def bootstrap(self):
        return {'csrf': self.token, 'instance': self.service.instance, 'version': '1.0.0', 'author': 'you wu', 'team': TEAM,
                'workspace': str(self.service.root), 'data': str(self.data), 'bank_error': self.bank_error,
                'bank': self.service.catalog.describe() if self.service.catalog else None,
                'adapters': self.service.store.adapters()}

    def load_bank(self, value):
        if not isinstance(value, str) or not value.strip() or '\x00' in value:
            raise ValueError('Enter the extracted benchmark directory')
        bank = self.service.set_data(value)
        self.data = self.service.catalog.data
        self.bank_error = None
        return bank


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, application):
        if address[0] != '127.0.0.1':
            raise ValueError('The local interface must bind to 127.0.0.1')
        self.application = application
        super().__init__(address, Handler)
        port = self.server_address[1]
        self.hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}


class Handler(BaseHTTPRequestHandler):
    server: LocalServer

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        pass

    def _send(self, status, value, kind='application/json; charset=utf-8', *, filename=None):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8') if isinstance(value, (dict, list)) else value
        compressed = len(body) > 1024 and 'gzip' in self.headers.get('Accept-Encoding', '') and not kind.startswith('image/')
        if compressed:
            body = gzip.compress(body, compresslevel=4, mtime=0)
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Vary', 'Accept-Encoding')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'; object-src 'none'")
        if filename:
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _allowed(self, mutation=False):
        host, origin = self.headers.get('Host'), self.headers.get('Origin')
        if host not in self.server.hosts or (origin is not None and origin != f'http://{host}'):
            self._send(403, {'error': 'This interface accepts same-origin local requests only'})
            return False
        if self.headers.get('Sec-Fetch-Site') in {'cross-site', 'same-site'}:
            self._send(403, {'error': 'Open the interface directly on this computer'})
            return False
        if mutation and (origin != f'http://{host}' or not compare_digest(
                self.headers.get('X-CSRF-Token', ''), self.server.application.token)):
            self._send(403, {'error': 'Refresh the local interface before submitting this request'})
            return False
        return True

    def _route(self):
        url = urlsplit(self.path)
        parts = [unquote(part) for part in url.path.strip('/').split('/') if part]
        query = {key: values[-1] for key, values in parse_qs(url.query).items()}
        for key in ('offset', 'limit', 'round', 'repetition', 'attempt', 'cursor'):
            if key in query:
                query[key] = int(query[key])
        return parts, query

    def _error(self, exc):
        if isinstance(exc, RuntimeError):
            return self._send(409, {'error': str(exc)})
        if isinstance(exc, (OSError, ValueError, TypeError, KeyError)):
            return self._send(400, {'error': str(exc)})
        return self._send(500, {'error': f'{type(exc).__name__}: {exc}'})

    def do_GET(self):
        if not self._allowed():
            return
        try:
            parts, q = self._route()
            app, service = self.server.application, self.server.application.service
            if parts == ['api', 'bootstrap']:
                return self._send(200, app.bootstrap())
            if parts == ['api', 'catalog']:
                return self._send(200, service._catalog().query(**q))
            if parts == ['api', 'task']:
                return self._send(200, service._catalog().preview(q['case_id'], q.get('round')))
            if parts == ['api', 'asset']:
                path = service._catalog().asset(q['path'])
                return self._send(200, path.read_bytes(), 'image/png' if path.suffix == '.png' else 'image/jpeg')
            if parts == ['api', 'experiments']:
                service.reconcile()
                return self._send(200, service.store.list(**q))
            if parts == ['api', 'compare']:
                return self._send(200, service.compare(**q))
            if parts == ['api', 'adapters']:
                return self._send(200, {'items': service.store.adapters()})
            if len(parts) == 3 and parts[:2] == ['api', 'adapters']:
                return self._send(200, service.adapter(parts[2]))
            if len(parts) in {3, 4} and parts[:2] == ['api', 'experiments']:
                identifier = parts[2]
                service.directory(identifier)
                action = parts[3] if len(parts) == 4 else 'detail'
                if action == 'detail':
                    return self._send(200, service.detail(identifier))
                if action == 'state':
                    return self._send(200, service.snapshot(identifier, q.get('since')))
                if action == 'results':
                    return self._send(200, service.store.results(identifier, **q))
                if action == 'statistics':
                    return self._send(200, service.store.statistics(identifier, **q))
                if action == 'measurements':
                    return self._send(200, service.store.measurements(identifier, **q))
                if action in {'result', 'events'}:
                    method = service.result_detail if action == 'result' else service.events
                    return self._send(200, method(identifier, **q))
                if action == 'export':
                    format = q.get('format', 'json')
                    content, kind = service.export(identifier, format)
                    return self._send(200, content, kind, filename=f'astromembench-{identifier[:8]}.{format}')
            allowed = {'/': ('index.html', 'text/html; charset=utf-8'),
                       '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                       '/style.css': ('style.css', 'text/css; charset=utf-8')}
            path = urlsplit(self.path).path
            if path in allowed:
                name, kind = allowed[path]
                return self._send(200, (STATIC / name).read_bytes(), kind)
            return self._send(404, {'error': 'Page not found'})
        except Exception as exc:
            self._error(exc)

    def do_POST(self):
        if not self._allowed(mutation=True):
            return
        if self.headers.get_content_type() != 'application/json':
            return self._send(415, {'error': 'A JSON request is required'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
                return self._send(413, {'error': 'The request is too large or has no declared length'})
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError('The request must be a JSON object')
            parts, _ = self._route()
            app, service = self.server.application, self.server.application.service
            if parts == ['api', 'bank']:
                return self._send(200, app.load_bank(value.get('data')))
            if parts == ['api', 'selection']:
                cases = select_cases(service._catalog().rows, value.get('selection', {}))
                return self._send(200, {'total': len(cases), 'preview': cases[:20]})
            if parts == ['api', 'adapters', 'import']:
                return self._send(201, service.import_adapter(value['path'], parallel_safe=value.get('parallel_safe', False), adapter_id=value.get('id')))
            if parts == ['api', 'adapters', 'save']:
                return self._send(201, service.save_adapter(value))
            if parts == ['api', 'adapters', 'check']:
                return self._send(200, service.check_adapter(value['id']))
            if parts == ['api', 'experiments']:
                return self._send(201, service.save(value))
            if parts == ['api', 'experiments', 'import']:
                return self._send(201, service.import_run(value['path']))
            if len(parts) == 4 and parts[:2] == ['api', 'experiments']:
                identifier, action = parts[2:]
                service.directory(identifier)
                if action in {'save', 'append'}:
                    return self._send(200, service.save(value, identifier, append=action == 'append'))
                if action == 'start':
                    return self._send(202, service.start(identifier))
                if action in {'pause', 'stop'}:
                    return self._send(200, service.control(identifier, action))
            return self._send(404, {'error': 'Endpoint not found'})
        except Exception as exc:
            self._error(exc)


def serve(data, host='127.0.0.1', port=8765, open_browser=False, workspace=None):
    app = Application(data, workspace)
    try:
        server = LocalServer((host, port), app)
    except OSError as exc:
        raise OSError(f'Cannot open local port {port}; choose another --port. {exc}') from exc
    with server:
        url = f'http://127.0.0.1:{server.server_address[1]}'
        print(f'AstroMemBench: {url}', flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever(poll_interval=.25)
        except KeyboardInterrupt:
            pass
        # Workers intentionally outlive this server. Controls remain available
        # to the CLI or a newly opened UI using the same workspace.
