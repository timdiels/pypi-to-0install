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
CLI interface; signals setup
'''

from pypi_to_0install.update import update
from pypi_to_0install.context import Context
from pypi_to_0install import logging as logging_
from pathlib import Path
import logging
import signal
import click
import sys
import os
import re

logger = logging.getLogger(__name__)

def _default_workers():
    cpu_count = None
    
    # cpuset (limits a process' available processors) 
    try:
        match = re.search(r'(?m)^Cpus_allowed:\s*(.*)$', Path('/proc/self/status').read_text())
    except IOError:
        match = None
    if match:
        res = bin(int(match.group(1).replace(',', ''), 16)).count('1')
        if res > 0:
            cpu_count = res
    
    # Logical cpus
    if not cpu_count:
        cpu_count = os.cpu_count()  # logical cpus
        
    # Return more under the assumption that there will be idling due to IO.
    # Don't return too many though, as it also increases the number of
    # concurrent downloads
    return cpu_count * 2
    
@click.command()
@click.option('--workers', type=click.IntRange(min=1), default=_default_workers, help='Number of threads to use')
@click.option(
    '--pypi-mirror',
    type=str,
    help='PyPI mirror to use, e.g. http://localhost/ when using bandersnatch with default settings'
)
@click.option(
    '-v', '--verbose', 'verbosity',
    count=True, 
    help='Verbosity level. Default prints nothing, '
    '-v prints errors and minimal info, -vv prints all info. '
    'This does not affect logging to files'
)
def main(workers, pypi_mirror, verbosity):
    context = Context(
        pypi_uri='https://pypi.python.org/pypi',
        base_uri='https://timdiels.github.io/pypi-to-0install/',
        pypi_mirror=pypi_mirror,
    )
    
    logging_.configure(context, verbosity)
    
    # Clean exit on cancellation signals
    def cancel(signal_, frame):
        sys.exit(1)
    for signal_ in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signal_, cancel)
    
    # Run
    try:
        update(context, workers)
    finally:
        logger.info('Exited cleanly')

if __name__ == '__main__':
    main()
