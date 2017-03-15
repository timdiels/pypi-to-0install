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
from contextlib import contextmanager
import contextlib
import attr
import pypandoc
from patoolib import extract_archive
from tempfile import TemporaryDirectory
from urllib.request import urlretrieve
import urllib.error
import pkginfo
from pypi_to_0install.various import zi, zi_namespaces, canonical_name
from ._version import parse_version
from ._specifiers import convert_specifiers
import logging
from collections import defaultdict
import pkg_resources
from zeroinstall.zerostore import manifest
import hashlib
from chicken_turtle_util import path as path_

logger = logging.getLogger(__name__)

def convert(context, pypi_name, zi_name, old_feed):
    '''
    Convert PyPI package to ZI feed
    
    Returns
    -------
    lxml.etree.ElementTree
    '''
    show_hidden = True
    versions = context.pypi.package_releases(pypi_name, show_hidden)  # returns [version :: str]
    max_version = max(versions, key=parse_version)
    release_data = context.pypi.release_data(pypi_name, max_version)
    
    # Create feed with general info
    feed = _convert_general(context, pypi_name, zi_name, release_data)
    
    # Add <implementation>s to feed
    for version in versions:
        zi_version = parse_version(version).format_zi()
        for release_url in context.pypi.release_urls(pypi_name, version):
            try:
                package_type = release_url['packagetype']
                action = 'Converting' if package_type == 'sdist' else 'Skipping' 
                logger.info('{} {} distribution: {}'.format(action, package_type, release_url['filename']))
                if action == 'Converting':
                    _convert_distribution(context, pypi_name, zi_name, zi_version, feed, old_feed, release_data, release_url)
            except _InvalidDownload as ex:
                #TODO mark this conversion partial, i.e. needs to be revisited/redone at a later time
                context.feed_logger.warning(
                    'Failed to download distribution, retrying later. {}'
                    .format(ex.args[0])
                )
                
    return feed
    
def _convert_general(context, pypi_name, zi_name, release_data):
    '''
    Populate feed with general info from latest release_data
    '''
    interface = zi.interface(**{
        'uri': context.feeds_uri + zi_name + '.xml',
        'min-injector-version': '0.48', #TODO check what we use, set accordingly
    })
    interface.append(zi.name(zi_name))
    
    summary = release_data.get('summary')
    if summary:
        interface.append(zi.summary(summary))
        
    homepage = release_data['home_page']
    if homepage:
        interface.append(zi.homepage(homepage))
        
    description = release_data['description']
    if description:
        description = pypandoc.convert_text(description, format='rst', to='plain')
        description = description[:100] #TODO rm, debug 
        interface.append(zi.description(description))
        
    #TODO: <category>s from classifiers
    
    classifiers = release_data.get('classifiers')
    if 'Environment :: Console' in classifiers:  #TODO test
        interface.append(zi('needs-terminal'))
        
    return etree.ElementTree(interface)

def _convert_distribution(context, pypi_name, zi_name, zi_version, feed, old_feed, release_data, release_url): #TODO rm unused params
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
        distribution_directory = next(unpack_directory.iterdir())
        context.feed_logger.debug('Converting')
        egg_info_directory = next(distribution_directory.glob('*.egg-info'))
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
                    interface=context.feed_uri('convert_sdist', converted=False)
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
        print((etree.tostring(feed, pretty_print=True)).decode())
        assert False
        
def _stability(pypi_version):
    pypi_version = parse_version(pypi_version)
    if 'dev' in str(pypi_version):
        return 'developer'
    elif pypi_version.is_prerelease:
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
    
    # Download
    context.feed_logger.debug('Downloading {}'.format(url))
    distribution_file = Path(urlretrieve(url)[0])  # returns temp file with correct extension
    
    # Check md5 hash
    print(release_url['md5_digest'])
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
#         temporary_directory = Path('test') #TODO rm debug
        
        context.feed_logger.debug('Unpacking')
        unpack_directory = Path(extract_archive(str(distribution_file), outdir=str(temporary_directory), interactive=False, verbosity=-1))
        
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
    
def _convert_dependencies(context, egg_info_path):
    # Parse requirements
    all_requirements = _parse_requirements(egg_info_path)
    
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