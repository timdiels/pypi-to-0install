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

from pypi_to_0install.various import zi, canonical_name
from ._various import InvalidDistribution, UnsupportedDistribution
from ._specifiers import convert_specifiers, EmptyRangeConversion
from collections import defaultdict
import pkg_resources
import attr

def convert_dependencies(context, egg_info_directory):
    '''
    Convert Python dependencies into list of ZI <requires>
    '''
    # Parse requirements
    all_requirements = _parse_requirements(egg_info_directory)

    # Warn about any extras and conditional requirements
    extras = [extra for extra in all_requirements if extra is not None]
    if extras:
        context.logger.warning(
            'Has extras. Each extra requirement item will be selected when '
            'possible with disregard of which extra the requirement belongs to. '
            'Extras: {}'
            .format(', '.join(map(repr, extras)))
        )
    if any(':' in extra for extra in extras):
        context.logger.warning('Some extras have environment markers. Environment markers are ignored.')

    # Merge extras and required dependencies, intersecting specifiers for
    # dependencies which appear in multiple places
    zi_requirements = defaultdict(lambda: _ZIRequirement(required=False, specifiers=[]))  # pypi_name => ZIRequirement
    for extra, requirements in all_requirements.items():
        for requirement in requirements:
            # Note: requirement.key appears to be the name of extra, so can be ignored without warning
            if requirement.marker:
                context.logger.warning('Marker ignored: {};{}'.format(requirement.name, requirement.marker))
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
        try:
            version_expression = convert_specifiers(context, zi_requirement.specifiers)
        except EmptyRangeConversion:
            raise InvalidDistribution(
                'Requirement {!r} (pypi name) constrains to an empty range '
                'and can never be satisfied'.format(pypi_name)
            )
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
    dependencies_files = [egg_info_directory / name for name in ('requires.txt', 'depends.txt')]
    if all(file.exists() for file in dependencies_files):
        raise UnsupportedDistribution('Egg info has both a requires.txt and depends.txt file')
    for dependencies_file in dependencies_files:
        if dependencies_file.exists():
            for extra, requirements in pkg_resources.split_sections(dependencies_file.read_text().splitlines()):
                try:
                    all_requirements[extra].extend(pkg_resources.parse_requirements(requirements))
                except pkg_resources.RequirementParseError as ex:
                    raise InvalidDistribution('{} failed to parse'.format(name)) from ex
    return all_requirements

@attr.s
class _ZIRequirement(object):

    required = attr.ib()  # True iff importance='required'
    specifiers = attr.ib()  # [(operator :: str, version :: str)]. Python specifier list
