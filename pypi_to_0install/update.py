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

from pypi_to_0install.convert import convert, NoValidRelease
from pypi_to_0install.various import zi, canonical_name, Blacklists
from contextlib import contextmanager
from pathlib import Path
from lxml import etree
from tempfile import NamedTemporaryFile
from collections import defaultdict
import plumbum as pb
import contextlib
import logging
import attr
import sys
import shutil
import os
import pickle

logger = logging.getLogger(__name__)

def update(context):
    os.makedirs(str(context.feeds_directory), exist_ok=True)
    state = _State.load()
    
    # Get list of changed packages
    logger.info('Getting changelog from PyPI')
    newest_serial = context.pypi.changelog_last_serial()
    if not state.last_serial:
        state.changed = set(context.pypi.list_packages())
    else:
        state.changed |= _changed_packages_since(context, state.last_serial)
    state.last_serial = newest_serial
    
    try:
        # Update/create feeds of changed packages
        errored = False
        for pypi_name in sorted(state.changed.copy()): #TODO tmp sorted, debug
            try:
                failed_partially = _update_feed(context, pypi_name, state.blacklists)
                if failed_partially:
                    context.feed_logger.warning('Partially updated, will retry failed parts on next run')
                else:
                    context.feed_logger.info('Fully updated')
                    state.changed.remove(pypi_name)
            except Exception:
                errored = True
                context.feed_logger.exception('Unhandled error occurred.')
        
        # Exit non-zero iff errored
        if errored:
            logger.error('There were errors, programmer required, see exception(s) in log')
            sys.exit(1)
    finally:
        state.save()

@attr.s
class _State(object):
    
    # int or None. None iff never updated before
    last_serial = attr.ib()
    
    # {pypi_name :: str}. Changed packages. Packages to update.
    changed = attr.ib()
    
    # defaultdict({pypi_name :: str => _Blacklists}).
    blacklists = attr.ib()
    
    _file = Path('state')
    
    @staticmethod
    def load():
        if _State._file.exists():
            with _State._file.open('rb') as f:
                return pickle.load(f)
        else:
            return _State(
                last_serial=None,
                changed=set(),
                blacklists=defaultdict(Blacklists)
            )
        
    def save(self):
        with _atomic_write(_State._file) as f:
            pickle.dump(self, f)
    
def _changed_packages_since(context, serial):
    changes = context.pypi.changelog_since_serial(serial)  # list of five-tuples (name, version, timestamp, action, serial) since given serial
    return {change[0] for change in changes}
        
@contextmanager
def _feed_log_handler(context, log_file):
    file_handler = logging.FileHandler(str(log_file))
    with contextlib.closing(file_handler):
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {message}', style='{'))
        context.feed_logger.addHandler(file_handler)
        try:
            yield
        finally:
            context.feed_logger.removeHandler(file_handler)
            
def _update_feed(context, pypi_name, blacklists):
    '''
    Update feed
    
    Parameters
    ----------
    context : Context
    pypi_name : str
    blacklists : various.Blacklists
    
    Returns
    -------
    failed_partially : bool
        True iff conversion failed partially, e.g. failed to download archive.
        Skipping unsupported conversions does not count as failure, e.g.
        ignoring a ===foo specifier does not return True.
    '''
    zi_name = canonical_name(pypi_name)
    feed_file = context.feed_file(zi_name)
    with _feed_log_handler(context, feed_file.with_suffix('.log')):
        context.feed_logger.info('Updating {!r}'.format(pypi_name))
        
        # Read ZI feed file corresponding to the PyPI package, if any 
        if feed_file.exists():
            feed = etree.parse(str(feed_file))
        else:
            feed = etree.ElementTree(zi.interface())
            
        # Convert to ZI feed
        try:
            feed, failed_partially = convert(context, pypi_name, zi_name, feed, blacklists[pypi_name])
        except NoValidRelease:
            context.feed_logger.info('Package has no valid release, not generating a feed file')
            return False
        
        # Write feed
        with _atomic_write(feed_file) as f:
            feed.write(f, pretty_print=True)
            f.close()
            pb.local['0launch']('http://0install.net/2006/interfaces/0publish', '--xmlsign', f.name)
        
        context.feed_logger.info('Feed written')
    
    return failed_partially

@contextmanager
def _atomic_write(destination, mode='w+b'):  #TODO move to CTU project
    f = NamedTemporaryFile(mode=mode, delete=False)
    try:
        yield f
        f.close()
        shutil.move(f.name, str(destination.absolute()))  # acts like `mv -f a b`
    except:
        Path(f.name).unlink()
        raise
    