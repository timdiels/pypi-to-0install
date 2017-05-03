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

from pypi_to_0install.various import (
    zi, zi_namespaces, canonical_name, PyPITimeout, kill, CalledProcessError
)
from ._version import parse_version, InvalidVersion
from ._various import (
    NoValidRelease, UnsupportedDistribution, InvalidDistribution, InvalidDownload
)
from ._general import convert_general
from ._sdist import convert_sdist
from ._specifiers import convert_specifiers, EmptyRangeConversion
from functools import partial, wraps
from pathlib import Path
from copy import deepcopy
import urllib.error
import asyncio
import xmlrpc

async def convert(context, package, old_feed):
    '''
    Convert PyPI package to ZI feed

    Parameters
    ----------
    context : FeedContext
    package : Package
    old_feed : lxml.etree.ElementTree

    Returns
    -------
    feed : lxml.etree.ElementTree
        ZI feed
    finished : bool
        True iff conversion finished. A conversion can be unfinished due to
        temporary errors (e.g. a failed download); these unfinished parts will
        be retried when called again. Conversion is not marked unfinished due to
        dropping invalid/unsupported parts of the PyPI package; those parts will
        not be retried.
    '''
    def blacklist(release_url):
        context.logger.warning('Blacklisting distribution, will not retry')
        package.blacklisted_distributions.add(release_url['url'])

    @_async_pypi(context)
    def release_data():
        with context.pool.pypi() as pypi:
            return pypi.release_data(package.name, max_version)

    @_async_pypi(context)
    def release_urls(py_version):
        with context.pool.pypi() as pypi:
            return pypi.release_urls(package.name, py_version)

    finished = True
    versions = await _versions(context, package)
    if not versions:
        raise NoValidRelease()

    # Create feed with general info based on the latest release_data of the
    # latest version
    py_versions = [pair[0] for pair in versions]
    max_version = max(py_versions, key=parse_version)
    release_data_ = await release_data()
    release_data_['version'] = max_version
    release_data_ = {k:v for k, v in release_data_.items() if v is not None and v != ''}
    feed = await convert_general(context, package.name, release_data_)

    # Add <implementation>s to feed
    for py_version, zi_version in versions:
        for release_url in await release_urls(py_version):
            if release_url['url'] in package.blacklisted_distributions:
                continue
            try:
                await _convert_distribution(context, feed, old_feed, release_data_, release_url, zi_version)
            except InvalidDownload as ex:
                finished = False
                context.logger.warning(
                    'Failed to download distribution. {}'
                    .format(ex.args[0])
                )
            except urllib.error.URLError as ex:
                finished = False
                context.logger.warning('Failed to download distribution. Cause: {}'.format(ex))
            except UnsupportedDistribution as ex:
                context.logger.warning('Unsupported distribution: {}'.format(ex.args[0]))
                blacklist(release_url)
            except InvalidDistribution as ex:
                context.logger.warning('Invalid distribution: {}'.format(ex.args[0]))
                blacklist(release_url)

    # If no implementations, and we converted all we could, raise it has no release
    if finished and feed.find('{{{}}}implementation'.format(zi_namespaces[None])) is None:
        raise NoValidRelease()

    return feed, finished

async def _convert_distribution(context, feed, old_feed, release_data, release_url, zi_version):
    '''
    Convert distribution to <implementation> and add it to feed
    '''
    # Add from old_feed if it already has it (distributions can be deleted, but not changed or reuploaded)
    implementations = old_feed.xpath('//implementation[@id={!r}]'.format(release_url['path']))
    if implementations:  # TODO test this, e.g. do we have to add xpath(namespaces=nsmap)?
        context.logger.info('Reusing from old feed')
        feed.append(implementations[0])
        return

    # Add from scratch
    _ensure_supported_release_size(release_url)
    package_type = release_url['packagetype']
    if package_type == 'sdist':
        context.logger.info('Converting {} distribution: {}'.format(package_type, release_url['filename']))
        implementation = await convert_sdist(context, zi_version, release_data, release_url)
    else:
        raise UnsupportedDistribution(
            'Unsupported package type: {!r} for release: {}'
            .format(package_type, release_url['filename'])
        )
    feed.getroot().append(implementation)

async def _versions(context, package):
    '''
    Get versions of package

    Returns
    -------
    [(py_version :: str, zi_version :: str)]
    '''
    @_async_pypi(context)
    def package_releases():
        show_hidden = True
        with context.pool.pypi() as pypi:
            return pypi.package_releases(package.name, show_hidden)
    py_versions = await package_releases()  # returns [str]
    versions = []
    for py_version in py_versions:
        if py_version in package.blacklisted_versions:
            continue
        try:
            zi_version = parse_version(py_version).format_zi()
            versions.append((py_version, zi_version))
        except InvalidVersion as ex:
            context.logger.warning(
                'Blacklisting version {!r}, will not retry. Reason: {}'
                .format(py_version, ex.args[0])
            )
            package.blacklisted_versions.add(py_version)
    return versions

def _ensure_supported_release_size(release_url):
    '''
    Ensure release is not too large
    '''
    # Get size
    try:
        size = int(release_url['size'])
    except KeyError:
        raise InvalidDistribution('release_url["size"] is missing')
    except ValueError:
        raise InvalidDistribution('Invalid release_url["size"]: {!r}'.format(size))

    # Unsupported if larger than 50MB
    if size > 50 * 2**20:  # assume size is bytes
        raise UnsupportedDistribution('Distribution is too large (>50M): {} MB'.format(size / 2**20))

def _async_pypi(context):
    '''
    Make pypi xmlrpc request async and retry on failure

    When call times out, it retries after a delay. Upon the 5th failure,
    PyPITimeout is raised.
    '''
    def decorator(call):
        @wraps(call)
        async def decorated(*args):
            for _ in range(5):
                try:
                    return await asyncio.get_event_loop().run_in_executor(None, call, *args)
                except xmlrpc.client.Fault as ex:
                    if 'timeout' in str(ex).lower():
                        context.logger.warning(
                            'PyPI request timed out, this worker will back off for 5 minutes. '
                            'We may be throttled, consider using less workers to put less load on PyPI'
                        )
                        await asyncio.sleep(5 * 60)
            raise PyPITimeout('5 consecutive PyPI requests (on this worker) timed out with 5 minutes between each request')
        return decorated
    return decorator
