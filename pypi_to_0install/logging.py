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
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager
import contextlib
from pathlib import Path
import bz2

feed_logger = logging.getLogger(__name__ + ':current_feed')

def configure(context, verbosity):
    def reset_logging():
        # Note: zeroinstall calls logging.basicConfig when imported, naughty naughty
        root_logger = logging.getLogger()
        while root_logger.handlers:
            root_logger.removeHandler(root_logger.handlers[-1])
        
    def set_log_levels():
        # Filter out messages that no handler wants
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger('pypi_to_0install').setLevel(logging.DEBUG)
        feed_logger.setLevel(logging.DEBUG)
        
    def ensure_zi_name_prefix_filter(record):
        # Ensure each record has zi_name_prefix
        if hasattr(record, 'zi_name'):
            record.zi_name_prefix = record.zi_name + ': '
        else:
            record.zi_name_prefix = ''
        return True
        
    def add_stderr_handler():
        if not verbosity:
            return
        
        # Create stderr handler with terse format
        stderr_handler = logging.StreamHandler()
        stderr_handler.setFormatter(logging.Formatter('{levelname[0]}: {zi_name_prefix}{message}', style='{'))
        
        # Exclude <INFO
        stderr_handler.setLevel(logging.INFO)
        
        #
        if verbosity == 1:
            # Exclude feed_logger<ERROR, except the Updating msg
            def filter_(record):
                return (
                    record.name != feed_logger.name or
                    record.levelno >= logging.ERROR or
                    record.msg.startswith('Updating ')
                )
            stderr_handler.addFilter(filter_)
        
        #
        stderr_handler.addFilter(ensure_zi_name_prefix_filter)
            
        # Add to root logger
        logging.getLogger().addHandler(stderr_handler)
        
    def add_file_handler():
        # Create file handler with detailed format
        file_handler = _CompressedRotatingFileHandler('pypi_to_0install.log', max_bytes=10**10)
        file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {zi_name_prefix}{message}', style='{'))
        
        # Log all info, even from feed_logger
        file_handler.setLevel(logging.INFO)
        
        #
        file_handler.addFilter(ensure_zi_name_prefix_filter)
        
        # Add to root logger
        logging.getLogger().addHandler(file_handler)
        
    reset_logging()
    set_log_levels()
    add_stderr_handler()
    add_file_handler()

# Set max_bytes so that up to 150k packages can have a full log without
# exceeding GitHub's 1GB repository size limit
_feed_log_max_bytes = 2**30 // 150e3

@contextmanager
def configure_feed_logger(zi_name, log_file):
    '''
    Temporarily configure feed_logger for feed 
    '''
    # File handler
    file_handler = _CompressedRotatingFileHandler(str(log_file), _feed_log_max_bytes)
    with contextlib.closing(file_handler):
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('{levelname[0]} {asctime}: {message}', style='{'))
        
        # Add feed name to each log record by filter
        def filter_(record):
            record.zi_name = zi_name
            return True
        
        # Attach to logger
        feed_logger.addHandler(file_handler)
        feed_logger.addFilter(filter_)
        try:
            yield
        finally:
            feed_logger.removeHandler(file_handler)
            feed_logger.removeFilter(filter_)
            
def _CompressedRotatingFileHandler(file_name, max_bytes):
    '''
    Modify handler to bz2 compress when rotating
    
    Parameters
    ----------
    file_name : str
    max_bytes : int
        Max bytes that all log files combined may take (approximately)
    '''
    def namer(name):
        return name + ".bz2"

    def rotator(source, dest):
        with open(source, "rb") as f:
            data = f.read()
        compressed = bz2.compress(data)
        with open(dest, "wb") as f:
            f.write(compressed)
        Path(source).unlink()
    
    # Note: we expect a compression rate of 3.5. At this rate, 1 uncompressed
    # log file of max_bytes / 2 + 3 compressed files is less than max_bytes
    handler = RotatingFileHandler(file_name)#TODO tmp unlimited#, maxBytes=max_bytes // 2, backupCount=3)
    
    # Compress on rotate
    handler.rotator = rotator
    handler.namer = namer
    
    return handler
