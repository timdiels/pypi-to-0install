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

from ._version import parse_version
from zeroinstall.zerostore import manifest

class NoValidRelease(Exception):
    '''
    When a package has not a single valid release
    '''

class InvalidDistribution(Exception):
    pass

class UnsupportedDistribution(Exception):
    '''
    Valid but unsupported distribution
    '''

class InvalidDownload(Exception):
    '''
    Downloaded file is invalid, e.g. md5 hash does not match
    '''

def stability(pypi_version):
    version = parse_version(pypi_version)
    if version.modifiers and version.modifiers[-1].type_ == 'dev':
        return 'developer'
    elif version.is_prerelease:
        return 'testing'
    else:
        return 'stable'

def digest_of(directory):
    '''
    Get 0install 265new digest of directory
    '''
    alg = manifest.get_algorithm('sha256new')
    digest = alg.new_digest()
    for line in alg.generate_manifest(str(directory)):
        digest.update((line + '\n').encode('utf-8'))
    digest = alg.getID(digest).split('_', maxsplit=1)[1]
    return digest

languages = {
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
    'Natural Language :: Norwegian': 'nb_NO',  # there's also nn_NO, so this conversion gets it wrong sometimes
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
