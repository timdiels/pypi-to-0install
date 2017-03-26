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

from copy import deepcopy
from lxml import etree
from pathlib import Path
from contextlib import contextmanager, suppress
import contextlib
import attr
import pypandoc
from patoolib import extract_archive
import patoolib
from tempfile import TemporaryDirectory, NamedTemporaryFile
from urllib.request import urlretrieve
import urllib.error
import pkginfo
from pypi_to_0install.various import zi, zi_namespaces, canonical_name
from ._version import parse_version, InvalidVersion
from ._specifiers import convert_specifiers
import logging
from collections import defaultdict
import pkg_resources
from zeroinstall.zerostore import manifest
import hashlib
from chicken_turtle_util import path as path_
import plumbum as pb
import xmlrpc
import time

logger = logging.getLogger(__name__)

def convert(context, package, zi_name, old_feed):
    '''
    Convert PyPI package to ZI feed
    
    Parameters
    ----------
    context : Context
    package : Package
    zi_name : str
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
        context.feed_logger.warning('Blacklisting distribution, will not retry')
        package.blacklisted_distributions.add(release_url['url'])
        
    finished = True
    versions = _versions(context, package)
    if not versions:
        raise NoValidRelease()
    
    # Create feed with general info based on the latest release_data of the
    # latest version
    py_versions = [pair[0] for pair in versions]
    max_version = max(py_versions, key=parse_version)
    release_data = _retry_pypi(context, lambda: context.pypi.release_data(package.name, max_version))
    release_data['version'] = max_version
    release_data = {k:v for k, v in release_data.items() if v is not None and v != ''}
    feed = _convert_general(context, package.name, zi_name, release_data)
    
    # Add <implementation>s to feed
    for py_version, zi_version in versions:
        for release_url in _retry_pypi(context, lambda: context.pypi.release_urls(package.name, py_version)):
            if release_url['url'] in package.blacklisted_distributions:
                continue
            try:
                package_type = release_url['packagetype']
                action = 'Converting' if package_type == 'sdist' else 'Skipping' 
                context.feed_logger.info('{} {} distribution: {}'.format(action, package_type, release_url['filename']))
                if action == 'Converting':
                    _convert_distribution(context, zi_version, feed, old_feed, release_data, release_url)
            except _InvalidDownload as ex:  # e.g. md5sum differs
                finished = False
                context.feed_logger.warning(
                    'Failed to download distribution. {}'
                    .format(ex.args[0])
                )
            except urllib.error.URLError as ex:
                finished = False
                context.feed_logger.warning('Failed to download distribution. Cause: {}'.format(ex))
            except _InvalidDistribution as ex:
                context.feed_logger.warning('Invalid distribution: {}'.format(ex.args[0]))
                blacklist(release_url)
                
    # If no implementations, and we converted all we could, raise it has no release
    if finished and feed.find('{{{}}}implementation'.format(zi_namespaces[None])) is None:
        raise NoValidRelease()
    
    return feed, finished

def _retry_pypi(context, call):
    '''
    Make pypi xmlrpc request, backoff if it times out, then retry until it succeeds
    '''
    for _ in range(5):
        try:
            return call()
        except xmlrpc.client.Fault as ex:
            if 'timeout' in str(ex).lower():
                context.feed_logger.warning(
                    'PyPI request timed out, this worker will back off for 5 minutes. '
                    'We may be throttled, consider using less workers to put less load on PyPI'
                )
                logger.exception(ex) #TODO
                time.sleep(5*60)
    raise PyPITimeout('5 consecutive PyPI requests (on this worker) timed out with 5 minutes between each request')

class PyPITimeout(Exception):
    pass

class NoValidRelease(Exception):
    '''
    When a package has not a single valid release
    '''
    
class _InvalidDistribution(Exception):
    pass

def _versions(context, package):
    '''
    Get versions of package
    
    Returns
    -------
    [(py_version :: str, zi_version :: str)]
    '''
    show_hidden = True
    py_versions = context.pypi.package_releases(package.name, show_hidden)  # returns [str]
    versions = []
    for py_version in py_versions:
        if py_version in package.blacklisted_versions:
            continue
        try:
            zi_version = parse_version(py_version).format_zi()
            versions.append((py_version, zi_version))
        except InvalidVersion as ex:
            context.feed_logger.warning(
                'Blacklisting version {!r}, will not retry. Reason: {}'
                .format(py_version, ex.args[0])
            )
            package.blacklisted_versions.add(py_version)
    return versions
    
def _convert_general(context, pypi_name, zi_name, release_data):
    '''
    Populate feed with general info from latest release_data
    '''
    interface = zi.interface(**{
        'uri': context.feed_uri(zi_name),
        'min-injector-version': '0.48', #TODO check what we use, set accordingly
    })
    interface.append(zi.name(zi_name))
    
    # Note: .get() or 'x' is not the same as .get(, 'x') when value can be '' 
    summary = release_data.get('summary', 'Converted from PyPI; missing summary')
    interface.append(zi.summary(summary))  # Note: required element
        
    homepage = release_data.get('home_page')
    if homepage:
        interface.append(zi.homepage(homepage))
        
    description = release_data.get('description')
    if description:
        description = pypandoc.convert_text(description, format='rst', to='plain')
        interface.append(zi.description(description))
        
    #TODO: <category>s from classifiers
    
    classifiers = release_data.get('classifiers', [])
    if 'Environment :: Console' in classifiers:  #TODO test
        interface.append(zi('needs-terminal'))
        
    return etree.ElementTree(interface)

def _convert_distribution(context, zi_version, feed, old_feed, release_data, release_url):
    '''
    Append <implementation> to feed, converted from distribution
    '''
    # Add from old_feed if it already has it (distributions can be deleted, but not changed or reuploaded)
    implementations = old_feed.xpath('//implementation[@id={!r}]'.format(release_url['path']))
    if implementations: #TODO test this, e.g. doe we have to add xpath(namespaces=nsmap)?
        context.feed_logger.info('Reusing from old feed')
        feed.append(implementations[0])
        return
    
    # Not in old feed, need to convert.
    with _unpack_distribution(context, release_url) as unpack_directory:
        distribution_directory = _find_distribution_directory(unpack_directory)
        context.feed_logger.debug('Generating <implementation>')
        
        with TemporaryDirectory() as temporary_directory:
            egg_info_directory = _find_egg_info(distribution_directory, Path(temporary_directory))
            package = pkginfo.UnpackedSDist(str(egg_info_directory))
            requirements = _convert_dependencies(context, egg_info_directory)
        
        implementation_attributes = dict(
            id=release_url['path'],
            arch='*-src',
            version=zi_version,
            released=release_url['upload_time'].strftime('%Y-%m-%d'),
            stability=_stability(release_data['version']),
            langs=' '.join(
                _languages[classifier]
                for classifier in package.classifiers
                if classifier in _languages
            ),
        )
        
        source_implementation_attributes = implementation_attributes.copy()
        del source_implementation_attributes['id']
        
        implementation = zi.implementation(
            implementation_attributes,
            zi('manifest-digest',
                sha256new=_digest_of(unpack_directory)
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
        
        licenses = sorted(classifier for classifier in package.classifiers if classifier.startswith('License ::'))
        if licenses:
            implementation.set('license', licenses[0])
        
        # Add to feed
        feed.getroot().append(implementation)
        
def _find_distribution_directory(unpack_directory):
    '''
    Find the directory with setup.py
    '''
    if (unpack_directory / 'setup.py').exists():
        return unpack_directory  # tar bomb
    else:
        distribution_directory = next(unpack_directory.iterdir())
        if (distribution_directory / 'setup.py').exists():
            return distribution_directory
    raise _InvalidDistribution('Could not find setup.py')
        
def _find_egg_info(distribution_directory, output_directory):
    '''
    Get *.egg-info directory
    
    Parameters
    ----------
    distribution_directory : Path
        Directory with setup.py of the distribution
    output_directory : Path
        Directory to generate egg-info in if it is missing
        
    Returns
    -------
    Path
        The egg-info directory
    '''
    def is_valid(egg_info_directory):
        return (egg_info_directory / 'PKG-INFO').exists()
    
    # Try to find egg-info
    egg_info_directories = tuple(distribution_directory.glob('*.egg-info'))
    if len(egg_info_directories) == 1:
        egg_info_directory = egg_info_directories[0]
        if is_valid(egg_info_directory):
            return egg_info_directory
    
    # Try to generate egg-info
    for python in ('python2', 'python3'):
        with suppress(pb.ProcessExecutionError, StopIteration):
            with pb.local.cwd(str(distribution_directory)):
                pb.local[python]('setup.py', 'egg_info', '--egg-base', str(output_directory), timeout=10)
                egg_info_directory = next(output_directory.iterdir())
                if is_valid(egg_info_directory):
                    return egg_info_directory
    
    # Failed to get valid egg-info
    raise _InvalidDistribution('No valid *.egg-info directory and setup.py egg_info failed or timed out')
    
def _stability(pypi_version):
    version = parse_version(pypi_version)
    if version.modifiers and version.modifiers[-1].type_ == 'dev':
        return 'developer'
    elif version.is_prerelease:
        return 'testing'
    else:
        return 'stable'
        
class _InvalidDownload(Exception):
    pass

@contextmanager
def _unpack_distribution(context, release_url):
    # Get url
    if context.pypi_mirror:
        url = '{}packages/{}'.format(context.pypi_mirror, release_url['path'])
    else:
        url = release_url['url']
    
    with NamedTemporaryFile() as f:
        # Download
        context.feed_logger.debug('Downloading {}'.format(url))
        distribution_file = Path(f.name)
        urlretrieve(url, str(distribution_file))
    
        # Check md5 hash
        expected_digest = release_url['md5_digest']
        if expected_digest:
            # Generate digest
            actual_digest = path_.hash(distribution_file, hashlib.md5).hexdigest()
            
            # If digest differs, raise
            if actual_digest != expected_digest:
                raise _InvalidDownload(
                    'MD5 digest differs. Got {!r}, expected {!r}'
                    .format(actual_digest, expected_digest)
                )
        
        # Unpack
        with TemporaryDirectory() as temporary_directory:
            temporary_directory = Path(temporary_directory)
            
            context.feed_logger.debug('Unpacking')
            try:
                unpack_directory = Path(extract_archive(str(distribution_file), outdir=str(temporary_directory), interactive=False, verbosity=-1))
            except patoolib.util.PatoolError as ex:
                if 'unknown archive' in ex.args[0]:
                    raise _InvalidDistribution('Invalid archive or unknown archive format') from ex
                else:
                    raise
            
            # Yield
            yield unpack_directory
        
def _digest_of(directory):
    '''
    Get 0install 265new digest of directory
    '''
    alg = manifest.get_algorithm('sha256new')
    digest = alg.new_digest()
    for line in alg.generate_manifest(str(directory)):
        digest.update((line + '\n').encode('utf-8')) 
    digest = alg.getID(digest).split('_', maxsplit=1)[1]
    return digest
    
@attr.s
class _ZIRequirement(object):
    
    '''
    _convert_dependencies helper class
    '''
    
    required = attr.ib()  # True iff importance='required' 
    specifiers = attr.ib()  # [(operator :: str, version :: str)]. Python specifier list
    
def _convert_dependencies(context, egg_info_directory):
    # Parse requirements
    all_requirements = _parse_requirements(egg_info_directory)
    
    # Split into ZI required and recommended
    zi_requirements = defaultdict(lambda: _ZIRequirement(required=False, specifiers=[]))  # pypi_name => ZIRequirement
    extras = [extra for extra in all_requirements if extra is not None]
    if extras:
        context.feed_logger.warning(
            'Has extras. Each extra requirement item will be selected when '
            'possible with disregard of which extra the requirement belongs to. '
            'Extras: {}'
            .format(', '.join(map(repr, extras)))
        )
    if any(':' in extra for extra in extras):
        context.feed_logger.warning('Some extras have environment markers. Environment markers are ignored.')
    for extra, requirements in all_requirements.items():
        for requirement in requirements:
            # Note: requirement.key appears to be the name of extra, so can be ignored without warning
            if requirement.marker:
                context.feed_logger.warning('Marker ignored: {};{}'.format(requirement.name, requirement.marker))
            zi_requirement = zi_requirements[requirement.name]
            if not requirement.marker and not extra:
                zi_requirement.required = True
            zi_requirement.specifiers.extend(requirement.specs)
    
    # Convert
    requirements = []
    for pypi_name, zi_requirement in sorted(zi_requirements.items()):
        requires = zi.requires(
            interface=context.feed_uri(canonical_name(pypi_name)),
            importance='essential' if zi_requirement.required else 'recommended'
        )
        version_expression = convert_specifiers(context, zi_requirement.specifiers)
        if version_expression:
            requires.set('version', version_expression)
        requirements.append(requires)
    return requirements
    
def _parse_requirements(egg_info_directory):
    '''
    Get required and optional requirements from egg-info directory
    
    Returns
    -------
    {extra :: str or None : [pkg_resources.Requirement]}
        `extra` is the name of the group of optional dependencies or ``None`` if
        they are required. Like, ``setup(extras_require=...)`` with
        ``extras_require[None]=required_dependencies`.
    '''
    all_requirements = defaultdict(list)
    for name in 'requires.txt', 'depends.txt':
        dependencies_file = egg_info_directory / name
        if dependencies_file.exists():
            for extra, requirements in pkg_resources.split_sections(dependencies_file.read_text().splitlines()):
                all_requirements[extra].extend(pkg_resources.parse_requirements(requirements))
    return all_requirements

_languages = {
    'Natural Language :: Afrikaans': 'af',
    'Natural Language :: Arabic': 'ar',
    'Natural Language :: Bengali': 'bn',
    'Natural Language :: Bosnian': 'bs',
    'Natural Language :: Bulgarian': 'bg',
    'Natural Language :: Cantonese': 'zh_HK',
    'Natural Language :: Catalan': 'ca',
    'Natural Language :: Chinese (Simplified)': 'zh_HANS',
    'Natural Language :: Chinese (Traditional)': 'zh_HANT',
    'Natural Language :: Croatian': 'hr',
    'Natural Language :: Czech': 'cs',
    'Natural Language :: Danish': 'da',
    'Natural Language :: Dutch': 'nl',
    'Natural Language :: English': 'en',
    'Natural Language :: Esperanto': 'eo',
    'Natural Language :: Finnish': 'fi',
    'Natural Language :: French': 'fr',
    'Natural Language :: Galician': 'gl',
    'Natural Language :: German': 'de',
    'Natural Language :: Greek': 'el',
    'Natural Language :: Hebrew': 'he',
    'Natural Language :: Hindi': 'hi',
    'Natural Language :: Hungarian': 'hu',
    'Natural Language :: Icelandic': 'is',
    'Natural Language :: Indonesian': 'id',
    'Natural Language :: Italian': 'it',
    'Natural Language :: Japanese': 'ja',
    'Natural Language :: Javanese': 'jv',
    'Natural Language :: Korean': 'ko',
    'Natural Language :: Latin': 'la',
    'Natural Language :: Latvian': 'lv',
    'Natural Language :: Macedonian': 'mk',
    'Natural Language :: Malay': 'ms',
    'Natural Language :: Marathi': 'mr',
    'Natural Language :: Norwegian': 'nb_NO', # there's also nn_NO, so this conversion gets it wrong sometimes
    'Natural Language :: Panjabi': 'pa',
    'Natural Language :: Persian': 'fa_IR',
    'Natural Language :: Polish': 'pl',
    'Natural Language :: Portuguese': 'pt_PT',
    'Natural Language :: Portuguese (Brazilian)': 'pt_BR',
    'Natural Language :: Romanian': 'ro',
    'Natural Language :: Russian': 'ru',
    'Natural Language :: Serbian': 'sr',
    'Natural Language :: Slovak': 'sk',
    'Natural Language :: Slovenian': 'sl',
    'Natural Language :: Spanish': 'es',
    'Natural Language :: Swedish': 'sv',
    'Natural Language :: Tamil': 'ta',
    'Natural Language :: Telugu': 'te',
    'Natural Language :: Thai': 'th',
    'Natural Language :: Turkish': 'tr',
    'Natural Language :: Ukranian': 'uk',
    'Natural Language :: Urdu': 'ur',
    'Natural Language :: Vietnamese': 'vi',
}