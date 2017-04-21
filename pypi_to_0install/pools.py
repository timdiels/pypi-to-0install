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
Resource pools
'''

from pypi_to_0install.various import ServerProxy, kill
from tempfile import TemporaryDirectory
from contextlib import contextmanager, ExitStack, suppress
from asyncio_extras.contextmanager import async_contextmanager
from pathlib import Path
import plumbum as pb
import logging
import asyncio
import errno
import os

_logger = logging.getLogger(__name__)

@contextmanager
def _pool_get(self):
    '''
    Temporarily acquire a resource from the pool
    '''
    if not self._available:
        self._add()
    item = self._available.pop()
    try:
        yield item
    finally:
        self._available.append(item)

class CgroupsPool(object):

    '''
    Pool of cgroups

    Each group has a 10MB memory+swap usage limit and has minimal disk IO
    priority.

    Examples
    --------
    with CgroupPool as pool:
        with pool.get() as cgroups:
            pass
    '''

    def _cgroup_subsystems():  # @NoSelf
        _cgroup_root = Path('/sys/fs/cgroup')
        _cgroup_subsystems = ('memory', 'blkio')  # the cgroup subsystems we use
        return {
            subsystem: _cgroup_root / subsystem / 'pypi_to_0install'
            for subsystem in _cgroup_subsystems
        }
    _cgroup_subsystems = _cgroup_subsystems()

    def __init__(self):
        # [Path] all cgroups
        self._all = []

        # [[Path]] available cgroups, each [Path] is intended to limit a single process
        self._available = []

        # id used in group names of last created pool resource
        self._last_id = 0

    def _add(self):
        # Add a cgroup in each subsystem we use
        self._last_id += 1
        cgroups = []
        for subsystem, path in self._cgroup_subsystems.items():
            cgroup = path / str(self._last_id)
            cgroup.mkdir()  # Create group
            self._all.append(cgroup)
            if subsystem == 'memory':
                # Limit to 50MB of memory+swap usage
                (cgroup / 'memory.limit_in_bytes').write_text('50M', encoding='ascii')
                (cgroup / 'memory.memsw.limit_in_bytes').write_text('50M', encoding='ascii')
            elif subsystem == 'blkio':
                # give minimal priority for disk IO
                (cgroup / 'blkio.weight').write_text('100', encoding='ascii')
            else:
                assert False, 'unused subsystem: {}'.format(subsystem)
            cgroups.append(cgroup)
        self._available.append(cgroups)

    async def __aenter__(self):
        # Create pypi_to_0install cgroups
        #
        # Note: we never clean these up as we might not have been the ones who
        # created them. E.g. when the sysadmin created them for us instead of
        # granting sudo permissions
        sudo = pb.local['sudo']
        user = pb.local.env['USER']
        for cgroup in self._cgroup_subsystems.values():
            if not cgroup.exists():
                sudo('mkdir', str(cgroup))
            if not os.access(str(cgroup), os.W_OK):
                # Insufficient permissions, set owner to current user
                sudo('chown', user, str(cgroup))
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        # Try to remove all our cgroups
        await asyncio.gather(
            *(self._rm_cgroup(cgroup) for cgroup in self._all),
            return_exceptions=True
        )

    async def _rm_cgroup(self, cgroup):
        # Stubbornly remove cgroup
        while True:
            try:
                cgroup.rmdir()
                return
            except OSError as ex:
                if ex.errno == errno.EBUSY:
                    # If fails due to busy, kill processes in all groups
                    await self._kill_groups([cgroup])
                else:
                    # Else, give up
                    _logger.warning('Could not remove {}'.format(cgroup))
                    return

    async def _kill_groups(self, cgroups):
        '''
        Kill any process still using the cgroups
        '''
        while True:
            pids = set()
            for cgroup in cgroups:
                pids |= set(map(int, (cgroup / 'tasks').read_text().split()))
            if not pids:
                break
            with suppress(asyncio.CancelledError):  # this needs to happen
                await kill(pids, timeout=2)

    @async_contextmanager
    async def get(self):
        with _pool_get(self) as cgroups:
            try:
                yield cgroups
            finally:
                await self._kill_groups(cgroups)

class QuotaDirectoryPool(object):

    '''
    Pool directories with a ~96MB disk quota
    '''

    def __init__(self):
        self._exit_stack = ExitStack()
        self._available = []

    def _add(self):
        # Create temporary directory with disk quota of 250MB - 10MB overhead from ext2
        temporary_directory = Path(self._exit_stack.enter_context(TemporaryDirectory()))
        storage_file = temporary_directory / 'storage'
        pb.local['truncate']('-s', '250m', storage_file)  # Create sparse file
        pb.local['mkfs']('-t', 'ext2', '-m', 0, storage_file)
        mount_point = temporary_directory / 'mount_point'
        mount_point.mkdir()
        pb.local['sudo']('mount', '-t', 'ext2', storage_file, mount_point)
        self._exit_stack.callback(pb.local['sudo'], 'umount', '--force', mount_point)
        pb.local['sudo']('chown', pb.local.env['USER'], mount_point)
        self._available.append(mount_point)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        self._exit_stack.close()

    get = _pool_get

class ServerProxyPool(object):

    '''
    Pool of xmlrpc server proxies
    '''

    def __init__(self, uri):
        self._uri = uri
        self._all = []
        self._available = []

    def _add(self):
        self._available.append(ServerProxy(self._uri))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, traceback):
        pass  # TODO cleanup proxies

    get = _pool_get

class CombinedPool(object):

    def __init__(self, pypi_uri):
        self._cgroups_pool = CgroupsPool()
        self._quota_directory_pool = QuotaDirectoryPool()
        self._pypi_proxy_pool = ServerProxyPool(pypi_uri)

    def cgroups(self):
        return self._cgroups_pool.get()

    def quota_directory(self):
        return self._quota_directory_pool.get()

    def pypi(self):
        '''
        Get ServerProxy of Python index XMLRPC interface
        '''
        return self._pypi_proxy_pool.get()

    async def __aenter__(self):
        self._pypi_proxy_pool.__enter__()
        self._quota_directory_pool.__enter__()
        await self._cgroups_pool.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        await self._cgroups_pool.__aexit__(exc_type, exc_val, traceback)
        self._quota_directory_pool.__exit__(exc_type, exc_val, traceback)
        self._pypi_proxy_pool.__exit__(exc_type, exc_val, traceback)
