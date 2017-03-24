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

from xmlrpc.client import ServerProxy
from pathlib import Path
import logging
import attr

@attr.s(frozen=True, slots=True, init=False, cmp=False, hash=False)
class Context(object):
    _pypi_uri = attr.ib()  # uri of `pypi` ServerProxy
    base_uri = attr.ib()  # base URI where all files will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
    pypi = attr.ib()  # Generated. ServerProxy. See https://wiki.python.org/moin/PyPIXmlRpc
    
    def __init__(self, pypi_uri, base_uri, pypi_mirror):
        # Note: regular assignment triggers FrozenInstanceError
        object.__setattr__(self, '_pypi_uri', pypi_uri)
        object.__setattr__(self, 'base_uri', base_uri)
        object.__setattr__(self, 'pypi_mirror', pypi_mirror)
        object.__setattr__(self, 'pypi', self._server_proxy(pypi_uri))
    
    def _server_proxy(self, pypi_uri):
        return ServerProxy(self._pypi_uri, use_datetime=True)
    
    @property
    def feeds_directory(self):
        return Path('feeds').absolute()
    
    @property
    def feed_logger(self):
        return logging.getLogger(__name__ + ':current_feed')
    
    def feed_file(self, zi_name):
        '''
        Get local file path to feed 
        '''
        return self.feeds_directory / (zi_name + '.xml')
        
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
    
# Note: can't set directly on class as @attr.s overwrites them
def __getstate__(self):
    return {
        '_pypi_uri': self._pypi_uri,
        'base_uri': self.base_uri,
        'pypi_mirror': self.pypi_mirror,
    }
Context.__getstate__ = __getstate__
del __getstate__

def __setstate__(self, state):
    for attribute, value in state.items():
        object.__setattr__(self, attribute, value)
    object.__setattr__(self, 'pypi', self._server_proxy(self._pypi_uri))
Context.__setstate__ = __setstate__
del __setstate__  