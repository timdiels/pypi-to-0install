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

from pypi_to_0install.various import (
    zi, kill, CalledProcessError
)
from contextlib import suppress
from lxml import etree  # @UnresolvedImport
import subprocess
import asyncio

async def convert_general(context, pypi_name, release_data):
    '''
    Create feed with general info from latest release_data
    '''
    interface = zi.interface(**{
        'uri': context.feed_uri(context.zi_name),
        'min-injector-version': '0.48',  # TODO check what we use, set accordingly
    })
    interface.append(zi.name(context.zi_name))

    summary = release_data.get('summary', 'Converted from PyPI; missing summary')
    interface.append(zi.summary(summary))  # Note: required element

    homepage = release_data.get('home_page')
    if homepage:
        interface.append(zi.homepage(homepage))

    description = release_data.get('description')
    if description:
        description = await _try_convert_description(context, description)
        interface.append(zi.description(description))

    # TODO: <category>s from classifiers

    classifiers = release_data.get('classifiers', [])
    if 'Environment :: Console' in classifiers:  # TODO test
        interface.append(zi('needs-terminal'))

    return etree.ElementTree(interface)

async def _try_convert_description(context, description):
    '''
    Convert description to ZI description.

    If conversion times out or fails, return unconverted.
    '''
    args = ('pandoc', '--from', 'rst', '--to', 'plain')
    process = await asyncio.create_subprocess_exec(
        *args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    async def kill_process():
        with suppress(ProcessLookupError):
            process.terminate()
        await kill([process.pid], timeout=1)
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(description.encode()),
            timeout=1  # second
        )
    except asyncio.TimeoutError:
        # Note: it turns out it's possible to write descriptions that (seem to)
        # take forever to convert
        context.logger.warning('Could not convert description: timed out')
        await kill_process()
        return description
    except Exception:
        context.logger.warning('Could not convert description', exc_info=True)
        await kill_process()
        return description
    finally:
        await process.wait()
    if process.returncode == 0:
        description = stdout.decode()
    else:
        context.logger.warning(
            'Could not convert description: {}'.format(
                CalledProcessError(process.returncode, args, stdout, stderr)
            )
        )
    return description
