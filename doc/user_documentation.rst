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

python3 should be at least python 3.4.

Running
-------
To run::

    . $repo_root/venv/bin/activate
    export PYTHONPATH="$repo_root"
    python3 $repo_root/pypi_to_0install/main.py