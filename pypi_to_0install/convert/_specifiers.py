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

import attr
from ._version import parse_version, Modifier, InvalidVersion, Version
from zeroinstall.injector.versions import parse_version as zi_parse_version
    
def convert_specifiers(context, specifiers):
    '''
    Convert Python version specifiers to ZI constraints
    
    Parameters
    ----------
    specifiers : iterable((operator :: str, version :: str))
        Python version specifiers
        
    Returns
    -------
    str or None
        ZI version expression: ``range | range | ...`` or None if no constraint
    '''
    ast = _specifiers_to_ast(context, specifiers)
    if not ast:
        return None
    print(ast)
    ast = _remove_and(ast)
    print(ast)
    ast = _simplify(ast)
    return ast.format_zi()

class AST(object):
    
    '''
    Interface: Abstract Syntax Tree
    '''
    
    def format_zi(self):
        '''
        Format as ZI version constraint
        
        Returns
        -------
        str
            ZI version constraint, i.e. fits in ``<requires version={}>``
        '''
        raise NotImplementedError()
        
@attr.s(frozen=True)
class _And(AST):
    
    '''
    expr (and expr)*
    '''
    
    expressions = attr.ib(convert=tuple) # tuple(_And or _Or or _Range)
    
    def format_zi(self):
        raise NotImplementedError('Cannot be formatted as ZI version constraint')
    
@attr.s(frozen=True)
class _Or(AST):
    
    '''
    range (or range)*
    '''
    
    def _validate_ranges(self, attribute, ranges):
        for range_ in ranges:
            if not isinstance(range_, _Range):
                raise Exception('Invalid range: {!r}'.format(range_))
            
    ranges = attr.ib(convert=tuple, validator=_validate_ranges)  # tuple(_Range)
    
    def format_zi(self):
        return ' | '.join(range_.format_zi() for range_ in self.ranges)
    
@attr.s(frozen=True, repr=False, str=False, cmp=False)
class _Range(AST):
    
    '''
    version..!version | version.. | ..!version
    '''
    
    def _validate_start(self, attribute, start):
        if start is None:
            raise ValueError('start cannot be None')
        if start == Version.MAX:
            raise ValueError('Range cannot start at Version.MAX')
        
    def _validate_end(self, attribute, end):
        if end is None:
            raise ValueError('end cannot be None')
        if end == Version.MIN:
            raise ValueError('Range cannot end at Version.MAX')
        if end <= self.start:
            raise ValueError('Range cannot be empty')
        
    start = attr.ib(validator=_validate_start)  # :: Version
    end = attr.ib(validator=_validate_end)  # :: Version
    
    def __and__(self, other):
        '''
        Intersect with range
        
        Returns
        -------
        _Range
        '''
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        return _Range(start, end)
    
    def __lt__(self, other):
        return self.start < other.start
        
    def format_zi(self):
        # If range contains single version, return version, else return range
        if self.end == self.start.after_version():
            return self.start.format_zi()
        else:
            if self.start == Version.MIN:
                start = ''
            else:
                start = self.start.format_zi()
                
            if self.end == Version.MAX:
                end = ''
            else:
                end = '!' + self.end.format_zi()
                
            return '{}..{}'.format(start, end)
    
    def __repr__(self):
        return '_Range({!r})'.format(self.format_zi())
    
    def __str__(self):
        return self.format_zi()
    
@attr.s(frozen=True)
class _NotVersion(AST):
    
    '''
    !version
    '''
    
    version = attr.ib()  # :: Version
    
    def format_zi(self):
        return '!{}'.format(self.version.format_zi())
    
class _InvalidSpecifier(Exception):
    pass

def _specifiers_to_ast(context, specifiers):
    '''
    Build abstract syntax tree from Python version specifiers
    
    Parameters
    ----------
    context : Context
    specifiers : iterable((operator :: str, version :: str))
        Python version specifiers
        
    Returns
    -------
    _And or None
        Root of the created abstract syntax tree or None if the specifiers did
        not actually constrain anything
    '''
    and_expressions = []
    
    # Convert specifiers
    for operator, version in specifiers:
        def _log_invalid_specifier(reason):
            context.feed_logger.warning(
                "Ignoring invalid specifier: '{}{}'. {}"
                .format(operator, version, reason)
            )
            
        try:
            if version.endswith('.*'):
                try:
                    converter = _prefix_match_converters[operator]
                except KeyError:
                    _log_invalid_specifier('{} does not allow prefix match suffix (.*)'.format(operator))
                    continue
                expression = converter(parse_version(version[:-2]))  # Note: -2 removes the .* suffix
            else:
                expression = _converters[operator](parse_version(version))
            and_expressions.append(expression)
        except InvalidVersion as ex:
            _log_invalid_specifier('Invalid version: {}'.format(ex.args[0]))
        except _InvalidSpecifier as ex:
            _log_invalid_specifier(ex.args[0])
    
    # Return
    if not and_expressions:
        return None  # happens when all specifiers were ignored (due to invalid)
    elif len(and_expressions) == 1:
        return and_expressions[0]
    else:
        return _And(and_expressions)

def _convert_ge(version):
    '''
    Convert >=version to AST
    
    Parameters
    ----------
    version : str
        Python version string
    '''
    return _Range(version, Version.MAX)  # v..

def _convert_le(version):
    '''
    Convert <=version to AST
    '''
    return _Range(Version.MIN, version.after_version())  # ..v

def _convert_gt(version):
    '''
    Convert >version to AST
    '''
    # Note: "The exclusive ordered comparison >V MUST NOT allow a post-release of the given version unless V itself is a post release."
    can_append_post = not version.modifiers or version.modifiers[-1].type_ not in ('post', 'dev')
    if can_append_post:
        # Increment to first version after version.post*
        if version.modifiers:
            version.increment_last_modifier()
        else:
            version = attr.assoc(version, release=version.release + '.1', raw=None)
        
        # Append .dev0
        version = version.append_modifier(Modifier('dev', 0))
        
        return _Range(version, Version.MAX)  # (v+1).dev0..
    else:
        return _Range(version.after_version(), Version.MAX)  # v+..

def _convert_lt(version):
    '''
    Convert <version to AST
    '''
    # Note: "The exclusive ordered comparison <V MUST NOT allow a pre-release of the specified version unless the specified version is itself a pre-release."
    if not version.is_prerelease:
        # Note: With v of the form epoch!release[.postN], v.dev0..!v are all
        # prereleases of v. Removing the prereleases from ..!v, yields
        # ..!v.dev0
        return _Range(Version.MIN, version.append_modifier(Modifier('dev', 0)))  # ..!v.dev0
    else:
        return _Range(Version.MIN, version)  # ..!v

def _convert_arbitrary_eq(version):
    '''
    Convert ===version to AST
    '''
    # Note: we only support valid public PEP440 versions, by consequence === is
    # equivalent to == without prefix match
    return _convert_eq(version)

def _convert_compatible(version):
    '''
    Convert ~=version to AST
    '''
    and_expressions = []
    
    # >=v
    and_expressions.append(_convert_ge(version))
    
    # Replace modifiers and last release component with .*
    version = parse_version(version.raw, trim_zeros=False)
    release = version.release.split('.')
    if len(release) < 2:
        raise _InvalidSpecifier('Compatible release clause requires multi-part release segment (e.g. ~=1.1)')
    release = '.'.join(release[:-1])
    version = attr.assoc(version, release=release, modifiers=(), raw=None)
    and_expressions.append(_convert_eq_prefix_match(version))  # ==stripped.*
    
    # Return
    return _And(and_expressions)

def _convert_eq(version):
    '''
    Convert ==version to AST
    '''
    # v..!v+ = v
    return _Range(version, version.after_version())

def _convert_ne(version):
    '''
    Convert !=version to AST
    '''
    # ..!v | v+.. = !v
    return _Or((
        _Range(Version.MIN, version),
        _Range(version.after_version(), Version.MAX)
    ))

def _convert_eq_prefix_match(version):
    '''
    Convert ==version.* to AST
    '''
    return _convert_prefix_match(version, is_eq=True)
    
def _convert_ne_prefix_match(version):
    '''
    Convert !=version.* to AST
    '''
    return _convert_prefix_match(version, is_eq=False)

def _convert_prefix_match(version, is_eq):
    # Derive start of range covered by prefix.*
    start = version.append_modifier(Modifier('dev', 0))
    
    # Derive end by incrementing by 1 the number of the last modifier if
    # any, or the last component of the release segment otherwise
    if version.modifiers:
        if version.modifiers[-1].type_ == 'dev':
            raise _InvalidSpecifier('Prefix match must not end with .dev.*')
        end = version.increment_last_modifier()
    else:
        end = version.increment_release()
    end = end.append_modifier(Modifier('dev', 0))
        
    # Return AST
    if is_eq:
        # s..!e
        return _Range(start, end)
    else:
        # ..!s | e..
        return _Or((
            _Range(Version.MIN, start),
            _Range(end, Version.MAX)
        ))
    
_converters = {
    '>=': _convert_ge,
    '>': _convert_gt,
    '<=': _convert_le,
    '<': _convert_lt,
    '===': _convert_arbitrary_eq,
    '~=': _convert_compatible,
    '==': _convert_eq,
    '!=': _convert_ne,
}

_prefix_match_converters = {
    '==': _convert_eq_prefix_match,
    '!=': _convert_ne_prefix_match,
}
    
def _remove_and(ast):
    '''
    Remove all _And from abstract syntax tree
    
    Parameters
    ----------
    ast : _And or _Or or _Range
        AST root
        
    Returns
    -------
    _Or
        Root of AST with all _And removed
    '''
    if isinstance(ast, _And):
        # Reduce expressions left to right
        left = _remove_and(ast.expressions[0])
        for right in ast.expressions[1:]:
            right = _remove_and(right)
            
            # Convert _And(_Or, _Or) to _Or, e.g.:
            # (r1 | r2 ...) & (r3 | r4 ...)
            # to
            # ((r1 & r3) | (r1 & r4) | (r2 & r3) | (r2 & r4) ...)
            left = _Or(range1 & range2 for range1 in left.ranges for range2 in right.ranges)
        return left
    elif isinstance(ast, _Range):
        return _Or((ast,))
    else:
        return ast
    
def _simplify(ast):
    '''
    Simplify abstract syntax tree
    
    Parameters
    ----------
    ast : _Or
        AST root
        
    Returns
    -------
    _Or or _Range or _NotVersion
        Root of simplified AST
    '''
    ranges = sorted(ast.ranges)
    ranges = _join_touching_or_overlapping(ranges)
    
    # If ranges includes all but one version, return !version
    if len(ranges) == 2:
        range1 = ranges[0]
        range2 = ranges[1]
        if (range1.start == Version.MIN
            and range2.end == Version.MAX
            and range1.end.after_version() == range2.start
        ):
            return _NotVersion(range1.end)
        
    #
    if len(ranges) == 1:
        return ranges[0]
    else:
        return _Or(ranges)
    
def _join_touching_or_overlapping(ranges):
    '''
    Join touching or overlapping ranges
    
    Parameters
    ----------
    ranges : Sequence(_Range)
        Sorted ranges
        
    Returns
    -------
    [_Range]
    '''
    new_ranges = []
    range1 = ranges[0]
    for range2 in ranges[1:]:
        # If range is v.., stop as it includes all subsequent ranges
        if range1.end == Version.MAX:
            break
        
        # If touching/overlapping,
        is_touching_or_overlapping = range1.end >= range2.start
        if is_touching_or_overlapping:
            # Join ranges
            end = max(range1.end, range2.end)
            range1 = attr.assoc(end=end)
        else:
            # Save range1 and continue with range2
            new_ranges.append(range1)
            range1 = range2
            break
    new_ranges.append(range1)  # Save the last range
    return new_ranges
