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
Test pypi_to_0install.convert._various
'''

from pypi_to_0install.convert._various import stability, license
import pytest

@pytest.mark.parametrize('version, expected', [
    ('1.dev', 'developer'),
    ('1.a', 'testing'),
    ('1.b', 'testing'),
    ('1.rc', 'testing'),
    ('1', 'stable'),
])
def test_stability(version, expected):
    '''
    <impl stability> is developer if Python version has a .dev segment. Else, if
    the version contains a prerelease segment (.a|b|rc), stability is testing.
    Otherwise, stability is stable.
    '''
    assert stability(version) == expected

@pytest.mark.parametrize('classifiers, expected', [
    ([], None),
    (['Natural Language :: Latvian'], None),
    (['License :: Freeware'], 'License :: Freeware'),
    (['License :: DFSG approved', 'License :: Freeware'], 'License :: DFSG approved'),
    (['License :: Freeware', 'License :: DFSG approved'], 'License :: DFSG approved'),  # deterministic through sorting
])
def test_license(classifiers, expected):
    '''
    Derive license Trove classifier. If License :: is in classifiers, it is
    used. If there are multiple, pick one in a deterministic fashion. Else, omit
    the license attribute.
    '''
    assert license(classifiers) == expected