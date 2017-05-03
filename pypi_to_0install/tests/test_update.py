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
Test pypi_to_0install.update
'''

from .common import convert_version
from pypi_to_0install.update import _update_feed, FeedContext
from pypi_to_0install.various import Package
from pypi_to_0install.pools import CombinedPool
from chicken_turtle_util.test import temp_dir_cwd
from pytest_localserver.http import WSGIServer
from pkg_resources import resource_string
from textwrap import dedent
from datetime import datetime
from pathlib import Path
import plumbum as pb
import logging
import pytest

@pytest.yield_fixture
def http_server(request):
    mime_types = {
        '.tgz': 'application/gzip',
        '.xml': 'text/xml',
    }
    def app(environ, start_response):
        path = environ['PATH_INFO']
        mime_type = mime_types[Path(path).suffix]
        if path == '/dependency.tgz':
            response = resource_string(__name__, 'data/test_sdist_integration/dependency.tgz')
        elif path == '/dependent.tgz':
            response = resource_string(__name__, 'data/test_sdist_integration/dependent.tgz')
        elif path == '/pypi_to_0install/convert_sdist.xml':
            response = Path('convert_sdist.xml').read_text()
        elif path == '/feeds/dependency.xml':
            response = Path('dependency.xml').read_text()
        elif path == '/feeds/dependent.xml':
            response = Path('dependent.xml').read_text()
        else:
            assert False, path
        start_response('200 OK', [('Content-type', mime_type)])
        return [response]
    server = WSGIServer(application=app)
    server.start()
    try:
        yield server
    finally:
        server.stop()

@pytest.mark.asyncio
async def test_sdist_integration(mocker, temp_dir_cwd, http_server):
    '''
    When valid sdist with a dependency, its resulting feed is usable and
    contains the relevant parts
    '''
    zi_version = convert_version("1")

    # Mock PyPI xmlrpc
    class ServerProxyMock(mocker.MagicMock):

        def package_releases(self, pypi_name, show_hidden):
            assert show_hidden
            assert pypi_name in ('Dependency', 'Dependent')
            return ['1']

        def release_data(self, pypi_name, version):
            assert version == '1'
            if pypi_name == 'Dependency':
                return {
                    'version': '1',
                }
            elif pypi_name == 'Dependent':
                return {
                    'version': '1',
                }
            else:
                assert False

        def release_urls(self, pypi_name, version):
            assert version == '1'
            release = {
                'size': 1000,  # bogus size, is fine with current implementation
                'upload_time': datetime(2000, 2, 3, 12, 30, 30),  # 2000-02-03 12:30:30
                'packagetype': 'sdist',
            }
            if pypi_name == 'Dependency':
                release.update({
                    'url': '{}/dependency.tgz'.format(http_server.url),
                    'path': 'dependency.tgz',
                    'filename': 'dependency.tgz',
                    'md5_digest': '789dbd59b78cbf46f2f20c8257812417',
                })
            elif pypi_name == 'Dependent':
                release.update({
                    'url': '{}/dependent.tgz'.format(http_server.url),
                    'path': 'dependent.tgz',
                    'filename': 'dependent.tgz',
                    'md5_digest': '0bbfbaa57d74b74ed1414c10cf87251d',
                })
            else:
                assert False
            return [release]

    pool = CombinedPool('http://example.com')
    pool._pypi_proxy_pool = mocker.MagicMock(get=ServerProxyMock)
    async with pool:
        context_args = dict(
            base_uri=http_server.url,
            pypi_mirror=None,
            pool=pool,
        )
        
        # Convert dependency
        context = FeedContext(
            logger=logging.getLogger(__name__ + ':dependency'),
            zi_name='dependency',
            feed_file=Path('dependency.xml').absolute(),
            **context_args
        )
        package = Package('Dependency')
        await _update_feed(context, package)

        actual = Path('dependency.xml').read_text()
        actual = '\n'.join(actual.splitlines()[:-8])
        assert actual == dedent('''\
            <?xml version="1.0" ?>
            <?xml-stylesheet type='text/xsl' href='interface.xsl'?>
            <interface min-injector-version="0.48" uri="{url}/feeds/dependency.xml" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile">
              <name>dependency</name>
              <summary>Converted from PyPI; missing summary</summary>
              <implementation arch="*-src" id="dependency.tgz" released="2000-02-03" stability="stable" version="{version}">
                <manifest-digest sha256new="VEQQBFVPUXQ4UAPPUOZPMPNU7H7IG4YRQS2GIYVT22N5RDCRBKNA"/>
                <archive href="{url}/dependency.tgz" size="1000"/>
                <command name="compile">
                  <runner interface="https://raw.githubusercontent.com/timdiels/pypi-to-0install/new/feeds/compile_sdist.xml"/>
                  <compile:implementation released="2000-02-03" stability="stable" version="{version}">
                    <environment insert="$DISTDIR/lib" name="PYTHONPATH"/>
                    <environment insert="$DISTDIR/scripts" name="PATH"/>
                    <environment mode="replace" name="PYTHONDONTWRITEBYTECODE" value="true"/>
                  </compile:implementation>
                </command>
              </implementation>
            </interface>
            <!-- Base64 Signature'''
            .format(version=zi_version, url=http_server.url)
        )

        # Convert dependent
        context = FeedContext(
            logger=logging.getLogger(__name__ + ':dependent'),
            zi_name='dependent',
            feed_file=Path('dependent.xml').absolute(),
            **context_args
        )
        package = Package('Dependent')
        await _update_feed(context, package)

        actual = Path('dependent.xml').read_text()
        actual = '\n'.join(actual.splitlines()[:-8])
        assert actual == dedent('''\
            <?xml version="1.0" ?>
            <?xml-stylesheet type='text/xsl' href='interface.xsl'?>
            <interface min-injector-version="0.48" uri="{url}/feeds/dependent.xml" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile">
              <name>dependent</name>
              <summary>Converted from PyPI; missing summary</summary>
              <implementation arch="*-src" id="dependent.tgz" released="2000-02-03" stability="stable" version="{version}">
                <manifest-digest sha256new="IQJZ2FGMXBGLQVXRMU4CUMY3ORIMQOSP3VLVUGB3DDBTY3GSIQDQ"/>
                <archive href="{url}/dependent.tgz" size="1000"/>
                <command name="compile">
                  <runner interface="https://raw.githubusercontent.com/timdiels/pypi-to-0install/new/feeds/compile_sdist.xml"/>
                  <compile:implementation released="2000-02-03" stability="stable" version="{version}">
                    <environment insert="$DISTDIR/lib" name="PYTHONPATH"/>
                    <environment insert="$DISTDIR/scripts" name="PATH"/>
                    <environment mode="replace" name="PYTHONDONTWRITEBYTECODE" value="true"/>
                    <requires importance="essential" interface="{url}/feeds/dependency.xml"/>
                  </compile:implementation>
                </command>
                <requires importance="essential" interface="{url}/feeds/dependency.xml"/>
              </implementation>
            </interface>
            <!-- Base64 Signature'''
            .format(version=zi_version, url=http_server.url)
        )

        # Run dependent
        Path('test.xml').write_text(dedent('''\
            <?xml version="1.0" ?>
            <?xml-stylesheet type='text/xsl' href='interface.xsl'?>
            <interface min-injector-version="0.48" xmlns="http://zero-install.sourceforge.net/2004/injector/interface" xmlns:compile="http://zero-install.sourceforge.net/2006/namespaces/0compile">
              <name>test</name>
              <summary>Test generated feeds</summary>
              <implementation id="." version="1">
                <command name="run">
                  <runner interface='http://repo.roscidus.com/python/python'>
                    <version after='3'/>
                    <arg>-c</arg>
                    <arg>import dependent; print(dependent.y)</arg>
                  </runner>
                </command>
                <requires importance="essential" interface="{url}/feeds/dependent.xml"/>
              </implementation>
            </interface>
            '''
            .format(url=http_server.url)
        ))
        pb.local['0launch']['test.xml'] & pb.FG()
        assert False

# TODO only tested a single case of sdist. Did not test persistence of state
# (blacklisted, completed; generally avoiding to redo things next run),
# exception handling, logging
