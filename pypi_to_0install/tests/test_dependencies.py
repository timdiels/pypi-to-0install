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
Test pypi_to_0install.convert._dependencies.convert_dependencies
'''

from pypi_to_0install.convert._dependencies import convert_dependencies
from pypi_to_0install.convert._various import UnsupportedDistribution
from pypi_to_0install.convert._specifiers import convert_specifiers
from chicken_turtle_util.test import temp_dir_cwd
from textwrap import dedent
from pathlib import Path
from lxml import etree  # @UnresolvedImport
import logging
import pytest
import attr

feed_logger_name = __name__ + ':feed_logger'
namespaces = (
    'xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" '
    'xmlns="http://zero-install.sourceforge.net/2004/injector/interface"'
)

@attr.s()
class FeedContext(object):

    logger = attr.ib()

    def feed_uri(self, zi_name):
        return 'http://feeds.example.com/' + zi_name

@pytest.fixture
def context():
    feed_logger = logging.getLogger(feed_logger_name)
    feed_logger.setLevel(logging.DEBUG)
    return FeedContext(feed_logger)

def assert_requirements_equal(actual, expected):
    '''
    actual : [ZI <requires>]
    expected : str
    '''
    actual = ''.join(sorted(
        etree.tostring(requirement, pretty_print=True).decode()
        for requirement in actual
    ))
    assert actual == expected

@pytest.mark.parametrize('requirements_file_name', ('requires.txt', 'depends.txt'))
def test_happy_days(context, temp_dir_cwd, requirements_file_name):
    '''
    Convert requirements in requires.txt or depends.txt to list of ZI
    <requires>
    '''
    egg_info_dir = Path.cwd()
    (egg_info_dir / requirements_file_name).write_text(dedent('''\
        req1<3.0,~=1.2
        
        [extra1]
        req2==3.0
        req3[extra]>1.1.1
        '''
    ))
    actual = convert_dependencies(context, egg_info_dir)
    assert_requirements_equal(actual, dedent('''\
        <requires {ns} interface="http://feeds.example.com/req1" importance="essential" version="{}"/>
        <requires {ns} interface="http://feeds.example.com/req2" importance="recommended" version="{}"/>
        <requires {ns} interface="http://feeds.example.com/req3" importance="recommended" version="{}"/>
        '''
        .format(
            convert_specifiers(context, [('<', '3.0'), ('~=', '1.2')]),
            convert_specifiers(context, [('==', '3.0')]),
            convert_specifiers(context, [('>', '1.1.1')]),
            ns=namespaces
        )
    ))

def test_both_files(context, temp_dir_cwd):
    '''
    When both requires.txt and depends.txt exist, raise unsupported
    '''
    Path('requires.txt').write_text('req1')
    Path('depends.txt').write_text('dep1')
    with pytest.raises(UnsupportedDistribution) as ex:
        convert_dependencies(context, Path.cwd())
    assert ex.value.args[0] == 'Egg info has both a requires.txt and depends.txt file'

def test_required_and_extra(context, temp_dir_cwd):
    '''
    When a requirement appears both as required and optional dependency, it is
    required and its specifiers are the intersection of both

    Note: this behaviour likely differs from pip and might cause trouble in
    esoteric cases.
    '''
    egg_info_dir = Path.cwd()
    (egg_info_dir / 'requires.txt').write_text(dedent('''\
        req1>2.0
        
        [extra1]
        req1<3.0
        '''
    ))
    actual = convert_dependencies(context, egg_info_dir)
    assert_requirements_equal(actual, dedent('''\
        <requires {ns} interface="http://feeds.example.com/req1" importance="essential" version="{}"/>
        '''
        .format(
            convert_specifiers(context, [('>', '2.0'), ('<', '3.0')]),
            ns=namespaces
        )
    ))

def test_empty(context, temp_dir_cwd):
    '''
    When no requirement files, return []
    '''
    assert convert_dependencies(context, Path.cwd()) == []
