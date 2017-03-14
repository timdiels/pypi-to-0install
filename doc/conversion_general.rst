Conversion: general
===================
This details how PyPI packages are converted to ZI feeds. Parts specific to the
`packagetype` (sdist, wheel, ...) are detailed in the other conversion pages.
I will use shorthands such as ``release_data['summary']`` throughout the text
(instead of ``release_data(...)['summary']``) to refer to the PyPI XMLRPC
interface.

We will refer to a PyPI project as a package (e.g. numpy; this follows PyPI's
terminology) and its downloads as distributions (e.g. an sdist/wheel of numpy).

Overview
--------
This pseudo-feed gives an overview of the conversion (end tags omitted)::

    <interface>
      <name>{canonical_name(release_data['name'])}
      <summary>{release_data['summary']}
      <homepage>{release_data['home_page']}
      <description>{pandoc(release_data['description'], from=rst, to=txt)}
      <category type={uri_to_trove_namespace}>{release_data['classifiers'][i]}
        ...
      <needs-terminal/> iff ``Environment :: Console`` in classifiers

      <implementation 
        id={release_urls['path']}
        version={converted_version}
        released={format(release_urls['upload_time'], 'YYYY-MM-DD')}
        stability={stability}
        langs={langs}
        license={license}
        ...
      >
        <requires interface='https://pypi_to_zi_feeds.github.io/...' importance='{importance}' />
        ...

Where::

    def canonical_name(pypi_name):
        re.sub(r"[-_.]+", "-", pypi_name).lower()

Here, ``release_data`` refers to the release data of the newest release/version
of the package.

The description is converted from reST to plain text.

Categories are `Trove classifiers`_.

**TODO** What's the format of the xml file describing the categories?  Need
more info before I can convert Trove database into what's expected by ZI (or
find something existing).

For the meaning of ``{converted_version}``, see the `Version conversion`_ section
below.

``{stability}`` is ``developer`` if Python version has a ``.dev`` segment. Else, if
the version contains a prerelease segment (``.a|b|rc``), stability is
``testing``. Otherwise, stability is ``stable``.

``{langs}`` is derived from ``Natural Language ::`` classifiers.

``{license}`` is a Trove classifier. If ``License ::`` is in classifiers, it is
used. If there are multiple, pick one in a deterministic fashion. If none, try
to derive it from ``release_data['license']``.  If none or its value is not
understood, try to derive it from a ``LICENSE.txt``. If no such file, omit
the license attribute.

For ``<requires ...>...``, see `dependency conversion`_ below.

Additional attributes and content of each ``<implementation>`` depends on the
`packagetype` of the corresponding `release_url`.

Version conversion
------------------
As `Python <python versioning_>`_ and `ZI versioning`_ schemes
differ, conversion is required. Given a Python conversion, we convert it to a
normalised Python version (via `packaging.version.parse`_), which gives us::

    {epoch}!{release}[{prerelease_type}{prerelease_number}][.post{post_number}][.dev{dev_number}]

Where:

- ``[]`` denotes optional part
- ``release := N(.N)*``, with ``N`` an integer
- ``prerelease_type := a|b|rc``
- ``epoch, prerelease_number, post_number, dev_number`` are non-negative
  numbers

This is converted to the ZI version::

    {epoch}-{stripped_release}-{modifiers}

Where:

- ``stripped_release`` is ``release`` with trailing ``.0`` components trimmed
  off. This is necessary due to ``1 < 1.0`` in ZI, while ``1 == 1.0`` in
  Python.

- ``modifiers`` is a list of up to 3 modifiers where prereleases, post and dev
  segments are considered modifiers. Modifiers are joined by ``-``, e.g.
  ``{modifiers[0]}-{modifier[1]}``. A modifier is formatted as::

      {type}.{number}

  where:

  - ``type`` is a number derived from this mapping::

        types = {
          'dev': 0,
          'a': 1,
          'b': 2,
          'rc': 3,
          'post': 5,
        }

  - ``number`` is one of ``prerelease_number``, ``post_number``,
    ``dev_number``, depending on the modifier type.

  When a version has less than the maximum amount of modifiers, i.e. less than
  3, an empty modifier (``-4``) is appended to the list. This ensures
  correct version ordering.

  Some examples of modifier conversion::

      a10.post20.dev30 -> 1.10-5.20-0.30
      b10.dev30 -> 2.10-0.30-4
      post20.dev30 -> 5.20-0.30-4
      dev30 -> 0.30-4
      rc10 -> 3.10-4

For examples of the whole conversion, see `test_convert_version`_.

This conversion does not change version ordering.

Dependency conversion
---------------------
Dependencies are derived from the the distribution (``egg_info``:
``requires.txt`` and ``depends.txt``) as this information is not available
through PyPI's metadata (e.g.  ``release_data['requires']`` is missing).
``{importance}`` is ``essential`` if the dependency is in ``install_requires``
and ``recommended`` otherwise (``extras_require``).

Python packages allow for optional named groups of dependencies called extras.
Further, Python dependencies can be `conditional <conditional dependencies_>`_
(by using `environment markers`_). If a dependency is either conditional or
appears in extras_require, it is added as a recommended dependencies in the
converted feed, else it is added as a required dependency. Note that Zero
Install tries to select all recommended dependencies, but does not fail to
select the depending interface when one of its recommended dependencies cannot
be selected.

For example::

  install_requires = ['dep1 ; python_version<2.7', 'dep2==3.*']
  extras_require = {
      ':python_version<2.7': ['install_requires_dep'],
      'test:platform_system=="Windows"': ['pywin32'],  # only on windows
      'test': ['somepkg'], # regardless of platform
      'special_feature': ['dep2>=3.3,<4'], # regardless of platform
  }

is converted to::

    <implementation ...>
      <requires interface='.../feeds/dep1.xml' importance='recommended' />
      <requires interface='.../feeds/dep2.xml' importance='required' version='{constraints}' />
      <requires interface='.../feeds/install_requires_dep.xml' importance='recommended' />
      <requires interface='.../feeds/pywin32.xml' importance='recommended' />
      <requires interface='.../feeds/somepkg.xml' importance='recommended' />

where ``{constraints}`` are all Python version specifiers converted to a ZI
version expression.

.. _trove classifiers: http://www.catb.org/~esr/trove/
.. _python versioning: https://www.python.org/dev/peps/pep-0440/#version-scheme
.. _zi versioning: http://0install.net/interface-spec.html#versions
.. _conditional dependencies: https://hynek.me/articles/conditional-python-dependencies/
.. _environment markers: https://www.python.org/dev/peps/pep-0508/
.. _test_convert_version: https://github.com/timdiels/pypi-to-0install/blob/master/pypi_to_0install/tests/test_version.py#L30
.. _packaging.version.parse: https://packaging.pypa.io/en/latest/version/#packaging.version.parse
