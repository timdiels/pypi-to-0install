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

from packaging.version import Version, parse as py_parse_version
from itertools import product
import logging
import pytest

# http://stackoverflow.com/a/30091579/1031434
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)  # Ignore SIGPIPE

@pytest.fixture
def versions():
    '''
    Python version strings that cover all cases
    '''
    # Note: when changing this function, ensure it generates the same versions
    # or a superset thereof. Tests depend on these versions.

    # Note: Python version: [{epoch}!]{release}[{prerelease_type}{prerelease_number}][.post{post_number}][.dev{dev_number}]
    epochs = {0, 1}
    releases = {'0', '0.1', '1', '1.1', '1.2', '2', '2.1'}
    prerelease_types = {'a', 'b', 'rc', None}
    prerelease_numbers = {0, 1}
    post_numbers = {0, 1, None}
    dev_numbers = {0, 1, None}
    products = product(epochs, releases, prerelease_types, prerelease_numbers, post_numbers, dev_numbers)
    versions = []
    for epoch, release, prerelease_type, prerelease_number, post_number, dev_number in products:
        if prerelease_type is None:
            prerelease = ''
        else:
            prerelease = '.{}{}'.format(prerelease_type, prerelease_number)

        if post_number is None:
            post = ''
        else:
            post = '.post{}'.format(post_number)

        if dev_number is None:
            dev = ''
        else:
            dev = '.dev{}'.format(dev_number)

        versions.append('{epoch}!{release}{prerelease}{post}{dev}'.format(
            epoch=epoch,
            release=release,
            prerelease=prerelease,
            post=post,
            dev=dev
        ))

    # Remove duplicates caused by prerelease_types=None yielding the same regardless of prerelease_numbers
    versions = set(versions)

    # Assert valid python versions
    for version in versions:
        assert isinstance(py_parse_version(version), Version)

    return versions

@pytest.fixture(autouse=True)
def init_logging():
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger('pypi_to_0install').setLevel(logging.DEBUG)
