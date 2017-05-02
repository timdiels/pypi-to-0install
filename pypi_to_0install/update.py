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

'''
Logic of updating all feeds

For actual conversion of a package to a feed, see convert()
'''

from pypi_to_0install.various import (
    Package, atomic_write, ServerProxy, feeds_directory, ExitCode,
    cancellation_signals, zi, check_call, canonical_name, PyPITimeout
)
from pypi_to_0install.convert import convert, NoValidRelease
from pypi_to_0install.logging import feed_logger
from pypi_to_0install.pools import CombinedPool
from concurrent.futures import ThreadPoolExecutor
from tempfile import NamedTemporaryFile
from contextlib import contextmanager
from textwrap import dedent, indent
from pathlib import Path
from lxml import etree  # @UnresolvedImport
import subprocess
import asyncio
import logging
import pickle
import attr
import sys
import os

_logger = logging.getLogger(__name__)

def update(context, worker_count):
    '''
    Update feeds of all changed packages
    '''
    # Load state
    os.makedirs(str(feeds_directory), exist_ok=True)
    state = _State.load()

    # Get list of changed packages
    _logger.info('Getting changelog from PyPI')
    with ServerProxy(context.pypi_uri) as pypi:
        newest_serial = pypi.changelog_last_serial()
        if not state.last_serial:
            state.packages = {pypi_name: Package(pypi_name) for pypi_name in pypi.list_packages()}
            state.changed = state.packages.copy()
        else:
            changed = _changed_packages_since(pypi, state.last_serial)  # set of pypi_name
            changed -= state.changed.keys()  # ignore changes to packages already in state.changed

            # Create packages for brand new packages
            for pypi_name in changed - state.packages.keys():
                state.packages[pypi_name] = Package(pypi_name)

            # Add changed packages to state.changed
            for pypi_name in changed:
                state.changed[pypi_name] = state.packages[pypi_name]
    state.last_serial = newest_serial

    #
    with state:  # save on exit
        # Return if no changes
        if not state.changed:
            _logger.info('Nothing changed')
            return

        # Update/create feeds for changed packages, with a pool of worker processes
        _logger.debug('Updating feeds with {} workers'.format(worker_count))
        with _robust_main_loop(worker_count) as loop:
            loop.run_until_complete(
                _async_update(context, worker_count, state)
            )

async def _async_update(context, worker_count, state):
    '''
    Update feeds of changed packages asynchronously

    Notes
    -----
    While unpacking does require processing, it occurs in a subprocess, so all
    in all we are IO bound and thus multiprocessing is unnecessary for optimal
    performance.
    '''
    await _ensure_gpg_signing_works()
    async with CombinedPool(context.pypi_uri) as pool:
        with _exit_on_error() as errored:
            packages = list(state.changed.values())
            async def update_one_by_one():
                while packages:
                    # Update one
                    package = packages.pop()
                    finished = False
                    with _feed_context(context, pool, package, errored) as feed_context:
                        finished = await _update_feed(feed_context, package)
                        if finished:
                            feed_context.logger.info('Fully updated')
                            del state.changed[package.name]  # Remove from todo list
                        else:
                            feed_context.logger.warning('Partially updated, will retry failed parts on next run')

            # Create worker_count worker tasks
            workers = [
                update_one_by_one() for _ in range(worker_count)
            ]

            # Await workers
            await asyncio.gather(*workers)

async def _update_feed(context, package):
    '''
    Update feed of package

    Parameters
    ----------
    context : FeedContext
        Feed context of package
    package : Package

    Returns
    -------
    finished : bool
        See convert(...)[1]
    '''
    context.logger.info('Updating (PyPI name: {!r})'.format(package.name))

    # Read ZI feed file corresponding to the PyPI package, if any
    if context.feed_file.exists():
        feed = etree.parse(str(context.feed_file))
    else:
        feed = etree.ElementTree(zi.interface())

    # Convert to ZI feed
    try:
        feed, finished = await convert(context, package, feed)
    except NoValidRelease:
        def log(action):
            context.logger.info('Package has no valid release, {} feed file'.format(action))
        if context.feed_file.exists():
            log(action='removing its')
            context.feed_file.unlink()
        else:
            log(action='not generating a')
        return True

    # Write feed
    with atomic_write(context.feed_file) as f:
        feed.write(f, pretty_print=True)
        f.close()
        await _sign_feed(f.name)

    context.logger.info('Feed written')

    return finished


###############################################################################
# Various

@contextmanager
def _robust_main_loop(worker_count):
    '''
    Configure current loop, close it on exit
    '''
    loop = asyncio.get_event_loop()

    # Set custom executor
    executor = ThreadPoolExecutor(worker_count * 5)
    loop.set_default_executor(executor)

    # Cancel on cancellation signals
    def set_handlers():
        for signal_ in cancellation_signals:
            loop.add_signal_handler(signal_, _asyncio_cancel_all)
    loop.call_soon(set_handlers)

    # Yield it
    try:
        yield loop
    except asyncio.CancelledError:
        sys.exit(ExitCode.cancellation)
    finally:
        # Wait for executor to finish, then close loop
        executor.shutdown(wait=True)  # workaround for https://github.com/python/asyncio/issues/258
        loop.close()

def _asyncio_cancel_all():
    _logger.info('Cancelling')
    for task in asyncio.Task.all_tasks():
        task.cancel()

def _changed_packages_since(pypi, serial):
    changes = pypi.changelog_since_serial(serial)  # list of five-tuples (name, version, timestamp, action, serial) since given serial
    return {change[0] for change in changes}

@attr.s(cmp=False, hash=False)
class _State(object):

    # int or None. None iff never updated before
    last_serial = attr.ib()

    # Changed packages. Packages to update.
    # {pypi_name :: str => Package}
    changed = attr.ib()

    # All packages
    # {pypi_name :: str => Package}
    packages = attr.ib()

    _file = Path('state')

    @staticmethod
    def load():
        if _State._file.exists():
            with _State._file.open('rb') as f:
                return pickle.load(f)
        else:
            return _State(
                last_serial=None,
                changed={},
                packages={}
            )

    def save(self):
        _logger.info('Saving')
        with atomic_write(_State._file) as f:
            pickle.dump(self, f)
        _logger.info('Saved')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.save()

@contextmanager
def _exit_on_error():
    '''
    Exit non-zero iff errored

    Yields function that should be called when unhandled error occurs
    '''
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
            _logger.error('There were unhandled errors, this may be a bug, see exception(s) in log')
            sys.exit(ExitCode.unhandled_error)

async def _ensure_gpg_signing_works():
    '''
    Ensure GPG signing works
    '''
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
            await _sign_feed(f.name)
        finally:
            f.close()
            Path(f.name).unlink()
    except subprocess.CalledProcessError as ex:
        # It doesn't work
        _logger.error(
            'Failed to sign test feed, likely cause: no secret gpg key found.\n\n'
            + indent(str(ex), ' ' * 4)
        )
        sys.exit(ExitCode.error)

@attr.s(frozen=True, slots=True, cmp=False, hash=False)
class FeedContext(object):

    base_uri = attr.ib()  # base URI where all files will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
    logger = attr.ib()
    pool = attr.ib()  # CombinedPool
    zi_name = attr.ib()  # str
    feed_file = attr.ib()  # Path

    def feed_uri(self, zi_name):
        '''
        Get URI to feed

        Parameters
        ----------
        zi_name : str
        converted : bool
            True if the feed was converted from a PyPI package

        Returns
        -------
        str
        '''
        return '{}/feeds/{}.xml'.format(self.base_uri, zi_name)

    def script_uri(self, name):
        '''
        Get URI to PyPI to 0install script feed

        Parameters
        ----------
        name : str

        Returns
        -------
        str
        '''
        return '{}/pypi_to_0install/{}.xml'.format(self.base_uri, name)

async def _feed_context(context, pool, package, errored, feed_file):
    '''
    Enter feed context of package

    This includes robust error handling.

    Parameters
    ----------
    context : Context
    pool : CombinedPool
        Pool of resources
    package : Package
        packages to update. This may be shared with other workers as well
    errored : () -> None
        This function is called on error
    '''
    # Logging and exception handling that wraps _update_feed which does the
    # actual updating
    zi_name = canonical_name(package.name)
    feed_file = feeds_directory / (zi_name + '.xml')
    with feed_logger(zi_name, feed_file.with_suffix('.log')) as feed_logger_:
        feed_context = FeedContext(context.base_uri, context.pypi_mirror, feed_logger_, pool, zi_name, feed_file)
        try:
            yield feed_context
        except asyncio.CancelledError:
            raise
        except PyPITimeout as ex:
            _logger.error(ex.args[0] + '. PyPI may be having issues or may be blocking us. Giving up')
            _asyncio_cancel_all()
            raise asyncio.CancelledError
        except Exception:
            feed_context.logger.exception('Unhandled error occurred')
            errored()

async def _sign_feed(path):
    await check_call(
        '0launch', 'http://0install.net/2006/interfaces/0publish', '--xmlsign', str(path)
    )
