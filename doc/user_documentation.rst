User documentation
==================
   
Installation
------------
To install::

    git clone https://github.com/timdiels/pypi-to-0install.git
    cd pypi-to-0install
    python3.6 -m venv venv && . venv/bin/activate
    pip install -r requirements.txt

    # Add 0install python package to what will be our PYTHONPATH
    wget https://downloads.sf.net/project/zero-install/0install/2.3.4/0install-2.3.4.tar.bz2
    tar -xaf 0install-2.3.4.tar.bz2
    mv 0install-2.3.4/zeroinstall .
    rm -rf 0install-2.3.4*  # cleanup

PyPI to 0install has been tested with Python 3.6 and requires at least Python
3.6. You also need to `install Zero Install`_ such that ``0install`` is
available on ``$PATH``.

The default GPG key will be used to sign feeds. If you don't have one,
create it with ``gpg --gen-key``; do not use your real name, use something like
"PyPI to 0install" to indicate this was signed by an algorithm, not by you
personally. If you do not want to mess up your main GPG configuration, make a
new GPG home directory first and point the environment var ``GNUPGHOME`` to it.
To use a different key, set ``default-key {key_name}`` in
``$GNUPGHOME/gpg.conf``.

`Install Firejail`_ with your system's package manager. Firejail sandboxing is
used to prevent malicious packages from compromising the system (``setup.py``
needs to be executed to get egg-info and can contain arbitrary code).  For
this to work properly, ``CONFIG_USER_NS=y`` must be set in the kernel config
(The linux-grsec Arch Linux package already sets this). Consider using
Grsecurity for additional security.

PyPI to 0install requires at least the following sudo permissions (also see the
section below on cgroups)::

    sudo mount -t ext4 $file $mountpoint
    sudo umount $mountpoint

Running
-------
cgroups are required to prevent a malicious setup.py from hogging resources.
PyPI to 0install executes the following commands to set up cgroups, unless the
required directories already exist::

    sudo mkdir /sys/fs/cgroup/memory/pypi_to_0install
    sudo chown $USER /sys/fs/cgroup/memory/pypi_to_0install
    sudo mkdir /sys/fs/cgroup/blkio/pypi_to_0install
    sudo chown $USER /sys/fs/cgroup/blkio/pypi_to_0install

Either ensure the above cgroups exist or give the required sudo permissions to
the user running PyPI to 0install.

To run::

    . $repo_root/venv/bin/activate
    export PYTHONPATH="$repo_root"
    python $repo_root/pypi_to_0install/main.py

.. _install zero install: http://0install.net/injector.html
.. _install firejail: https://firejail.wordpress.com/download-2/
