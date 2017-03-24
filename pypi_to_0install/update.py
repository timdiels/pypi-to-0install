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

from pypi_to_0install.various import Package, atomic_write, zi, canonical_name
from pypi_to_0install.convert import convert, NoValidRelease
from pypi_to_0install.logging import feed_log_handler
from tempfile import NamedTemporaryFile
from textwrap import dedent, indent
from pathlib import Path
from multiprocessing.pool import Pool
from lxml import etree
import plumbum as pb
import logging
import pickle
import attr
import sys
import os

logger = logging.getLogger(__name__)

def update(context, worker_count):
    check_gpg_signing()
    
    # Load state
    os.makedirs(str(context.feeds_directory), exist_ok=True)
    state = _State.load()
    
    # Get list of changed packages
    logger.info('Getting changelog from PyPI')
    newest_serial = context.pypi.changelog_last_serial()
    if not state.last_serial:
        state.packages = {pypi_name: Package(pypi_name) for pypi_name in context.pypi.list_packages()}
        state.changed = state.packages.copy()
    else:
        changed = _changed_packages_since(context, state.last_serial)  # set of pypi_name
        changed -= state.changed.keys()  # ignore changes to packages already in state.changed
        
        # Create packages for brand new packages
        for pypi_name in changed - state.packages.keys():
            state.packages[pypi_name] = Package(pypi_name)
        
        # Add changed packages to state.changed
        for pypi_name in changed:
            state.changed[pypi_name] = state.packages[pypi_name]
    state.last_serial = newest_serial
    
    # Return if no changes
    if not state.changed:
        logger.info('Nothing changed')
        state.save()
        return
    
    # Update all
    errored = False
    try:
        # Update/create feeds of changed packages, multithreaded
        with Pool(worker_count) as pool:  # calls pool.terminate on exit
            logger.debug('Updating feeds with {} workers'.format(worker_count))
            args = ((context, package) for package in list(state.changed.values()))
            results = pool.imap_unordered(_update_feed, args, chunksize=1)
            for package, finished in results:
                # If error, note and continue
                if isinstance(package, Exception):
                    errored = True
                    continue
                    
                # Update packages with changed package (it's a different
                # instance due to crossing process boundaries)
                state.packages[package.name] = package
                
                # Remove from todo list (changed) if finished
                if not finished:
                    context.feed_logger.warning('Partially updated, will retry failed parts on next run')
                else:
                    context.feed_logger.info('Fully updated')
                    del state.changed[package.name]
    finally:
        # Save progress
        state.save()
        
        # Exit non-zero iff errored
        if errored:
            logger.error('There were errors, programmer required, see exception(s) in log')
            sys.exit(1)
            
def check_gpg_signing():
    # Check GPG signing works
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
            _sign_feed(f.name)
        finally:
            f.close()
            Path(f.name).unlink()
    except pb.ProcessExecutionError as ex:
        # It doesn't work
        shell = (
            '$ {}\n'
            '{}\n'
            '{}'
            .format(
                ' '.join(ex.argv),
                ex.stdout,
                ex.stderr
            )
        )
        logger.error(
            'Failed to sign test feed, likely cause: no secret gpg key found.\n\n'
            + indent(shell, '  ')
        )
        sys.exit(1)

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
    
def _changed_packages_since(context, serial):
    changes = context.pypi.changelog_since_serial(serial)  # list of five-tuples (name, version, timestamp, action, serial) since given serial
    return {change[0] for change in changes}

def _update_feed(args):
    '''
    Update feed
    
    Parameters
    ----------
    args : (Context, Package)
    
    Returns
    -------
    package : Package or Exception
        The package that was passed to this function. Or if there was an
        unhandled exception, it is returned instead.
    finished : bool
        See convert's return
    '''
    try:
        context, package = args
        zi_name = canonical_name(package.name)
        feed_file = context.feed_file(zi_name)
        with feed_log_handler(context, feed_file.with_suffix('.log')):
            context.feed_logger.info('Updating {!r}'.format(package.name))
            
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
                _sign_feed(f.name)
            
            context.feed_logger.info('Feed written')
        
        return package, finished
    except Exception as ex:
        context.feed_logger.exception('Unhandled error occurred')
        return ex, False

def _sign_feed(path):
    pb.local['0launch']('http://0install.net/2006/interfaces/0publish', '--xmlsign', str(path))