User documentation
==================
   
Installation
------------
To install::

    git clone https://github.com/timdiels/pypi-to-0install.git
    cd pypi-to-0install
    python3 -m venv venv && . venv/bin/activate
    pip install -r requirements.txt
    wget https://downloads.sf.net/project/zero-install/0install/2.3.4/0install-2.3.4.tar.bz2
    tar -xaf 0install-2.3.4.tar.bz2
    mv 0install-2.3.4/zeroinstall .
    rm -rf 0install-2.3.4*  # cleanup, optional

python3 should be at least python 3.5. You also need to `install Zero Install`_
such that ``0install`` is available on ``$PATH``.

Lastly, the default GPG key will be used to sign feeds. If you don't have one,
create it with ``gpg --gen-key``; do not use your real name, use something like
"PyPI to 0install" to indicate this was signed by an algorithm, not by you
personally. If you do not want to mess up your main GPG configuration, make a
new GPG home directory first and point the environment var ``GNUPGHOME`` to it.
To use a different key, set ``default-key {key_name}`` in
``$GNUPGHOME/gpg.conf``.

Running
-------
To run::

    . $repo_root/venv/bin/activate
    export PYTHONPATH="$repo_root"
    python3 $repo_root/pypi_to_0install/main.py
    
.. _install zero install: http://0install.net/injector.html
