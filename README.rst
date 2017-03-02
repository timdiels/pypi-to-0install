Script that converts all PyPI packages to Zero Install feeds.

Resulting feeds have a source implementation which calls ``pip install .``.
Wheels are currently ignored.

Requirements:

- Python 3
- pip install -r requirements.txt  # in a venv

For a weekly conversion, see pypi_to_0install.github.io TODO

Documentation
-------------
Design:

- `PyPI XMLRPC interface <pypi_xmlrpc_interface.rst>`_
- `Conversion: general <conversion_general.rst>`_
- `Conversion: packagetype specifics <conversion_packagetype_specifics.rst>`_
- `Developer guide <developer_guide.rst>`_
