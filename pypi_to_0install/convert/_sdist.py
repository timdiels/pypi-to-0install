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

from pypi_to_0install.various import zi, zi_namespaces
from ._various import (
    InvalidDistribution, UnsupportedDistribution, InvalidDownload,
    languages, stability, digest_of, license
)
from ._dependencies import convert_dependencies
from chicken_turtle_util import path as path_  # @UnresolvedImport
from asyncio_extras.contextmanager import async_contextmanager
from pkg_resources import resource_filename, resource_string  # @UnresolvedImport
from tempfile import NamedTemporaryFile
from patoolib import extract_archive
from contextlib import suppress
from urllib.request import urlretrieve
from functools import partial
from pathlib import Path
from copy import deepcopy
import subprocess
import patoolib
import pkginfo
import hashlib
import asyncio
import shutil

_setup_py_profile_file = Path(resource_filename(__name__, 'setup_py_firejail.profile')).absolute()
_setup_py_firejail_sh = Path(resource_filename(__name__, 'setup_py_firejail.sh')).absolute()

async def convert_sdist(context, zi_version, feed, old_feed, release_data, release_url):
    '''
    Append <implementation> to feed, converted from distribution
    '''
    async with _unpack_distribution(context, release_url) as unpack_directory:
        distribution_directory = _find_distribution_directory(unpack_directory)
        context.logger.debug('Generating <implementation>')

        # Get egg info and convert dependencies to ZI requirements
        async with _find_egg_info(context, distribution_directory) as egg_info_directory:
            try:
                package = pkginfo.UnpackedSDist(str(egg_info_directory))
            except ValueError as ex:
                raise InvalidDistribution("Invalid egg-info: " + ex.args[0]) from ex
            requirements = convert_dependencies(context, egg_info_directory)

        # Create <implementation>
        implementation_attributes = dict(
            id=release_url['path'],
            arch='*-src',
            version=zi_version,
            released=release_url['upload_time'].strftime('%Y-%m-%d'),
            stability=stability(release_data['version']),
            langs=' '.join(
                languages[classifier]
                for classifier in package.classifiers
                if classifier in languages
            ),
        )

        license_ = license(package.classifiers)
        if license_:
            implementation_attributes['license'] = license_

        source_implementation_attributes = implementation_attributes.copy()
        del source_implementation_attributes['id']

        try:
            digest = digest_of(unpack_directory)
        except PermissionError:
            raise InvalidDistribution('Distribution contains files/directories without read permission')
        except UnicodeEncodeError as ex:
            raise UnsupportedDistribution(
                'Distribution triggers error in (old) 0install digest algorithm: ' + ex.args[0]
            )

        implementation = zi.implementation(
            implementation_attributes,
            zi('manifest-digest',
                sha256new=digest
            ),
            zi.archive(
                href=release_url['url'],
                size=str(release_url['size'])
            ),
            zi.command(
                dict(name='compile'),
                zi.runner(
                    interface=context.script_uri('convert_sdist')
                ),
                zi('{{{}}}implementation'.format(zi_namespaces['compile']),
                    source_implementation_attributes,
                    zi.environment(name='PYTHONPATH', insert='$DISTDIR/lib'),
                    zi.environment(name='PATH', insert='$DISTDIR/scripts'),
                    zi.environment(name='PYTHONDONTWRITEBYTECODE', value='true', mode='replace'),
                    *deepcopy(requirements)
                ),
            ),
            *requirements
        )

        # Add implementation to feed
        feed.getroot().append(implementation)

def _find_distribution_directory(unpack_directory):
    '''
    Find directory with setup.py
    '''
    children = list(unpack_directory.iterdir())
    if len(children) == 1:
        distribution_directory = children[0]
        try:
            if (distribution_directory / 'setup.py').exists():
                return distribution_directory
            else:
                raise InvalidDistribution('Could not find setup.py')
        except PermissionError:
            raise InvalidDistribution('No read permission on setup.py')
    elif children:
        raise InvalidDistribution('sdist is a tar bomb')
    else:
        raise InvalidDistribution('sdist is empty')

@async_contextmanager
async def _find_egg_info(context, distribution_directory):
    '''
    Get *.egg-info directory

    Generate it if it's missing

    Parameters
    ----------
    context : FeedContext
    unpack_directory : Path
        Directory in which distribution was unpacked.
    distribution_directory : Path
        Directory with setup.py of the distribution. This parent directory
        should have a disk quota to guard against a malicious setup.py. Files
        and directories may be created in this directory, or as siblings to this
        directory.

    Yields
    ------
    Path
        The egg-info directory
    '''
    def is_valid(egg_info_directory):
        return (egg_info_directory / 'PKG-INFO').exists()

    def try_find_egg_info():
        egg_info_directories = tuple(distribution_directory.glob('*.egg-info'))
        if len(egg_info_directories) == 1:
            egg_info_directory = egg_info_directories[0]
            if is_valid(egg_info_directory):
                return egg_info_directory
        return None

    @async_contextmanager
    async def generate_egg_info():
        # Prepare output_directory
        with NamedTemporaryFile(dir=str(distribution_directory), delete=False) as f:
            setup_file = f.name
            f.write(resource_string(__name__, 'setuptools_setup.py'))
        output_directory = distribution_directory.with_name(distribution_directory.name + '.out')
        output_directory.mkdir()
        distribution_directory.with_name(distribution_directory.name + '.tmp').mkdir()

        # Run setup.py egg_info in sandbox, in mem limiting cgroup, with disk
        # quota and 10 sec time limit
        for python in ('python2', 'python3'):
            async with context.pool.cgroups() as cgroups:
                tasks_files = [cgroup / 'tasks' for cgroup in cgroups]
                with suppress(StopIteration, asyncio.TimeoutError):
                    # Create egg info with setup.py
                    args = map(str,
                        [
                            'sh', _setup_py_firejail_sh,
                            distribution_directory, _setup_py_profile_file,
                            python, setup_file
                        ] +
                        tasks_files
                    )
                    process = await asyncio.create_subprocess_exec(
                        *args,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    try:
                        await asyncio.wait_for(process.wait(), timeout=10)
                    except:
                        # Note: when exiting cgroups, it will kill and wait
                        # for any processes still using the cgroup
                        with suppress(ProcessLookupError):
                            process.terminate()
                        raise

                    # Find egg-info
                    egg_info_directory = next(output_directory.iterdir())
                    if is_valid(egg_info_directory):
                        yield egg_info_directory
                        return
            raise InvalidDistribution(
                'No valid *.egg-info directory and setup.py egg_info failed or timed out'
            )

    egg_info_directory = try_find_egg_info()
    if egg_info_directory:
        yield egg_info_directory
    else:
        async with generate_egg_info() as egg_info_directory:
            yield egg_info_directory

@async_contextmanager
async def _unpack_distribution(context, release_url):
    '''
    Download and unpack sdist
    '''
    # Get url
    if context.pypi_mirror:
        url = '{}packages/{}'.format(context.pypi_mirror, release_url['path'])
    else:
        url = release_url['url']

    with NamedTemporaryFile() as f:
        # Download
        context.logger.debug('Downloading {}'.format(url))
        distribution_file = Path(f.name)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, urlretrieve, url, str(distribution_file))

        # Check md5 hash
        expected_digest = release_url['md5_digest']
        if expected_digest:
            # Generate digest
            actual_digest = path_.hash(distribution_file, hashlib.md5).hexdigest()

            # If digest differs, raise
            if actual_digest != expected_digest:
                raise InvalidDownload(
                    'MD5 digest differs. Got {!r}, expected {!r}'
                    .format(actual_digest, expected_digest)
                )

        # Unpack
        with context.pool.quota_directory() as temporary_directory:
            temporary_directory = Path(temporary_directory)

            context.logger.debug('Unpacking')
            try:
                unpack_directory = Path(
                    await loop.run_in_executor(
                        None,
                        partial(
                            extract_archive,
                            str(distribution_file),
                            outdir=str(temporary_directory),
                            interactive=False,
                            verbosity=-1
                        )
                    )
                )
            except patoolib.util.PatoolError as ex:
                if 'unknown archive' in ex.args[0]:
                    raise InvalidDistribution('Invalid archive or unknown archive format') from ex
                else:
                    # Discern between disk full and unknown error
                    usage = shutil.disk_usage(str(temporary_directory))
                    is_full = usage.free < 5 * 2**20  # i.e. iff less than 5MB free
                    if is_full:
                        raise UnsupportedDistribution(
                            'Unpacked distribution exceeds disk quota of {}MB'
                            .format(round(usage.total / 2**20))
                        )
                    else:
                        raise InvalidDistribution(
                            'Cannot unpack distribution: {}'.format(ex)
                        ) from ex

            # Yield
            yield unpack_directory
