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

from pypi_to_0install.convert._version import parse_version
from lxml import etree  # @UnresolvedImport

def convert_version(version):
    '''
    Get ZI version string given a Python version string
    '''
    version = parse_version(version)
    return version.format_zi()

def assert_xml_equals(actual, expected):
    '''
    actual : lxml.etree._Element or _ElementTree
    expected : str
    '''
    actual = etree.tostring(actual, pretty_print=True).decode()
    assert actual == expected
