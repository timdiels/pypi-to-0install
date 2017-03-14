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
Test pypi_to_0install.convert._specifiers.convert_specifiers
'''

import pytest
from packaging.specifiers import SpecifierSet
from pkg_resources import Requirement
from zeroinstall.injector.versions import parse_version_expression, parse_version as zi_parse_version 
from pypi_to_0install.convert._specifiers import convert_specifiers
from pypi_to_0install.convert._version import parse_version
from pypi_to_0install.main import Context
from .common import convert_version
import logging

feed_logger_name = __name__ + ':feed_logger'

@pytest.fixture
def context():
    feed_logger = logging.getLogger(feed_logger_name)
    feed_logger.setLevel(logging.DEBUG)
    return Context(None, None, None, feed_logger)

def convert_specifiers_(context, specifiers):
    return convert_specifiers(context, Requirement.parse('a{}'.format(specifiers)).specs)

_workarounds = {
    '~=1.1': '>=1.1, ==1.*',
    '~=1.1.a1.post1.dev1': '>=1.1.a1.post1.dev1, ==1.*',
    '~=1.1.b': '>=1.1.b, ==1.*',
    '~=1.1.rc1.post': '>=1.1.rc1.post, ==1.*',
    '~=1.0.dev1': '>=1.0.dev1, ==1.*',
}

def SpecifierSet_(specifiers, prereleases):
    # Workaround to https://github.com/pypa/packaging/issues/100
    specifiers_ = []
    for specifier in specifiers.split(','):
        if specifier.strip().startswith('~='):
            specifier = _workarounds[specifier]
        specifiers_.append(specifier)
    specifiers = ','.join(specifiers_)
    
    #
    return SpecifierSet(specifiers, prereleases)

@pytest.mark.parametrize('specifiers', (
    '>=1',
    '>=1.1',
    '>=1.1.a1.post1.dev1',
    '>=1.1.rc1.post',
    
    '>1',
    '>1.1',
    '>1.1.a1.post1.dev1',
    '>1.1.rc1.post',
    
    '<=1',
    '<=1.1',
    '<=1.1.a1.post1.dev1',
    '<=1.1.rc1.post',
    
    '<1',
    '<1.1',
    '<1.1.a1.post1.dev1',
    '<1.1.rc1.post',
    
    '==1',
    '==1.1',
    '==1.1.a1.post1.dev1',
    '==1.1.rc1.post',
    
    '==1.*',
    '==1.rc1.post1.*',
    '==1.1.*',
    '==1.1.a1.*',
    '==1.1.rc1.post1.*',
    
    '!=1',
    '!=1.1',
    '!=1.1.a1.post1.dev1',
    '!=1.1.rc1.post',
    
    '!=1.*',
    '!=1.rc1.post1.*',
    '!=1.1.*',
    '!=1.1.a1.*',
    '!=1.1.rc1.post1.*',
    
    # Note: while PEP440 requires sort of an exact match, we simply use == and
    # compare by normalised versions as usual. I.e. === isn't fully supported;
    # but it's intended for legacy versions, so we'll be fine
    '===1',
    '===1.1',
    '===1.1a1.post1.dev1',
    '===1.1rc1.post0',
    
    #
    '~=1.1',  # >=1.1, ==1.*
    '~=1.1.a1.post1.dev1',
    '~=1.1.b',
    '~=1.1.rc1.post',
    '~=1.0.dev1',  # >=1.dev1, ==1.*
    
    # combinations
    '==1.*,!=1.1.dev1,<1.2',
    '==1,===1',
    '~=1.1,==1.*,!=1.2.b1,>1,>=1.b1,<3,<=2.1'
))
def test_happy_days(context, versions, specifiers):
    '''
    Test convert_specifiers returns an equivalent constraint
    '''
    # Python constraint
    py_constraint = SpecifierSet_(specifiers, prereleases=True)
    
    # Converted ZI constraint
    zi_version_expression = convert_specifiers_(context, specifiers)
    zi_constraint = parse_version_expression(zi_version_expression)
    
    # Assert both constraints include/exclude the same versions
    for version in versions:
        zi_version = convert_version(version)
        actual = zi_constraint(zi_parse_version(zi_version))
        expected = version in py_constraint
        assert actual == expected, (
            '\n'
            '{} in {}\n'
            'vs\n'
            '{} in {}'
            .format(
                zi_version, zi_version_expression,
                version, specifiers
            )
        )
    
class TestInvalidInput(object):
    
    def assert_warns_on(self, specifier, warning, context, caplog):
        '''
        Assert convert_specifiers logs warning on given specifier, but continues
        with any other specifiers
        '''
        caplog_start = len(caplog.records())
        actual =  convert_specifiers(context, (specifier, ('==', '1')))
            
        # Assert a matching warning message was logged
        for record in caplog.records()[caplog_start:]:
            if record.name != feed_logger_name:
                continue
            if record.levelname != 'WARNING':
                continue
            if record.msg == "Ignoring invalid specifier: '{}{}'. {}".format(specifier[0], specifier[1], warning):
                break  # found a match
        else:
            assert False  # `warning` was not logged
            
        # Assert the other specifiers were still converted
        expected = convert_specifiers_(context, '==1')
        assert actual == expected
    
    def test_prefix_match_dev(self, context, caplog):
        '''
        When prefix match on dev version, warn and skip
        '''
        self.assert_warns_on(('==', '1.dev.*'), 'Prefix match must not end with .dev.*', context, caplog)
        
    @pytest.mark.parametrize('operator', ('>=', '>', '<=', '<', '===', '~='))
    def test_prefix_match_non_eq_ne_operator(self, context, caplog, operator):
        '''
        When is prefix match and operator is not == or !=, warn and skip
        '''
        self.assert_warns_on((operator, '1.*'), '{} does not allow prefix match suffix (.*)'.format(operator), context, caplog)
        
    def test_invalid_version(self, context, caplog):
        '''
        When invalid version, warn and skip
        '''
        self.assert_warns_on(('===', 'foobar'), "Invalid version: Got: 'foobar'. Should be valid (public) PEP440 version", context, caplog)
        
    def test_invalid_compatible(self, context, caplog):
        '''
        When invalid compatible release, warn and skip
        '''
        self.assert_warns_on(('~=', '1'), 'Compatible release clause requires multi-part release segment (e.g. ~=1.1)', context, caplog)
    
def test_all_invalid(context, caplog):
    '''
    When all specifiers invalid, return None
    '''
    actual = convert_specifiers_(context, '===foobar')
    assert actual is None
    
@pytest.mark.parametrize('specifiers, expected', (
    ('==1', convert_version('1')),
    ('!=1', '!{}'.format(convert_version('1'))),
    ('>1,>2,>3', '{}..'.format(convert_version('3.1.dev'))),
    ('>=1,>=2,>=3', '{}..'.format(convert_version('3'))),
    ('<1,<2,<3', '..!{}'.format(convert_version('1.dev'))),
    ('<=1,<=2,<=3', '..!{}'.format(parse_version('1').after_version().format_zi())),
    ('==1.*,==1.1.*', '{}..!{}'.format(  # ==1.1.*
        convert_version('1.1.dev'),
        convert_version('1.2.dev'),
    )),
    ('==1.*,~=1.1', '{}..!{}'.format(  # ~=1.1
        convert_version('1.1'),
        convert_version('2.dev'),
    )),
    ('>1,!=2.1,<=3', '{}..!{} | {}..!{}'.format(
        parse_version('1.1.dev').format_zi(),
        convert_version('2.1'),
        parse_version('2.1').after_version().format_zi(),
        parse_version('3').after_version().format_zi(),
    )),
    ('==1.*,!=1.1.dev1,<1.2', '{}..!{} | {}..!{}'.format(
        convert_version('1.dev'),
        convert_version('1.1.dev1'),
        parse_version('1.1.dev1').after_version().format_zi(),
        convert_version('1.2.dev'),
    )),
    ('==1,===1', convert_version('1')),
    ('~=1.1,==1.*,!=1.2.b1,>1,>=1.b1,<3,<=2.1', '{}..!{} | {}..!{}'.format(  # ~=1.1,!=1.2.b1
        convert_version('1.1'),
        convert_version('1.2.b1'),
        parse_version('1.2.b1').after_version().format_zi(),
        convert_version('2.dev'),
    )),
))
def test_simplified(context, specifiers, expected):
    '''
    Test converted specifiers are simplified
    '''
    assert convert_specifiers_(context, specifiers) == expected
