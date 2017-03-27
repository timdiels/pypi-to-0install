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

import re
import attr
from lxml.builder import ElementMaker
from tempfile import NamedTemporaryFile
from contextlib import contextmanager
from xmlrpc.client import ServerProxy
from functools import partial
from pathlib import Path
import plumbum as pb
import shutil

zi_namespaces = {
    None: 'http://zero-install.sourceforge.net/2004/injector/interface',
    'compile': 'http://zero-install.sourceforge.net/2006/namespaces/0compile'
}
zi = ElementMaker(namespace=zi_namespaces[None], nsmap=zi_namespaces)

ServerProxy = partial(ServerProxy, use_datetime=True)
feeds_directory = Path('feeds').absolute()
_cgroup_root = Path('/sys/fs/cgroup')
cgroup_subsystems = ('memory', 'blkio')  # the cgroup subsystems we use
cgroup_subsystems = {
    subsystem: _cgroup_root / subsystem / 'pypi_to_0install'
    for subsystem in cgroup_subsystems
} 

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
def atomic_write(destination, mode='w+b'):  #TODO move to CTU project
    f = NamedTemporaryFile(mode=mode, delete=False)
    try:
        yield f
        f.close()
        shutil.move(f.name, str(destination.absolute()))  # acts like `mv -f a b`
    except:
        f.close()
        Path(f.name).unlink()
        raise

def print_memory_usage():
    '''
    Print memory usage for debugging
    '''
    from pympler import muppy, summary
    summary.print_(summary.summarize(muppy.get_objects()))

def sign_feed(path):
    pb.local['0launch']('http://0install.net/2006/interfaces/0publish', '--xmlsign', str(path))
