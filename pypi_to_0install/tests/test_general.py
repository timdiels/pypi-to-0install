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
Test pypi_to_0install.convert._general.convert_general
'''

from pypi_to_0install.convert._general import convert_general
from textwrap import dedent
from lxml import etree  # @UnresolvedImport
import logging
import pytest
import attr

feed_logger_name = __name__ + ':feed_logger'

@attr.s()
class FeedContext(object):

    logger = attr.ib()
    zi_name = attr.ib()

    def feed_uri(self, zi_name):
        return 'http://feeds.example.com/' + zi_name

# Bogus PyPI XMLRPC values that should be handled robustly
bogus_pypi_values = (None, '')

@pytest.fixture
def context(zi_name):
    feed_logger = logging.getLogger(feed_logger_name)
    feed_logger.setLevel(logging.DEBUG)
    return FeedContext(feed_logger, zi_name)

@pytest.fixture
def pypi_name():
    return 'Pkg-Name'

@pytest.fixture
def zi_name():
    return 'pkg_name'

@pytest.fixture
def release_data():
    return {
        'summary': 'The summary',
        'description': 'Description\n===========\nText',
        'home_page': 'http://example.com',
        'classifiers': ['Framework :: Bob', 'Framework :: Chandler'],
    }

def assert_feed_equals(actual, expected):
    '''
    actual : lxml.etree._ElementTree
    expected : str
    '''
    actual = etree.tostring(actual, pretty_print=True).decode()
    assert actual == expected

@pytest.mark.asyncio
async def test_happy_days(context, pypi_name, release_data):
    '''
    When all valid input, output expected xml
    '''
    feed = await convert_general(context, pypi_name, release_data)
    assert_feed_equals(feed, dedent('''\
        <interface xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" uri="http://feeds.example.com/pkg_name" min-injector-version="0.48">
          <name>pkg_name</name>
          <summary>The summary</summary>
          <homepage>http://example.com</homepage>
          <description>
        
        DESCRIPTION
        
        
        Text
        </description>
        </interface>
        '''
    ))

def invalidate_release_data(release_data, attribute, missing, invalid_value):
    if missing:
        del release_data[attribute]
    else:
        release_data[attribute] = invalid_value
        
@pytest.mark.parametrize('missing, invalid_value',
    [(True, None)] +
    [(False, value) for value in bogus_pypi_values]
)
class TestInvalidAttribute(object):

    @pytest.mark.asyncio
    async def test_invalid_summary(self, context, pypi_name, release_data, missing, invalid_value):
        '''
        When invalid summary, fill in a default
        '''
        invalidate_release_data(release_data, 'summary', missing, invalid_value)
        feed = await convert_general(context, pypi_name, release_data)
        assert_feed_equals(feed, dedent('''\
            <interface xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" uri="http://feeds.example.com/pkg_name" min-injector-version="0.48">
              <name>pkg_name</name>
              <summary>Converted from PyPI; missing summary</summary>
              <homepage>http://example.com</homepage>
              <description>
            
            DESCRIPTION
            
            
            Text
            </description>
            </interface>
        '''
        ))

    @pytest.mark.asyncio
    async def test_invalid_homepage(self, context, pypi_name, release_data, missing, invalid_value):
        '''
        When invalid summary, fill in a default
        '''
        invalidate_release_data(release_data, 'home_page', missing, invalid_value)
        feed = await convert_general(context, pypi_name, release_data)
        assert_feed_equals(feed, dedent('''\
            <interface xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" uri="http://feeds.example.com/pkg_name" min-injector-version="0.48">
              <name>pkg_name</name>
              <summary>The summary</summary>
              <description>
            
            DESCRIPTION
            
            
            Text
            </description>
            </interface>
            '''
        ))

    @pytest.mark.asyncio
    async def test_invalid_description(self, context, pypi_name, release_data, missing, invalid_value):
        '''
        When invalid summary, fill in a default
        '''
        invalidate_release_data(release_data, 'description', missing, invalid_value)
        feed = await convert_general(context, pypi_name, release_data)
        assert_feed_equals(feed, dedent('''\
            <interface xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" uri="http://feeds.example.com/pkg_name" min-injector-version="0.48">
              <name>pkg_name</name>
              <summary>The summary</summary>
              <homepage>http://example.com</homepage>
            </interface>
            '''
        ))

@pytest.mark.asyncio
@pytest.mark.parametrize('missing, invalid_value',
    [(True, None)] +
    [(False, value) for value in bogus_pypi_values] +
    [(False, [value]) for value in bogus_pypi_values]
)
async def test_invalid_classifiers(context, pypi_name, release_data, missing, invalid_value):
    '''
    When invalid summary, fill in a default
    '''
    invalidate_release_data(release_data, 'classifiers', missing, invalid_value)
    feed = await convert_general(context, pypi_name, release_data)
    assert_feed_equals(feed, dedent('''\
        <interface xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" uri="http://feeds.example.com/pkg_name" min-injector-version="0.48">
          <name>pkg_name</name>
          <summary>The summary</summary>
          <homepage>http://example.com</homepage>
          <description>
        
        DESCRIPTION
        
        
        Text
        </description>
        </interface>
        '''
    ))

@pytest.mark.asyncio
async def test_terminal(context, pypi_name, release_data):
    '''
    When has 'Environment :: Console', feed gets <needs-terminal/>
    '''
    release_data['classifiers'].append('Environment :: Console')
    feed = await convert_general(context, pypi_name, release_data)
    assert_feed_equals(feed, dedent('''\
        <interface xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" uri="http://feeds.example.com/pkg_name" min-injector-version="0.48">
          <name>pkg_name</name>
          <summary>The summary</summary>
          <homepage>http://example.com</homepage>
          <description>
        
        DESCRIPTION
        
        
        Text
        </description>
          <needs-terminal/>
        </interface>
        '''
    ))
