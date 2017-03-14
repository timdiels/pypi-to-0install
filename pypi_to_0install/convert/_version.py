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

from zeroinstall.injector.versions import parse_version as zi_parse_version
from packaging.version import parse as py_parse_version, VERSION_PATTERN
from functools import total_ordering
import attr
import re

@total_ordering
@attr.s(frozen=True, cmp=False)
class Version(object):
    epoch = attr.ib()  #: int
    release = attr.ib()  #: str, e.g. 1.1
    
    #: tuple(Modifier). Musn't contain Modifier(type_='')
    modifiers = attr.ib(convert=tuple)
    
    #: str or None; if Version was created by parsing, the raw string which got
    #: parsed (such that parse_version(raw) == self), None otherwise (e.g.
    #: after_version())
    raw = attr.ib()
    
    #: allows for versions to come right after another such that no Python version can fit between them
    _after = attr.ib(default=0)
    
    #: Note: MIN/MAX are set after class definition (these assignments help keep calm Pylint)
    MIN = None  #: smallest possible version, just a regular version
    MAX = None  #: largest possible version, a special version that only supports comparisons
    
    def format_zi(self):
        '''
        Format as ZI version
        
        Returns
        -------
        str
        '''
        # modifiers
        modifiers = list(self.modifiers)
        max_modifiers = 3  # ...pre.post.dev
        if len(modifiers) < max_modifiers:
            modifiers.append(Modifier('', None))
        modifiers = '-'.join(modifier.format_zi() for modifier in modifiers)
        
        # after
        if self._after:
            after = '-{}'.format(self._after)
        else:
            after = ''
        
        #
        return '{epoch}-{release}-{modifiers}{after}'.format(
            epoch=self.epoch,
            release=self.release,
            modifiers=modifiers,
            after=after
        )
        
    def format_py(self):
        '''
        Format as Python version
        
        Returns
        -------
        str
        '''
        if self.after:
            raise Exception('Cannot format after-version as Python version')
        
        if self.modifiers:
            modifiers = '.' + '.'.join(modifier.format_py() for modifier in self.modifiers)
        else:
            modifiers = ''
        
        return '{epoch}!{release}{modifiers}'.format(
            epoch=self.epoch,
            release=self.release,
            modifiers=modifiers
        )
        
    def increment_last_modifier(self):
        '''
        Return version with last modifier incremented by 1
        '''
        if not self.modifiers:
            raise Exception('Cannot increment last modifier of version; it has no modifiers')
        last_modifier = self.modifiers[-1]
        last_modifier = attr.assoc(last_modifier, number=last_modifier.number + 1)
        modifiers = self.modifiers[:-1] + (last_modifier,)
        return attr.assoc(self, modifiers=modifiers, raw=None)
        
    def increment_release(self):
        '''
        Return version with last component of release incremented by 1
        '''
        release = self.release.split('.')
        release[-1] = str(int(release[-1]) + 1)
        release = '.'.join(release)
        return attr.assoc(self, release=release, raw=None)
        
    @property
    def is_prerelease(self):
        return self.modifiers and self.modifiers[0].type_ in ('a', 'b', 'rc')
    
    def append_modifier(self, modifier):
        '''
        Append modifier
        '''
        modifiers = self.modifiers + (modifier,)
        return attr.assoc(self, modifiers=modifiers, raw=None)
    
    def after_version(self):
        '''
        Get a version such that version..!after_version contains only the given
        version
        '''
        return attr.assoc(self, _after=self._after + 1, raw=None)
        
    def __eq__(self, other):
        if other == Version.MAX:
            return False
        else:
            return (
                (self.epoch, self.release, self.modifiers, self._after)
                ==
                (other.epoch, other.release, other.modifiers, other._after)
            )
        
    def __lt__(self, other):
        if other == Version.MAX:
            return True
        else:
            return zi_parse_version(self.format_zi()) < zi_parse_version(other.format_zi())
        
@attr.s(frozen=True)
class Modifier(object):
    type_ = attr.ib()  # str
    number = attr.ib()  # int or None iff type_==''
    
    _modifier_priorities = {
        'dev': 0,
        'a': 1,
        'b': 2,
        'rc': 3,
        '': 4,
        'post': 5
    }
    
    def format_zi(self):
        '''
        Format for use in ZI version string
        '''
        priority = Modifier._modifier_priorities[self.type_]
        if self.number is None:
            return str(priority)
        else:
            return '{}.{}'.format(priority, self.number)
        
    def format_py(self):
        '''
        Format for use in Python version string
        '''
        return '{}{}'.format(self.type_, self.number)
    
class InvalidVersion(Exception):
    pass
        
#TODO mv to tests, no longer used in 'real' code
def convert_version(version):
    '''
    Get ZI version string given a Python version string
    '''
    version = parse_version(version)
    return version.format_zi()
        
def parse_version(version, trim_zeros=True):
    '''
    Parse Python version string
    
    Parameters
    ----------
    version : str
        Python version. ``.*`` suffix is NOT allowed.
    trim_zeros : bool
        If True, trailing ``.0``\ s on the release segment are removed
    
    Returns
    -------
    Version
    
    Raises
    ------
    InvalidVersion
        If is not a valid PEP440 public version
    '''
    raw = version
    
    # Normalise the version; handles odd cases like 'alpha' instead of 'a'
    version = str(py_parse_version(version))
    
    # Split version
    match = re.fullmatch(VERSION_PATTERN, str(version), re.VERBOSE + re.IGNORECASE)
    if not match:
        raise InvalidVersion(
            'Got: {!r}. Should be valid (public) PEP440 version'
            .format(raw)
        )
    parts = match.groups()
    epoch = int(parts[0] or 0)
    release = parts[1]
    prerelease_type = parts[3]
    prerelease_number = parts[5]
    post_number = parts[9]
    dev_number = parts[12]
    local = parts[13]
    if local is not None:
        raise InvalidVersion(
            'Got local version: {!r}. Should be public version'
            .format(raw)
        )
    
    # Trim trailing zeros
    if trim_zeros:
        release = release.split('.')
        while release[-1] == '0' and len(release) > 1:
            release = release[:-1]
        release = '.'.join(release)
    
    # modifiers
    modifiers = []
    if prerelease_type is not None:
        modifiers.append(Modifier(prerelease_type, int(prerelease_number)))
    if post_number is not None:
        modifiers.append(Modifier('post', int(post_number)))
    if dev_number is not None:
        modifiers.append(Modifier('dev', int(dev_number)))
    
    return Version(epoch, release, modifiers, raw)

@total_ordering
class MaxVersion(object):
    def __lt__(self, other):
        if other == Version.MAX:
            return True
        else:
            return not (other < self)
        
Version.MIN = parse_version('0.dev')
Version.MAX = MaxVersion()
del MaxVersion
