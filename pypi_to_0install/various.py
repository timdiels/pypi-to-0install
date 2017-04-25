# Copyright (C) 2017 Tim Diels <timdiels.m@gmail.com>
#
# This file is part of PyPI to 0install.
#
# PyPI to 0install is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PyPI to 0install is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with PyPI to 0install.  If not, see <http://www.gnu.org/licenses/>.

from lxml.builder import ElementMaker
from tempfile import NamedTemporaryFile
from contextlib import contextmanager, suppress
from xmlrpc.client import ServerProxy
from textwrap import indent, dedent
from functools import partial
from pathlib import Path
from enum import IntEnum
import subprocess
import logging
import asyncio
import signal
import shutil
import psutil
import attr
import re

_logger = logging.getLogger(__name__)
zi_namespaces = {
    None: 'http://zero-install.sourceforge.net/2004/injector/interface',
    'compile': 'http://zero-install.sourceforge.net/2006/namespaces/0compile'
}
zi = ElementMaker(namespace=zi_namespaces[None], nsmap=zi_namespaces)
ServerProxy = partial(ServerProxy, use_datetime=True)
feeds_directory = Path('feeds').absolute()
cancellation_signals = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)

class ExitCode(IntEnum):
    success = 0
    error = 1
    cancellation = 2
    unhandled_error = 3

def canonical_name(pypi_name):
    '''
    Get canonical ZI name
    '''
    return re.sub(r"[-_.]+", "-", pypi_name).lower()

@attr.s(slots=True, cmp=False, hash=False)
class Package(object):

    '''
    A PyPI package
    '''

    # pypi name
    name = attr.ib()

    # Distributions never to try converting (again)
    # {distribution_url :: str}
    blacklisted_distributions = attr.ib(default=attr.Factory(set))

    # Versions that have been ignored
    # {py_version :: str}
    blacklisted_versions = attr.ib(default=attr.Factory(set))

@contextmanager
def atomic_write(destination, mode='w+b'):  # TODO move to CTU project
    f = NamedTemporaryFile(mode=mode, delete=False)
    try:
        yield f
        f.close()
        shutil.move(f.name, str(destination.absolute()))  # acts like `mv -f a b`
    except:
        f.close()
        Path(f.name).unlink()
        raise

class CalledProcessError(subprocess.CalledProcessError):

    '''
    Like CalledProcessError, but with a verbose __str__
    '''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self):
        stdout = indent(self.stdout.decode(), '  ')
        stderr = indent(self.stderr.decode(), '  ')
        return dedent('''\
            Process exited {}, command:
              {}

            out:
            {}

            err:
            {}
            '''.format(
                self.returncode,
                ' '.join(map(repr, self.cmd)),
                stdout,
                stderr
            )
        )

# TODO add to CTU, perhaps rename, probably too inflexible
async def check_call(*args):
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    try:
        stdout, stderr = await asyncio.gather(
            process.stdout.read(),
            process.stderr.read()
        )
    except Exception as ex:
        with suppress(ProcessLookupError):
            process.terminate()
        await kill([process.pid], timeout=1)
        raise ex
    finally:
        await process.wait()
    if process.returncode != 0:
        raise CalledProcessError(
            process.returncode, args, stdout, stderr
        )

class PyPITimeout(Exception):
    pass

async def kill(pids, timeout):
    '''
    Kill process and wait it to terminate

    First sends SIGTERM, then after a timeout sends SIGKILL.

    Parameters
    ----------
    pids : iterable(int)
        Processes to kill
    timeout : int
        Timeout in seconds before sending SIGKILL.
    '''
    processes = []
    for pid in pids:
        with suppress(psutil.NoSuchProcess):
            processes.append(psutil.Process(pid))
    if not processes:
        return

    # Send SIGTERM
    for process in processes:
        with suppress(psutil.NoSuchProcess):
            process.terminate()

    # Wait
    _, processes = await asyncio.get_event_loop().run_in_executor(None, psutil.wait_procs, processes, timeout)

    # Send SIGKILL
    if processes:
        for process in processes:
            with suppress(psutil.NoSuchProcess):
                process.kill()
