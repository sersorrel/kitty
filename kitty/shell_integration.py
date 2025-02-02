#!/usr/bin/env python
# vim:fileencoding=utf-8
# License: GPLv3 Copyright: 2021, Kovid Goyal <kovid at kovidgoyal.net>


import os
import time
from contextlib import suppress
from typing import Optional, Union

from .config import atomic_save
from .constants import shell_integration_dir
from .fast_data_types import get_options
from .types import run_once
from .utils import log_error, resolved_shell

posix_template = '''
# BEGIN_KITTY_SHELL_INTEGRATION
if test -e {path}; then source {path}; fi
# END_KITTY_SHELL_INTEGRATION
'''


def atomic_write(path: str, data: Union[str, bytes]) -> None:
    if isinstance(data, str):
        data = data.encode('utf-8')
    atomic_save(data, path)


def safe_read(path: str) -> str:
    with suppress(FileNotFoundError):
        with open(path) as f:
            return f.read()
    return ''


def setup_integration(shell_name: str, rc_path: str, template: str = posix_template) -> None:
    import re
    rc_path = os.path.realpath(rc_path)
    rc = safe_read(rc_path)
    home = os.path.expanduser('~') + '/'
    path = os.path.join(shell_integration_dir, f'kitty.{shell_name}')
    if path.startswith(home):
        path = '$HOME/' + path[len(home):]
    integration = template.format(path=f'"{path}"')
    newrc = re.sub(
        r'^# BEGIN_KITTY_SHELL_INTEGRATION.+?^# END_KITTY_SHELL_INTEGRATION',
        '', rc, flags=re.DOTALL | re.MULTILINE)
    newrc = newrc.rstrip() + '\n\n' + integration
    if newrc != rc:
        atomic_write(rc_path, newrc)


def setup_zsh_integration() -> None:
    base = os.environ.get('ZDOTDIR', os.path.expanduser('~'))
    rc = os.path.join(base, '.zshrc')
    setup_integration('zsh', rc)


def setup_bash_integration() -> None:
    setup_integration('bash', os.path.expanduser('~/.bashrc'))


def atomic_symlink(destination: str, in_directory: str) -> str:
    os.makedirs(in_directory, exist_ok=True)
    name = os.path.basename(destination)
    tmpname = os.path.join(in_directory, f'{name}-{os.getpid()}-{time.monotonic()}')
    os.symlink(destination, tmpname)
    try:
        os.replace(tmpname, os.path.join(in_directory, name))
    except OSError:
        os.unlink(tmpname)
        raise


def setup_fish_integration() -> None:
    base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    base = os.path.join(base, 'fish')
    path = os.path.join(shell_integration_dir, 'kitty.fish')
    atomic_symlink(path, os.path.join(base, 'conf.d'))
    from .complete import completion_scripts
    path = os.path.join(base, 'completions', 'kitty.fish')
    rc = safe_read(path)
    if rc != completion_scripts['fish2']:
        atomic_write(path, completion_scripts['fish2'])


SUPPORTED_SHELLS = {
    'zsh': setup_zsh_integration,
    'bash': setup_bash_integration,
    'fish': setup_fish_integration,
}


def get_supported_shell_name(path: str) -> Optional[str]:
    name = os.path.basename(path).split('.')[0].lower()
    if name in SUPPORTED_SHELLS:
        return name


@run_once
def setup_shell_integration() -> None:
    opts = get_options()
    q = opts.shell_integration.split()
    if opts.shell_integration == 'disabled' or 'no-rc' in q:
        return
    shell = get_supported_shell_name(resolved_shell(opts)[0])
    if shell is None:
        return
    func = SUPPORTED_SHELLS[shell]
    try:
        func()
    except Exception:
        import traceback
        traceback.print_exc()
        log_error(f'Failed to setup shell integration for: {shell}')
