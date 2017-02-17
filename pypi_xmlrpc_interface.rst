PyPI XMLRPC interface
=====================
This document clarifies some aspects of `PyPI's XMLRPC interface`_, which is
used for the conversion. 

While PyPI's metadata is structured, little input validation is performed. E.g.
some fields may be ``None``, ``''`` or something bogus such as ``UNKNOWN``
(`analyzing pypi metadata`_). E.g. author_email isn't required to be an email
adress.

The following is a non-exhaustive list of descriptions of the output of some of
the interface's commands:

- release_data:

  - name: the package name. This is not the `canonical name`_. You are required
    to use this name when requesting info through the interface, not the
    canonical name.

  - home_page: a URL.

  - license: a string such as ``GPL``, potentially has variations such as
    ``General Public License`` (and bogus values such as ``LICENSE.txt``).

  - summary: short description string

  - description: long description string in reStructuredText format

  - keywords: whitespace separated list of keywords as string

  - classifiers: list of `Trove classifiers`_, list of str.

  - release_url: the PyPI page corresponding to this version
  - package_url: the PyPI page of the latest version of this package

  - docs_url: if the package has hosted its documentation at PyPI, this URL
    points to it. Submitting documentation to PyPI has been deprecated (in
    favor of Read the Docs).

  - platform: do not use. It is tied to a version, but not to a download url
    (release_urls), so it can't be meaningful. E.g. for numpy it returns
    ``Windows`` while numpy is supported on Linux as well.

  - stable_version: `always empty string`_, useless.
  - requires, requires_dist, provides, provides_dist: seems these are not
    returned or are always empty

- release_urls:

  - packagetype:
    
    Meaning of the most common values:

    - sdist: source distribution
    - bdist_wheel: Python wheel
    - bdist_egg: Python egg, can be converted to a wheel
    - bdist_wininst: ``... bdist --format=wininst`` output, a self-extracting ZIP for Windows; but it can be converted to a wheel

  - python_version: unknown. Examples: ``source``, ``any``, ``py3``, ...

  - url: the download url

  - filename: file name of the download. For a wheel, this follows the `wheel
    file name convention`_. Eggs also follow a `file name convention <egg file
    name convention_>`_. Metadata such as which platform the download is for
    is missing, instead one has to derive it from the filename or download and
    inspect the binary.

.. _pypi's xmlrpc interface: https://wiki.python.org/moin/PyPIXmlRpc
.. _trove classifiers: http://www.catb.org/~esr/trove/
.. _analyzing pypi metadata: https://martin-thoma.com/analyzing-pypi-metadata/
.. _canonical name: https://www.python.org/dev/peps/pep-0503/#normalized-names
.. _always empty string: https://warehouse.pypa.io/api-reference/xml-rpc/
.. _wheel file name convention: https://www.python.org/dev/peps/pep-0491/#file-name-convention
.. _egg file name convention: https://svn.python.org/projects/sandbox/trunk/setuptools/doc/formats.txt
