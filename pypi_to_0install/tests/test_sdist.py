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
Test pypi_to_0install.convert._sdist
'''

from .common import assert_xml_equals, convert_version
from pypi_to_0install.convert._sdist import convert_sdist
from pkg_resources import resource_string  # @UnresolvedImport
from pypi_to_0install.various import zi
from textwrap import dedent
from datetime import datetime
import logging
import pytest
import attr

feed_logger_name = __name__ + ':feed_logger'

@attr.s()
class FeedContext(object):
    logger = attr.ib()
    pool = attr.ib()
    pypi_mirror = None

    def script_uri(self, name):
        return 'http://example.com/{}.xml'.format(name)

@pytest.fixture
def context(pool):
    feed_logger = logging.getLogger(feed_logger_name)
    feed_logger.setLevel(logging.DEBUG)
    return FeedContext(feed_logger, pool)

@pytest.mark.asyncio
async def test_happy_days(context, mocker, httpserver):
    '''
    When valid fairly minimal sdist with egg-info dir, output expected xml
    '''
    async with context.pool:
        def convert_dependencies_(*args):
            return [zi.requires(), zi.requires()]
        mocker.patch('pypi_to_0install.convert._sdist.convert_dependencies', convert_dependencies_)

        release_data = {
            'classifiers': [
                'Natural Language :: Latvian',
                'Natural Language :: Macedonian',
                'License :: Freeware',
            ],
            'version': '1',
        }

        httpserver.serve_content(resource_string(__name__, 'data/test_sdist.tgz'))
        release_url = {
            'url': httpserver.url,
            'size': 1000,
            'path': 'archive.tgz',
            'md5_digest': '1fae18f2f0fab6041881ed4849042645',
            'upload_time': datetime(2000, 2, 3, 12, 30, 30),  # 2000-02-03 12:30:30
        }

        zi_version = convert_version("1")
        implementation = await convert_sdist(context, zi_version, release_data, release_url)
        assert_xml_equals(implementation, dedent('''\
            <implementation xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" id="archive.tgz" arch="*-src" version="{version}" released="2000-02-03" stability="stable" langs="lv mk" license="License :: Freeware">
              <manifest-digest sha256new="GRBCS6ZYID6BKJX6UPHVYWQIDKERVMFEHN4NPORGALVIDU2XWZFA"/>
              <archive href="{url}" size="1000"/>
              <command name="compile">
                <runner interface="http://example.com/convert_sdist.xml"/>
                <compile:implementation version="{version}" released="2000-02-03" stability="stable" langs="lv mk" license="License :: Freeware">
                  <environment name="PYTHONPATH" insert="$DISTDIR/lib"/>
                  <environment name="PATH" insert="$DISTDIR/scripts"/>
                  <environment name="PYTHONDONTWRITEBYTECODE" value="true" mode="replace"/>
                  <requires/>
                  <requires/>
                </compile:implementation>
              </command>
              <requires/>
              <requires/>
            </implementation>
            '''
            .format(version=zi_version, url=httpserver.url)
        ))

# TODO: test robustness to invalid inputs
