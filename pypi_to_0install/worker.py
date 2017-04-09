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
    atomic_write, zi, canonical_name, sign_feed, PyPITimeout, async_cancel
)
from pypi_to_0install.convert import convert, NoValidRelease
from pypi_to_0install.logging import feed_logger
from pypi_to_0install.various import feeds_directory
from lxml import etree
import logging
import asyncio
import attr

logger = logging.getLogger(__name__)

@attr.s(frozen=True, slots=True, cmp=False, hash=False)
class WorkerContext(object):
    
    base_uri = attr.ib()  # base URI where all files will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
    feed_logger = attr.ib()
    pool = attr.ib()  # CombinedPool
    
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
    
async def update_feeds(context, pool, packages, state, errored):
    '''
    Update feeds
    
    Parameters
    ----------
    context : Context
    pool : CombinedPool
        Pool of resources
    packages : [Package]
        packages to update. This may be shared with other workers as well
    errored : () -> None
        function that is called when unhandled error occurs
    '''
    # Update packages one by one and note results
    while packages:
        # Wait for one to finish
        package = packages.pop()
        finished = await update_feed(context, pool, package, errored)
            
        # Remove from todo list (changed) if finished
        if finished:
            del state.changed[package.name]
    
async def update_feed(context, pool, package, errored):
    '''
    Update feed
    
    Parameters
    ----------
    context : Context
    pool : CombinedPool
        Pool of resources
    package : Package
        packages to update. This may be shared with other workers as well
        
    Returns
    -------
    finished : bool
        See convert's return
    '''
    # Logging and exception handling that wraps _update_feed which does the
    # actual updating
    zi_name = canonical_name(package.name)
    feed_file = feeds_directory / (zi_name + '.xml')
    with feed_logger(zi_name, feed_file.with_suffix('.log')) as feed_logger_:
        worker_context = WorkerContext(context.base_uri, context.pypi_mirror, feed_logger_, pool)
        try:
            finished = await _update_feed(worker_context, package, zi_name, feed_file)
            if not finished:
                worker_context.feed_logger.warning('Partially updated, will retry failed parts on next run')
            else:
                worker_context.feed_logger.info('Fully updated')
            return finished
        except asyncio.CancelledError:
            raise
        except PyPITimeout as ex:
            logger.error(ex.args[0] + '. PyPI may be having issues or may be blocking us. Giving up')
            async_cancel()
            raise asyncio.CancelledError
        except Exception:
            worker_context.feed_logger.exception('Unhandled error occurred')
            errored()
            return False
            
async def _update_feed(context, package, zi_name, feed_file):
    context.feed_logger.info('Updating (PyPI name: {!r})'.format(package.name))
    
    # Read ZI feed file corresponding to the PyPI package, if any 
    if feed_file.exists():
        feed = etree.parse(str(feed_file))
    else:
        feed = etree.ElementTree(zi.interface())
        
    # Convert to ZI feed
    try:
        feed, finished = await convert(context, package, zi_name, feed)
    except NoValidRelease:
        def log(action):
            context.feed_logger.info('Package has no valid release, {} feed file'.format(action))
        if feed_file.exists():
            log(action='removing its')
            feed_file.unlink()
        else:
            log(action='not generating a')
        return True
    
    # Write feed
    with atomic_write(feed_file) as f:
        feed.write(f, pretty_print=True)
        f.close()
        sign_feed(f.name)
    
    context.feed_logger.info('Feed written')

    return finished
