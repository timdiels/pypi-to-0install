Conversion: Packagetype specifics
=================================
This documents the parts of the conversion that depend on the `packagetype` of
each download (from ``release_urls``). These only affect ``<implementation>``.
There can be multiple download urls for the same version, each can have a
different `packagetype`.

Currently, only source distributions are supported.

Generally, a ``<manifest-digest>`` requires downloading and unpacking the archive.
In doing so, the download's md5sum is compared to ``release_urls['md5_digest']``.

Python distributions, installation
----------------------------------
Generally, a Python distribution (the download from ``release_urls``) is an
archive/executable which installs:

- Platform independent Python code into a location in ``PYTHONPATH``.

- Platform dependent libraries, such as extension modules, into ``PYTHONPATH``.

- Python scripts (`according to distutils <distutils scripts_>`_). These are
  added to ``PATH``. Some of these are stored as files in the distribution,
  others are generated from ``entry_points`` metadata.
  
  Upon build (``python setup.py build_scripts``), the stored scripts are copied
  and their shebang is edited to point to the python interpreter used for the
  build (this is an absolute path).

  Only upon installation, are scripts generated from ``entry_points``.

- Data files as specified by ``data_files`` in ``setup.py``. This does not
  include ``package_data`` files, those are placed next to the Python source
  files. ``data_files`` can have both absolute and relative destination paths.
  
  Files with a relative destination path can end up being installed anywhere
  and the application/library has no way of finding out where these data files
  have been installed; as such we can safely ignore these files in converting
  to ZI.
  
  Files with an absolute destination path will be installed to a predictable
  location and so the application/library can depend on them. However, making
  this possible in ZI would require a layered file system to make the file
  appear installed (e.g. a destination in /etc) without modifying global state.
  This is not currently supported.  I expect there are few popular packages, if
  any, which use this.
  
  Bottom line: the conversion drops ``data_files``. (``package_data`` is still
  included!)

- C/C++ header files.

pyc files
^^^^^^^^^
Normally, when installed, py files are compiled to pyc files.  These are
specific to the Python version and implementation (e.g. CPython 3.6).
Having pyc files in our binary ZI implementation would restrict its reusability
to ``os-cpu-python_implementation-python_implementation_version``, i.e. it
kills reuse. So, pyc files are not included in implementations.

When Python imports a package, it tries to write a pyc file if missing. This
pyc file is written (in a `__pycache__` directory) near the py file. There is
no way of writing pyc files to a different location. All these pyc writes
result in permission errors as the 0store cache is read-only.

This means we either generate highly platform-specific ZI implementations or
have no pyc files. According to #python, the lack of pyc files results in an
unnoticeable performance hit on startup time.

The permission errors can be avoided by setting the environment var
``PYTHONDONTWRITEBYTECODE=true``.

As such, we disable pyc file generation on installation and set
``PYTHONDONTWRITEBYTECODE``.


Source distribution
-------------------
A source distribution (``release_urls['packagetype'] == 'sdist'``) is a tgz/zip
containing at least a ``setup.py``. The preferred way to install these is with
pip.

After unpacking the distribution, it can be installed without affecting global
state like so::

    pip install \
      --install-option="--install-purelib=/lib" \
      --install-option="--install-platlib=/lib" \
      --install-option="--install-headers=/headers" \
      --install-option="--install-scripts=/scripts" \
      --install-option="--install-data=/data" \
      --root "$PWD/install" \
      --no-deps .

``--root`` prevents installing outside the install directory; this mainly
counters counter ``data_files`` with absolute paths.

The resulting dir contains:

lib
  - Cross platform 'libraries': Python source and pyc files, egg-info
    directories, package_data files, ...
  - Platform specific libraries such as Python extension modules.
scripts
  Python scripts with a shebang that points by absolute path to the python used
  by pip. This includes generated scripts.
headers
  C/C++ headers. Unused.
data
  Data files from ``data_files`` with relative destination paths. Unused.
\*
  Data files from ``data_files`` with absolute destination paths. Unused.

The source implementation as pseudo-code (extends the ``<implementation>`` from
`Conversion: general <conversion general_>`_)::

    <implementation arch='*-src'>
      <archive href='{release_urls['url']}' size='{release_urls['size']}' />
      <command name='compile' ...>
        ...
        <compile:implementation arch='*-*'>
          <archive href='{release_urls['url']}' size='{release_urls['size']}' />
          <environment name='PYTHONPATH' insert='{lib}' />
          <environment name='PATH' insert='{scripts}' />
          <environment name='PYTHONDONTWRITEBYTECODE' value='true' mode='replace' />

For now, some requirements are omitted from the compiled implementation (it may
be easier to tackle them when real life cases arise where this forms a problem):

- For example, the NumPy package does not work on PyPy. One way to add this
  constraint is ``<restricts interface=PyPy version='0'>`` where version 0 does
  not exist.
  
- `script generation`_ depends on ``os.name=posix|java|nt`` and
  ``sys.platform.startswith('java')``. It appears it is not possible to express
  this in ZI currently. Though, instead of expressing it in ZI, we should
  instead generate our own cross-platform scripts.

- The Python code itself could be platform dependent. This could be derived
  from classifiers; but these are often omitted and one can doubt the
  correctness of those that do list it.  In this case, it may be better to be
  too lenient rather than too restrictive.
  
- extension modules require a certain os-cpu architecture (and perhaps an ABI
  unless that's standardised by a PEP). When these are present, ``os-cpu``
  should be set

Wheel
-----
Not supported.

Notes:

- ``release_urls['packagetype'] == 'bdist_wheel'``

- can derive `arch` from ``release_urls['filename']``. See the `PyPI XMLRPC
  interface notes`_.

- bdist_egg and bdist_wininst can be converted to a wheel

- Wheels cannot be used as binary ZI implementation as scripts need to be
  generated for ``entry_points``.

- ``release_urls['python_version']`` should be used to restrict which python
  interpreters and versions may be used; if it's not already mentioned in the
  wheel name.

Egg
---
Not supported.

Notes:

- ``release_urls['packagetype'] == 'bdist_egg'``

- can derive `arch` from ``release_urls['filename']``. See the `PyPI XMLRPC
  interface notes`_ (follow the link to the egg file
  name convention and search it for "Filename-Embedded Metadata").

- for an example of eggs, see the pymongo project on PyPI

- Eggs cannot be used as binary ZI implementation as scripts need to be
  generated for ``entry_points``.

.. _distutils scripts: https://docs.python.org/2/distutils/setupscript.html#distutils-installing-scripts
.. _pkg_resources.resource_stream: http://setuptools.readthedocs.io/en/latest/pkg_resources.html#basic-resource-access
.. _script generation: https://github.com/pypa/pip/blob/403e398330c8e841e4633aceda859430f5f7b913/pip/_vendor/distlib/scripts.py
.. _PyPI XMLRPC interface notes: pypi_xmlrpc_interface.html
.. _conversion general: conversion_general.html
