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
from ._version import convert_version, parse_version, after_version, Modifier, InvalidVersion
from zeroinstall.injector.versions import parse_version as zi_parse_version, format_version as zi_format_version
    
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
    
@attr.s(frozen=True, repr=False, cmp=False)
class _Range(AST):
    
    '''
    version..!version | version.. | ..!version
    '''
    
    def _zi_parse_version_if_any(version):  # @NoSelf
        
        if isinstance(version, list):
            # ZI internal version is a list, so we assume it's an already parsed version
            return version
        elif version:
            return zi_parse_version(version)
        else:
            return None
    
    start = attr.ib(convert=_zi_parse_version_if_any)  # zi_version :: list or None. Start and end cannot both be None
    end = attr.ib(convert=_zi_parse_version_if_any)  # zi_version :: list or None
    
    def __and__(self, other):
        '''
        Intersect with range
        
        Returns
        -------
        _Range
        '''
        if self.start is None or other.start is None:
            start = self.start or other.start
        else:
            start = max(self.start, other.start)
            
        if self.end is None or other.end is None:
            end = self.end or other.end
        else:
            end = min(self.end, other.end)
            
        return _Range(start, end)
    
    def __lt__(self, other):
        if self.start is None:
            return True
        elif other.start is None:
            return False
        else:
            return self.start < other.start
        
    def format_zi(self):
        if self.start is None:
            start = ''
        else:
            start = zi_format_version(self.start)
            
        if self.end is None:
            end = ''
        else:
            end = zi_format_version(self.end)
            
        # If single version, return single, else return range
        if start and end == after_version(start):
            return start
        else:
            if end:
                end = '!' + end
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
    
    version = attr.ib()  # zi_version :: list
    
    def format_zi(self):
        return '!{}'.format(zi_format_version(self.version))
    
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
    expressions = []
    
    # Convert specifiers
    for operator, version in specifiers:
        try:
            try:
                if version.endswith('.*') and operator not in ('==', '!='):
                    raise _InvalidSpecifier('{} does not allow prefix match suffix (.*)'.format(operator))
                expressions.append(_converters[operator](version))
            except InvalidVersion as ex:
                raise _InvalidSpecifier('Invalid version: {}'.format(ex.args[0]))
        except _InvalidSpecifier as ex:
            context.feed_logger.warning(
                "Ignoring invalid specifier: '{}{}'. {}"
                .format(operator, version, ex.args[0])
            )
    
    # Return
    if not expressions:
        return None
    elif len(expressions) == 1:
        return expressions[0]
    else:
        return _And(expressions)

def _convert_ge(version):
    '''
    Convert >=version to AST
    
    Parameters
    ----------
    version : str
        Python version string
    '''
    return _Range(convert_version(version), None)  # v..

def _convert_le(version):
    '''
    Convert <=version to AST
    '''
    return _Range(convert_version('0.dev'), after_version(convert_version(version)))  # 0.dev..v; 0.dev is the min of valid Python versions

def _convert_gt(version):
    '''
    Convert >version to AST
    '''
    # Note: "The exclusive ordered comparison >V MUST NOT allow a post-release of the given version unless V itself is a post release."
    version = parse_version(version)
    can_append_post = not version.modifiers or version.modifiers[-1].type_ not in ('post', 'dev')
    if can_append_post:
        # Increment to first version after version.post*
        if version.modifiers:
            version.increment_last_modifier()
        else:
            version = attr.assoc(version, release=version.release + '.1')
        
        # Append .dev0
        version = version.append_modifier(Modifier('dev', 0))
        
        return _Range(version.format_zi(), None)  # (v+1).dev0..
    else:
        return _Range(after_version(version.format_zi()), None)  # v+..

def _convert_lt(version):
    '''
    Convert <version to AST
    '''
    # Note: "The exclusive ordered comparison <V MUST NOT allow a pre-release of the specified version unless the specified version is itself a pre-release."
    if not parse_version(version).is_prerelease:
        # Note: With v of the form epoch!release[.postN], v.dev0..!v are all
        # prereleases of v. Removing the prereleases from ..!v, yields
        # ..!v.dev0
        return _Range(None, convert_version(version + '.dev'))  # ..!v.dev0
    else:
        return _Range(None, convert_version(version))  # ..!v

def _convert_arbitrary_eq(version):
    '''
    Convert ===version to AST
    '''
    # Note: we only support valid public PEP440 versions, by consequence === is
    # equivalent to == without prefix match
    return _convert_eq(version, allow_prefix_match=False)

def _convert_compatible(version):
    '''
    Convert ~=version to AST
    '''
    and_expressions = []
    
    # >=v
    and_expressions.append(_convert_ge(version))
    
    # Replace modifiers and last release component with .*
    version = parse_version(version, trim_zeros=False)
    release = version.release.split('.')
    if len(release) < 2:
        raise _InvalidSpecifier('Compatible release clause requires multi-part release segment (e.g. ~=1.1)')
    release = '.'.join(release[:-1])
    version = attr.assoc(version, release=release, modifiers=[])
    and_expressions.append(_convert_eq(version.format_py() + '.*'))  # ==stripped.*
    
    # Return
    return _And(and_expressions)

def _convert_eq(version, allow_prefix_match=True):
    '''
    Convert ==version[.*] to AST
    '''
    print(version)
    return _convert_eq_or_ne(version, allow_prefix_match, is_eq=True)

def _convert_ne(version):
    '''
    Convert !=version[.*] to AST
    '''
    return _convert_eq_or_ne(version, allow_prefix_match=True, is_eq=False)

def _convert_eq_or_ne(version, allow_prefix_match, is_eq):
    is_prefix_match = version.endswith('.*')  # Note: prefix match is only allowed on == and !=
    if not is_prefix_match:
        version = convert_version(version)
        after_version_ = after_version(version)
        if is_eq:
            # v..!v+ = v
            return _Range(version, after_version_)
        else:
            # ..!v | v+.. = !v
            return _Or((
                _Range(None, version),
                _Range(after_version_, None)
            ))
    else:
        version = version[:-2]  # remove .* suffix
        version = parse_version(version)
        
        # Derive start of range covered by prefix.*
        start = version.append_modifier(Modifier('dev', 0))
        start = start.format_zi()
        
        # Derive end by incrementing by 1 the number of the last modifier if
        # any, or the last component of the release segment otherwise
        if version.modifiers:
            if version.modifiers[-1].type_ == 'dev':
                raise _InvalidSpecifier('Prefix match must not end with .dev.*')
            end = version.increment_last_modifier()
        else:
            end = version.increment_release()
        end = end.append_modifier(Modifier('dev', 0))
        end = end.format_zi()
            
        # Return AST
        if is_eq:
            # s..!e
            return _Range(start, end)
        else:
            # ..!s | e..
            return _Or((
                _Range(None, start),
                _Range(end, None)
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
    if len(ranges) == 2:
        range1 = ranges[0]
        range2 = ranges[1]
        if (range1.start is None
            and range2.end is None
            and range1.end is not None
            and range2.start is not None
            and after_version(zi_format_version(range1.end)) == zi_format_version(range2.start)
        ):
            return _NotVersion(range1.end)
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
        if range1.end is None:
            break
        
        # If touching/overlapping,
        is_touching_or_overlapping = range2.start is None or range1.end >= range2.start
        if is_touching_or_overlapping:
            # Join ranges
            if range2.end is None:
                end = None
            else:
                end = max(range1.end, range2.end)
            range1 = attr.assoc(end=end)
        else:
            # Save range1 and continue with range2
            new_ranges.append(range1)
            range1 = range2
            break
    new_ranges.append(range1)  # Save the last range
    return new_ranges
