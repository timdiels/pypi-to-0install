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

from pypi_to_0install.various import PyPITimeout
from pypi_to_0install import worker as worker_
from datetime import datetime, timedelta
from contextlib import contextmanager
from functools import partial
import multiprocessing as mp
import logging
import signal
import sys
import os

logger = logging.getLogger(__name__)

def parallel_update(context, worker_count, state):
    '''
    Update feeds of changed packages in parallel
    
    multiprocessing start method should be set to 'fork' as shared resources are
    passed in by argument, not by inheritance.
    
    Notes
    -----
    Why not threads? 1) You cannot (signal) interrupt a thread and 2) Python can
    only really execute one thread at a time and when using a local PyPI mirror, we
    are definitely processor-bound, not IO-bound.
    
    Why not concurrent.futures.ProcessPoolExecutor? It cannot be cancelled, its
    shutdown waits for all work to be finished.
    
    Why not multiprocessing.Pool? There is no way to have a worker process do
    cleanup on exit. When pool.terminate() is called, idle workers exit with
    os._exit, other workers receive SIGTERM. If you SIGTERM a worker before calling
    pool.terminate(), it creates a new worker. This makes it tricky to add cleanup
    on worker exit. Also note that atexit cannot be used for forked children as they
    should exit with os._exit.
    '''
    # Note: SimpleQueue simply blocks on put() when its pipe is full, so use
    # Queue for _changed_packages
    changed_packages = mp.Queue()
    results = mp.SimpleQueue()
    workers = []
    try:
        # Add workers
        repopulate_pool = partial(_repopulate_pool, context, workers, changed_packages, results, worker_count)
        repopulate_pool()
            
        # Fill work queue for workers
        results_left = len(state.changed.values())  # number of results we have yet to receive
        for package in state.changed.values():
            changed_packages.put(package)
            
        # Process and wait for results one by one
        with _exit_on_error() as errored:
            while results_left:
                # Wait for processes to die or results to come in
                sentinels = {worker.sentinel: worker for worker in workers}
                ready = mp.connection.wait(
                    list(sentinels.keys()) +
                    [results._reader]  # hack: accessing its privates
                )
                
                # Replace any dead processes
                for sentinel, worker in sentinels.items():
                    if sentinel in ready:
                        # Deduct a result in case it already took a package off
                        # self._changed_packages. We may end too early, but we
                        # surely won't end up waiting forever while queue is empty
                        # and workers are idle. Packages of missed results will
                        # simply be reconverted on the next run
                        results_left -= 1
                        
                        # Remove worker
                        workers.remove(worker)
                repopulate_pool()  # add workers
                
                # Process any results
                if results._reader in ready:
                    package, finished = results.get()
                    results_left -= 1
                    
                    # If error, note and continue
                    if isinstance(package, Exception):
                        ex = package
                        if isinstance(ex, PyPITimeout):
                            logger.error(ex.args[0] + '. PyPI may be having issues or may be blocking us. Giving up')
                            sys.exit(1)
                        errored()
                        continue
                        
                    # Update packages with changed package (it's a different
                    # instance due to crossing process boundaries)
                    state.packages[package.name] = package
                    
                    # Remove from todo list (changed) if finished
                    if finished:
                        del state.changed[package.name]
    finally:
        _kill_workers(workers)

def _repopulate_pool(context, workers, changed_packages, results, worker_count):
    while len(workers) < worker_count:
        worker = mp.Process(
            target=worker_.main,
            args=(context.pypi_uri, context.base_uri, context.pypi_mirror, changed_packages, results)
        )
        workers.append(worker)
        worker.start()
    
def _kill_workers(workers):
    def join_workers():
        '''
        Join workers with a 10s timeout
        
        Returns
        -------
        bool
            True iff all workers have joined
        '''
        deadline = datetime.now() + timedelta(seconds=10)
        for worker in workers:
            timeout = (deadline - datetime.now()).total_seconds()
            if timeout <= 0:
                return False
            worker.join(timeout)
        return True
    
    # Ignore workers which were not started. This happens if interrupted at
    # the right time in _add_worker
    workers = [worker for worker in workers if worker.pid]
    
    # Terminate workers
    for worker in workers:
        worker.terminate()  # sigterm
    
    # Try join workers
    if not join_workers():
        # SIGKILL workers which failed to terminate
        for worker in workers:
            if not worker.exitcode:
                os.kill(worker.pid, signal.SIGKILL)

@contextmanager
def _exit_on_error():
    # Exit non-zero iff errored
    errored_ = False
    def errored():
        nonlocal errored_
        errored_ = True  # @UnusedVariable, it doesn't understand nonlocal
    try:
        yield errored
    finally:
        if errored_:
            logger.error('There were errors, programmer required, see exception(s) in log')
            sys.exit(2)
