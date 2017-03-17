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

from pypi_to_0install.update import update
from xmlrpc.client import ServerProxy
from pathlib import Path
import logging
import attr
import sys

logger = logging.getLogger(__name__)

#TODO manually check that:
# append to a log file per feed

@attr.s(frozen=True)
class Context(object):
    pypi = attr.ib()
    base_uri = attr.ib()  # base URI where all files will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
    feed_logger = attr.ib()
    
    @property
    def feeds_directory(self):
        return Path('feeds').absolute()
    
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
    
def main():
    context = Context(
        pypi=ServerProxy('https://pypi.python.org/pypi', use_datetime=True),  # See https://wiki.python.org/moin/PyPIXmlRpc
        base_uri='https://timdiels.github.io/pypi-to-0install/',
        pypi_mirror='http://localhost/',
        feed_logger=logging.getLogger(__name__ + ':current_feed')
    )
    
    configure_logging(context)

    try:
        update(context)
    except KeyboardInterrupt:
        logger.info('Interrupted')
        sys.exit(1)
        
def configure_logging(context): #TODO manually test feed logger and main logger are set up correctly
    root_logger = logging.getLogger()
    
    # Reset logging (zeroinstall calls logging.basicConfig when imported, naughty naughty)
    while root_logger.handlers:
        root_logger.removeHandler(root_logger.handlers[-1])
    
    # Log info to stderr in terse format
    stderr_handler = logging.StreamHandler() # to stderr
    stderr_handler.setFormatter(logging.Formatter('{levelname[0]}: {message}', style='{'))
    root_logger.addHandler(stderr_handler)
    
    # Log debug to file in full format
    file_handler = logging.FileHandler('pypi_to_0install.log')
    file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {message}', style='{'))
    root_logger.addHandler(file_handler)
     
    # Noise levels
    root_logger.setLevel(logging.INFO)
    logging.getLogger('pypi_to_0install').setLevel(logging.DEBUG)
    context.feed_logger.setLevel(logging.DEBUG)
     
    stderr_handler.setLevel(logging.DEBUG)
    file_handler.setLevel(logging.DEBUG)
        
#TODO regularly persist changed_packages so that when killed, we don't miss or redo anything 
#TODO protect against sigkill everywhere; failed downloads; ...
#TODO when killed, surely all is lost as we don't clone?

#TODO only implement this is if run from scratch takes >>30 min. May need to
#have a time limit on the whole process at which we stop work, leaving the rest
#for the next run (Travis time limit)

#TODO
# initial commit: "Initial commit: PyPI serial {}"
# update: "Update: PyPI serial {old} -> {new}"
# Probably don't want to make a separate commit each time; just force update it

if __name__ == '__main__':
    main()

#TODO manually test every aspect or write proper tests