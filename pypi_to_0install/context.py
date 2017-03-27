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

import logging
import attr

@attr.s(frozen=True, slots=True, cmp=False, hash=False)
class Context(object):
    
    pypi_uri = attr.ib()  # uri of Python index XMLRPC interface. See https://wiki.python.org/moin/PyPIXmlRpc
    base_uri = attr.ib()  # base URI where all files will be hosted
    pypi_mirror = attr.ib()  # uri of PyPI mirror to use for downloads, if any
