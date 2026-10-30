"""Install the built wheel in isolation and run tests shipped in the source archive."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import venv


def unpack_source(archive, destination):
    with tarfile.open(archive) as source:
        for member in source:
            target = (destination / member.name).resolve()
            if (not target.is_relative_to(destination) or '\\' in member.name
                    or not (member.isdir() or member.isfile())):
                raise ValueError(f'Invalid source archive member: {member.name}')
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as reader, target.open('wb') as writer:
                    shutil.copyfileobj(reader, writer)
    roots = list(destination.iterdir())
    if len(roots) != 1 or not (roots[0] / 'pyproject.toml').is_file():
        raise ValueError('Expected one source project in the archive')
    return roots[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dist', type=Path, default=Path('dist'))
    parser.add_argument('--workdir', type=Path, required=True, help='New directory for all verification output')
    args = parser.parse_args()
    wheels = list(args.dist.resolve().glob('*.whl'))
    sources = list(args.dist.resolve().glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error('--dist must contain exactly one wheel and one source archive')
    work = args.workdir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = unpack_source(sources[0], work / 'source')
    if (source / 'data/benchmark/tasks.jsonl').exists():
        raise ValueError('The Python source archive must not bundle the full benchmark')
    for relative in ('manifest.json', 'index.json', 'assets/manifest.json'):
        if not (source / 'data/benchmark' / relative).is_file():
            raise ValueError(f'Missing benchmark metadata: {relative}')
    environment = work / 'environment'
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    temporary = work / 'tmp'
    temporary.mkdir()
    env = {key: value for key, value in os.environ.items() if key not in {'PYTHONPATH', 'PYTHONHOME'}}
    env.update(TMP=str(temporary), TEMP=str(temporary), TMPDIR=str(temporary),
               PIP_CACHE_DIR=str(work / 'pip-cache'), PYTHONDONTWRITEBYTECODE='1')

    def run(*arguments, cwd=work):
        subprocess.run([str(python), '-I', '-B', *arguments], check=True, cwd=cwd, env=env)

    run('-m', 'pip', 'install', str(wheels[0]), 'pytest>=8.3,<10')
    run('-c', "from pathlib import Path; import astromembench, sys; "
        "from importlib.metadata import version; from importlib.resources import files; "
        "assert Path(astromembench.__file__).is_relative_to(Path(sys.prefix)); "
        "assert version('astromembench') == '1.0.0'; "
        "assert all(files('astromembench.webui').joinpath('static', name).is_file() "
        "for name in ('index.html', 'app.js', 'style.css')); "
        "print('Installed wheel:', astromembench.__file__)")
    run('-m', 'astromembench', '--version')
    # Disable the source project's pytest path injection: exercise the installed
    # wheel using only tests, fixtures and sidecars from the shipped source archive.
    run('-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--import-mode=importlib',
        '-o', 'pythonpath=', '--basetemp', str(work / 'test-output'), cwd=source)
    print('Distribution verification passed', flush=True)


if __name__ == '__main__':
    main()
