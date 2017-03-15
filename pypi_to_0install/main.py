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

import logging
from pypi_to_0install.convert import convert
from pypi_to_0install.various import zi, canonical_name 
from xmlrpc.client import ServerProxy
import attr
from contextlib import contextmanager
import contextlib
from pathlib import Path
import urllib.error
from lxml import etree

logger = logging.getLogger(__name__)

#TODO manually check that:
# append to a log file per feed

@attr.s(frozen=True)
class Context(object):
    pypi = attr.ib()
    feeds_uri = attr.ib()  # the location where the feeds will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
    feed_logger = attr.ib()
    
    def feed_uri(self, zi_name, converted=True):
        '''
        converted : bool
            True if the feed was converted from a PyPI package
        '''
        return '{}{}{}.xml'.format(
            self.feeds_uri,
            'converted/' if converted else '',
            zi_name
        )
    
def main():
    context = Context(
        pypi=ServerProxy('https://pypi.python.org/pypi', use_datetime=True),  # See https://wiki.python.org/moin/PyPIXmlRpc
        feeds_uri='https://timdiels.github.io/pypi-to-0install/feeds/',
        pypi_mirror='http://localhost/',
        feed_logger=logging.getLogger(__name__ + ':current_feed')
    )
    
    configure_logging(context)

    # Get list of changed packages
    #TODO uncomment, debug
#     if not last_serial:
#         changed_packages = pypi.list_packages()  # [package_name :: str] #TODO should be a set
#     else:
#         serial = pypi.changelog_last_serial()
#         changed_packages = changed_packages_since(context, last_serial)
        #TODO save changed_packages and also save serial as last_serial
        #TODO add log messages to this part
    
    # Update/create feeds of changed packages
    changed_packages = {'chicken_turtle_util'}  #TODO rm, debug
#     changed_packages = ['FireWorks']  #TODO rm, debug
    for pypi_name in changed_packages.copy(): #TODO when a package raises (only on some errors, e.g. a release_url disappeared), skip it and try again next run
        zi_name = canonical_name(pypi_name)
        feed_file = Path(zi_name + '.xml')
        with feed_log_handler(context, feed_file.with_suffix('.log')):
            try:
                context.feed_logger.info('Updating {}'.format(pypi_name))
                
                # Read ZI feed file corresponding to the PyPI package, if any 
                if feed_file.exists():
                    assert False  #TODO implement: parse it
                    feed = stuff
                else:
                    feed = etree.ElementTree(zi.interface())
                    
                # Convert to ZI feed
                feed = convert(context, pypi_name, zi_name, feed)
                
                # Write feed
                context.feed_logger.info('Swapping old feed file with new one')  # TODO write to a temp feed file, then swap to avoid corrupt fail that would crash next run
                context.feed_logger.info('Swapped')
                #TODO also sign it
                write(feed)
                
                # Mark package up to date
                changed_packages.remove(pypi_name)
                save_changed_packages(changed_packages)
                context.feed_logger.info('Marked up to date')
            except urllib.error.HTTPError:
                context.feed_logger.exception('Error occurred, will retry updating package on next run')

def load_changed_packages():
    with open('changed_packages') as f:
        return set(f.read().split())
    
def save_changed_packages(changed_packages):
    with open('changed_packages') as f:
        f.write('\n'.join(changed_packages))
        
def load_last_serial():
    with open('last_serial') as f:
        return int(f.read().trim())
    
def write_last_serial(last_serial):
    with open('last_serial') as f:
        f.write(str(last_serial))
        
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
    
@contextmanager
def feed_log_handler(context, log_file):
    file_handler = logging.FileHandler(str(log_file))
    with contextlib.closing(file_handler):
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {message}', style='{'))
        context.feed_logger.addHandler(file_handler)
        try:
            yield
        finally:
            context.feed_logger.removeHandler(file_handler)
        
#TODO regularly persist changed_packages so that when killed, we don't miss or redo anything 
#TODO protect against sigkill everywhere; failed downloads; ...
#TODO when killed, surely all is lost as we don't clone?

#TODO only implement this is if run from scratch takes >>30 min. May need to
#have a time limit on the whole process at which we stop work, leaving the rest
#for the next run (Travis time limit)
    
def changed_packages_since(context, serial):
    changes = context.pypi.changelog_since_serial(serial)  # list of five-tuples (name, version, timestamp, action, serial) since given serial
    return [change[0] for change in changes]

#TODO
# initial commit: "Initial commit: PyPI serial {}"
# update: "Update: PyPI serial {old} -> {new}"
# Probably don't want to make a separate commit each time; just force update it

if __name__ == '__main__':
    main()

#TODO manually test every aspect or write proper tests