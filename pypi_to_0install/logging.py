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

'''
Logging configuration and handlers
'''

import logging
from contextlib import contextmanager
import contextlib

def configure(context):
    _reset_logging()
    _set_log_levels(context)
    _add_stderr_handler(context)
    _add_file_handler(context)

def _reset_logging():
    # Note: zeroinstall calls logging.basicConfig when imported, naughty naughty
    root_logger = logging.getLogger()
    while root_logger.handlers:
        root_logger.removeHandler(root_logger.handlers[-1])
    
def _set_log_levels(context):
    # Filter out messages that no handler wants
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger('pypi_to_0install').setLevel(logging.DEBUG)
    context.feed_logger.setLevel(logging.DEBUG)
    
def _add_stderr_handler(context):
    # Create stderr handler with terse format
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter('{levelname[0]}: {message}', style='{'))
    
    # Log all info excluding most of the feed_logger unless it's an error
    stderr_handler.setLevel(logging.INFO)
    def filter_(record):
        return (
            record.name != context.feed_logger.name or
            record.levelno >= logging.ERROR or
            record.msg.startswith('Updating ')
        )
    stderr_handler.addFilter(filter_)
    
    # Add to root logger
    logging.getLogger().addHandler(stderr_handler)
    
def _add_file_handler(context):
    # Create file handler with detailed format
    file_handler = logging.FileHandler('pypi_to_0install.log')
    file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {message}', style='{'))
    
    # Log all debug excluding the feed_logger unless it's an error
    file_handler.setLevel(logging.DEBUG)
    def filter_(record):
        return (
            record.name != context.feed_logger.name or
            record.levelno >= logging.ERROR
        )
    file_handler.addFilter(filter_)
    
    # Add to root logger
    logging.getLogger().addHandler(file_handler)
    
@contextmanager
def feed_log_handler(context, log_file):
    file_handler = logging.FileHandler(str(log_file))
    with contextlib.closing(file_handler):
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {message}', style='{'))
        context.feed_logger.addHandler(file_handler)
        try:
            yield
        finally:
            context.feed_logger.removeHandler(file_handler)
