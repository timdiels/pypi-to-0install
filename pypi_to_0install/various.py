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

import re
import attr
from lxml.builder import ElementMaker

zi_namespaces = {
    None: 'http://zero-install.sourceforge.net/2004/injector/interface',
    'compile': 'http://zero-install.sourceforge.net/2006/namespaces/0compile'
}
zi = ElementMaker(namespace=zi_namespaces[None], nsmap=zi_namespaces)

def canonical_name(pypi_name):
    '''
    Get canonical ZI name
    '''
    return re.sub(r"[-_.]+", "-", pypi_name).lower()
            
@attr.s
class Blacklists(object):
    
    # Distributions never to try converting (again)
    # {distribution_url :: str}
    distributions = attr.ib(default=attr.Factory(set))
    
    # Versions that have been ignored
    # {py_version :: str}
    versions = attr.ib(default=attr.Factory(set))