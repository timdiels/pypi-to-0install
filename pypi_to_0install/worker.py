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
Entry point of a feed update worker
'''

from pypi_to_0install.various import (
    atomic_write, zi, canonical_name, ServerProxy, sign_feed,
    feeds_directory, cgroup_subsystems
)
from pypi_to_0install.convert import convert, NoValidRelease
from pypi_to_0install.logging import configure_feed_logger, feed_logger
from lxml import etree
import contextlib
import attr
import os

@attr.s(frozen=True, slots=True, cmp=False, hash=False)
class WorkerContext(object):
    
    pypi = attr.ib()  # ServerProxy of Python index XMLRPC interface
    base_uri = attr.ib()  # base URI where all files will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
    
    @property
    def feed_logger(self):
        return feed_logger
    
    def feed_file(self, zi_name):
        '''
        Get local file path to feed 
        '''
        return feeds_directory / (zi_name + '.xml')
        
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
    
    def cgroup(self, subsystem):
        '''
        Path to setup.py cgroup for this worker for given subsystem
        
        Parameters
        ----------
        subsystem : str
            E.g. 'memory' or 'blkio'
        '''
        return cgroup_subsystems[subsystem] / str(os.getpid())
    
def initialize(pypi_uri, base_uri, pypi_mirror):
    '''
    Called to initialize the worker process
    
    Parameters
    ----------
    pypi_uri : str
        uri of Python index XMLRPC interface. See https://wiki.python.org/moin/PyPIXmlRpc
    base_uri : str
        base URI where all files will be hosted
    pypi_mirror : str
        uri of PyPI mirror to use for downloads, if any
    '''
    global _context
    _context = WorkerContext(
        ServerProxy(pypi_uri),
        base_uri,
        pypi_mirror
    )
    
    # Configure cgroup for executing setup.py
    for subsystem in cgroup_subsystems:
        cgroup = _context.cgroup(subsystem)
        cgroup.mkdir()  # Create group
        if subsystem == 'memory':
            # Limit to 10MB of memory+swap usage
            (cgroup / 'memory.limit_in_bytes').write_text('10M', encoding='ascii')
            (cgroup / 'memory.memsw.limit_in_bytes').write_text('10M', encoding='ascii')
        elif subsystem == 'blkio':
            # give minimal priority for disk IO
            (cgroup / 'blkio.weight').write_text('100', encoding='ascii')
        else:
            assert False, 'unused subsystem: {}'.format(subsystem)

def update_feed(package):
    '''
    Update feed in worker process
    
    Parameters
    ----------
    package : Package
        The package whose feed to update
    
    Returns
    -------
    package : Package or Exception
        The package that was passed to this function. Or if there was an
        unhandled exception, the exception is returned instead.
    finished : bool
        See convert's return
    '''
    global _context
    
    # Logging and exception handling that wraps _update_feed which does the
    # actual updating
    with contextlib.ExitStack() as exit_stack:  # removes feed log handler
        try:
            package, finished = _update_feed(_context, package, exit_stack)
            if not finished:
                _context.feed_logger.warning('Partially updated, will retry failed parts on next run')
            else:
                _context.feed_logger.info('Fully updated')
            return package, finished
        except Exception as ex:
            _context.feed_logger.exception('Unhandled error occurred')
            return ex, False
            
def _update_feed(context, package, exit_stack):
    zi_name = canonical_name(package.name)
    feed_file = context.feed_file(zi_name)
    exit_stack.enter_context(configure_feed_logger(zi_name, feed_file.with_suffix('.log')))
    context.feed_logger.info('Updating (PyPI name: {!r})'.format(package.name))
    
    # Read ZI feed file corresponding to the PyPI package, if any 
    if feed_file.exists():
        feed = etree.parse(str(feed_file))
    else:
        feed = etree.ElementTree(zi.interface())
        
    # Convert to ZI feed
    try:
        feed, finished = convert(context, package, zi_name, feed)
    except NoValidRelease:
        def log(action):
            context.feed_logger.info('Package has no valid release, {} feed file'.format(action))
        if feed_file.exists():
            log(action='removing its')
            feed_file.unlink()
        else:
            log(action='not generating a')
        return package, True
    
    # Write feed
    with atomic_write(feed_file) as f:
        feed.write(f, pretty_print=True)
        f.close()
        sign_feed(f.name)
    
    context.feed_logger.info('Feed written')

    return package, finished
