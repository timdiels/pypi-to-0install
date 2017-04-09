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

from pypi_to_0install.various import (
    Package, atomic_write, ServerProxy, feeds_directory
)
from pypi_to_0install import parallel
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import plumbum as pb
import asyncio
import logging
import pickle
import attr
import sys
import os

logger = logging.getLogger(__name__)

def update(context, worker_count):
    # Load state
    os.makedirs(str(feeds_directory), exist_ok=True)
    state = _State.load()
    
    # Get list of changed packages
    logger.info('Getting changelog from PyPI')
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
            logger.info('Nothing changed')
            return
        
        # Update/create feeds for changed packages, with a pool of worker processes
        logger.debug('Updating feeds with {} workers'.format(worker_count))
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(worker_count * 5)
        loop.set_default_executor(executor)
        try:
            loop.run_until_complete(
                parallel.update(context, worker_count, state)
            )
        except asyncio.CancelledError:
            sys.exit(2)
        finally:
            executor.shutdown(wait=True)  # workaround for https://github.com/python/asyncio/issues/258
            loop.close()
            
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
        logger.info('Saving')
        with atomic_write(_State._file) as f:
            pickle.dump(self, f)
        logger.info('Saved')
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.save()
    
def _changed_packages_since(pypi, serial):
    changes = pypi.changelog_since_serial(serial)  # list of five-tuples (name, version, timestamp, action, serial) since given serial
    return {change[0] for change in changes}
