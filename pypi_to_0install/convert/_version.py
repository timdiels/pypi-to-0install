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

from packaging.version import parse as py_parse_version, VERSION_PATTERN
import attr
import re

@attr.s(frozen=True)
class Version(object):
    epoch = attr.ib()  # int
    release = attr.ib()  # str, e.g. 1.1
    modifiers = attr.ib(convert=tuple)  # tuple(Modifier). Musn't contain Modifier(type_='')
    
    def format_zi(self):
        '''
        Format as ZI version
        
        Returns
        -------
        str
        '''
        modifiers = list(self.modifiers)
        max_modifiers = 3  # ...pre.post.dev
        if len(modifiers) < max_modifiers:
            modifiers.append(Modifier('', None))
        modifiers = '-'.join(modifier.format_zi() for modifier in modifiers)
        
        return '{epoch}-{release}-{modifiers}'.format(
            epoch=self.epoch,
            release=self.release,
            modifiers=modifiers
        )
        
    def format_py(self):
        '''
        Format as Python version
        
        Returns
        -------
        str
        '''
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
        return attr.assoc(self, modifiers=modifiers)
        
    def increment_release(self):
        '''
        Return version with last component of release incremented by 1
        '''
        release = self.release.split('.')
        release[-1] = str(int(release[-1]) + 1)
        release = '.'.join(release)
        return attr.assoc(self, release=release)
        
    @property
    def is_prerelease(self):
        return self.modifiers and self.modifiers[0].type_ in ('a', 'b', 'rc')
    
    def append_modifier(self, modifier):
        '''
        Append modifier
        '''
        modifiers = self.modifiers + (modifier,)
        return attr.assoc(self, modifiers=modifiers)
        
        
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
    original_version = version
    
    # Normalise the version; handles odd cases like 'alpha' instead of 'a'
    version = str(py_parse_version(version))
    
    # Split version
    match = re.fullmatch(VERSION_PATTERN, str(version), re.VERBOSE + re.IGNORECASE)
    if not match:
        raise InvalidVersion(
            'Got: {!r}. Should be valid (public) PEP440 version'
            .format(original_version)
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
            'Got local version: {!r}. Should be public'
            .format(original_version)
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
    
    return Version(epoch, release, modifiers)

#TODO rm if unused
def after_version(version):
    '''
    Get a version such that version..!after_version contains only the given
    version
    
    Parameters
    ----------
    version :: str
        ZI version
    
    Returns
    -------
    str
        ZI version, might not correspond to an actual Python version.
    '''
    return version + '-1'  # -0 would be sufficient, -1 shields us from the 0.001% chance that zero padding is added to ZI