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

from pypi_to_0install.various import sign_feed
from pypi_to_0install.pools import CombinedPool
from pypi_to_0install import worker as worker_
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from textwrap import dedent, indent
from pathlib import Path
import subprocess
import logging
import asyncio
import sys

_logger = logging.getLogger(__name__)

async def update(context, worker_count, state):
    '''
    Update feeds of changed packages in parallel

    Notes
    -----
    While unpacking does require processing, it occurs in a subprocess, so all
    in all we are IO bound and thus multiprocessing is unnecessary for optimal
    performance.
    '''
    await _check_gpg_signing()
    async with CombinedPool(context.pypi_uri) as pool:
        with _exit_on_error() as errored:
            # Create worker_count worker tasks
            packages = list(state.changed.values())
            workers = [
                worker_.update_feeds(context, pool, packages, state, errored)
                for _ in range(worker_count)
            ]

            # Await workers
            await asyncio.gather(*workers)

@contextmanager
def _exit_on_error():
    # Exit non-zero iff errored
    errored_ = False
    def errored():
        nonlocal errored_
        errored_ = True  # @UnusedVariable, it doesn't understand nonlocal
    try:
        yield errored
    except asyncio.CancelledError:
        raise
    except Exception:
        _logger.exception('Unhandled error occurred')
    finally:
        if errored_:
            _logger.error('There were errors, programmer required, see exception(s) in log')
            sys.exit(3)

async def _check_gpg_signing():
    # Check GPG signing works
    try:
        # Sign a dummy feed
        f = NamedTemporaryFile(delete=False)
        try:
            f.write(dedent('''\
                <?xml version='1.0'?>
                <interface xmlns='http://zero-install.sourceforge.net/2004/injector/interface'>
                  <name>dummy</name>
                  <summary>dummy</summary>
                </interface>'''
            ).encode())
            f.close()
            await sign_feed(f.name)
        finally:
            f.close()
            Path(f.name).unlink()
    except subprocess.CalledProcessError as ex:
        # It doesn't work
        _logger.error(
            'Failed to sign test feed, likely cause: no secret gpg key found.\n\n'
            + indent(str(ex), ' ' * 4)
        )
        sys.exit(1)
