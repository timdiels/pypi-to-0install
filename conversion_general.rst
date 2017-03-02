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
        <requires interface='https://pypi_to_zi_feeds.github.io/...' version='{version}' importance='{importance}' />
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

Dependencies are derived from the the distribution (``egg_info``: ``requires.txt``) as
this information is not available through PyPI's metadata (e.g.
``release_data['requires']`` is missing).  ``{importance}`` is ``essential`` if
the dependency is in ``install_requires`` and ``recommended`` otherwise
(``extras_require``).  ``{version}`` is the Python version ranges converted to
ZI version ranges. One tricky part is `conditional dependencies`_, for now the
conversion treats them as unconditional, though optional if in ``extras_require``.

Additional attributes and content of each ``<implementation>`` depends on the
`packagetype` of the corresponding `release_url`.

Version conversion
------------------
As `Python <python versioning_>`_ and `ZI versioning`_ schemes
differ, conversion is required. Given a Python version::

    [{epoch}!]{release}[{prerelease_type}{prerelease_number}][.post{post_number}][.dev{dev_number}]

Where:

- ``[]`` denotes optional part
- ``release := N(.N)*``, with ``N`` an integer
- ``prerelease_type := a|b|rc``

This is converted to::

    {epoch}-{release}[-{prerelease}][-post{post_number}][-{dev_number}]

Where:

- `epoch` is 0 if epoch segment was omitted
- when `prerelease_type` is:
  
  - ``a``, ``prerelease = pre0.{prerelease_number}``
  - ``b``, ``prerelease = pre1.{prerelease_number}``
  - ``rc``, ``prerelease = rc{prerelease_number}``

This conversion does not affect version ordering (**TODO** review this is true).

.. _trove classifiers: http://www.catb.org/~esr/trove/
.. _python versioning: http://0install.net/interface-spec.html#versions
.. _zi versioning: https://www.python.org/dev/peps/pep-0440/#version-scheme
.. _conditional dependencies: https://hynek.me/articles/conditional-python-dependencies/
