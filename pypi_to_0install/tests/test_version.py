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
Test pypi_to_0install.convert._version
'''

import pytest
import numpy as np
from packaging.version import parse as py_parse_version
from zeroinstall.injector.versions import parse_version as zi_parse_version
from pypi_to_0install.convert._version import convert_version, after_version, InvalidVersion, parse_version
from chicken_turtle_util import iterable

def test_convert():
    '''
    convert_version converts according to spec
    '''
    assert convert_version('1!1') == '1-1-4'  # trivial case
    assert convert_version('1!1.0') == '1-1-4' # trim zeros of release segment
    assert convert_version('0.0') == '0-0-4'  # if release is all zeros, trim all but one zeros
    assert convert_version('0.1') == '0-0.1-4'  # release segment with multiple parts after trimming
    assert convert_version('1.dev') == '0-1-0.0-4'  # dev priority is 0
    assert convert_version('1.a') == '0-1-1.0-4'  # alpha priority
    assert convert_version('1.b') == '0-1-2.0-4'  # beta priority
    assert convert_version('1.rc') == '0-1-3.0-4'  # rc priority
    assert convert_version('1.post') == '0-1-5.0-4'  # post priority
    assert convert_version('1.a2.post3.dev4') == '0-1-1.2-5.3-0.4'  # modifier numbers are used
    assert convert_version('1.b2') == '0-1-2.2-4'  # beta number
    assert convert_version('1.rc2') == '0-1-3.2-4'  # rc number
    
    # append -4 when less than 3 components
    assert convert_version('1') == '0-1-4'
    assert convert_version('1.a') == '0-1-1.0-4'
    assert convert_version('1.a.post') == '0-1-1.0-5.0-4'
    
def test_ordering(versions):
    '''
    convert_version does not change version ordering
    '''
    versions = sorted(versions)
    
    # Python ordering
    py_versions = list(map(py_parse_version, versions))
    py_sort_indices = sorted(range(len(versions)), key=py_versions.__getitem__)
    
    # ZI ordering
    converted_versions = list(map(convert_version, versions))
    zi_versions = list(map(zi_parse_version, converted_versions))
    zi_sort_indices = sorted(range(len(versions)), key=zi_versions.__getitem__)
    
    # Assert
    print(np.array(versions)[py_sort_indices[:10]])
    print(np.array(versions)[zi_sort_indices[:10]])
    print(np.array(converted_versions)[py_sort_indices[:10]])
    print(np.array(converted_versions)[zi_sort_indices[:10]])
    np.testing.assert_array_equal(py_sort_indices, zi_sort_indices)
    
def test_after_version(versions):
    '''
    version..!after_version does not contain any other version
    
    This test checks that after_version appears directly after its given version
    when all versions are sorted.
    '''
    # Convert and sort versions
    converted_versions = list(map(convert_version, versions))
    converted_versions = sorted(converted_versions, key=zi_parse_version)
    
    # Insert the after_version directly after each version
    versions_ = ((version, after_version(version)) for version in converted_versions)
    versions_ = [version for versions in versions_ for version in versions]
    
    # Assert versions are still sorted after inserting the after versions
    indices = list(range(len(versions_)))
    sorted_indices = sorted(indices, key=lambda i: zi_parse_version(versions_[i]))
    assert sorted_indices == indices
    
def test_local_version():
    '''
    When local version given to parse_version (or convert_version), raise
    '''
    with pytest.raises(InvalidVersion) as ex:
        parse_version('1+local')
    assert ex.value.args[0] == "Got: '1+foobar'. Should be valid (public) PEP440 version"
    
#TODO check whether above tests are fairly complete
#TODO test response to various invalid versions