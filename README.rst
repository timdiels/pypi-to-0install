Script that converts all PyPI packages to Zero Install feeds.

Resulting feeds have a source implementation which calls ``pip install .``.
Wheels are currently ignored.

Requirements:

- Python 3
- pip install -r requirements.txt  # in a venv

For a weekly conversion, see pypi_to_0install.github.io TODO

Documentation
-------------

Installation
^^^^^^^^^^^^
To install::

    git clone https://github.com/timdiels/pypi-to-0install.git
    cd pypi-to-0install
    wget https://downloads.sf.net/project/zero-install/0install/2.3.4/0install-2.3.4.tar.bz2
    tar -xaf 0install-2.3.4.tar.bz2
    mv 0install-2.3.4/zeroinstall .
    rm -rf 0install-2.3.4*  # cleanup, optional

Running
^^^^^^^
To run::

    export PYTHONPATH="$repo_root"
    python3 $repo_root/pypi_to_0install/main.py

python3 should be at least python 3.4.


Design
^^^^^^

- `PyPI XMLRPC interface <doc/pypi_xmlrpc_interface.rst>`_
- `Conversion: general <doc/conversion_general.rst>`_
- `Conversion: packagetype specifics <doc/conversion_packagetype_specifics.rst>`_
- `Developer guide <doc/developer_guide.rst>`_
