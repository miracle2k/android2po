android2po
==========

.. image:: https://github.com/miracle2k/android2po/workflows/Continuous%20integration/badge.svg

Convert Android string resources to gettext .po files, and import them
right back.

The goal is to remove as many syntax elements required by the Android
string resource files when exporting, to present the text to translators
in as easy a format as possible; and correctly writing everything back
to Android on import while keeping the generated XML files easily
readable as well (i.e. no unnecessary escaping).


Requirements
------------

The following Python modules are required, and will mostly be
auto-installed. See ``Installation`` below.

babel
    http://babel.pocoo.org/

lxml
    http://codespeak.net/lxml/

argparse
    http://argparse.googlecode.com/

Since the .po files this script generates use contexts (``msgctx``),
that's what you're gettext software will have to support as well.


Installation
------------

To install the current release, you can simply do:

    $ easy_install android2po

That's it!

If you want to install the current development version of
``android2po`` instead, get the source code, then run:

    $ python setup.py install

``setup.py`` should automatically install all the dependencies.
Alternatively, you can also use pip if you prefer:

    $ pip install -r requirements.pip

Usage
~~~~~

The basic idea is that:

* ``values/strings.xml`` holds the reference strings in their
  original language (the gettext ``msgid`` fields).

* The gettext .po files generated and updated by this script contain
  the reference version of the translations.

* The ``values-XX/strings.xml`` files are fully generated based on
  your ``.po`` files, and should not be modified manually.

In addition to your authoritative strings.xml file, you will usually 
also want to keep your .po files in source control; The generated 
language-specific ``strings.xml`` files then contain no additional 
information, and do not need to be source controlled, though you are 
free to if you like.

The environment
~~~~~~~~~~~~~~~

To be able to run, the script necessarily needs to know about two
filesystem locations: The directory where your Android resources are
located, and the directory where the gettext .po files should be stored:

    $ a2po COMMAND --android myproject/res --gettext myproject/locale

However, to simplify usage, the program will automatically try to
detect the location of these folders, as follows:

* It will search the directory hierarchy, starting with the your working
  directory, for a ``AndroidManifest.xml`` or ``.android2po`` file.
* As soon as it finds either of those files, it will stop, and consider
  the it's location the **project directory**.
* Unless explicitly overriden by you, it will place the .po files in
  a subdirectory ``./locale`` of that project directory.
* Only if a ``AndroidManifest.xml`` file is in the project directory
  will it assume that the Android resources are located in a subfolder
  named ``./res``.
* If a ``.android2po`` file is in the project directory, it automatically
  will be loaded as a configuration file. See the section below on the
  format of the configuration file, and possible values.
* The script automatically processes all the languages it can find. It
  will normally look at the existing .po files to determine the list of
  languages, with the exception of the ``init`` command, in which case
  the list of languages inside the Android resource directory will be
  used.

Initial setup
~~~~~~~~~~~~~

When switching to ``android2po``, you will first want to create an
initial export of your current translations.

    $ a2po init

This will ignore any languages for which a ``.po`` file already exists.

For testing purposes, you may want to immediately import the generated
files back in, to compare with what you originally had, and make sure
the script was able to process your files correctly.
At this point, make sure you have a backup, since your language-specific
``strings.xml`` files are going to be replaced (you are using source
control, right?!)::

    $ a2po import
    $ git diff --ignore-all-space res/values-XX/strings.xml

In the example above, ``git`` is used for source control. ``git``
provides a nice option to show a diff while ignoring whitespace
changes, which will make it much easier to spot problems with the
import. If you use a different tool, see if there is a comparable
feature.

Hopefully, your translated XML files at this point hold the same
information as before. The whitespace will probably have changed,
comments will have been removed, and some strings may have changed
visually (i.e. use different escaping). However, their *meaning*
should not have changed. If it has, please report a bug.

Updating
~~~~~~~~

After hacking on your code for a while, you have changed some
strings (in your authoritative ``values/strings.xml`` file), and now
you need to pass those on to your translators through your .po files.

Simply do:

    $ a2po export

This will update your ``.po files`` with your changes.

Importing
~~~~~~~~~

Your translators have come back to you with their changes, and you
want to include them in the next build. Simply do:

    $ a2po import

This will fully regenerate your language-specific ``strings.xml``
based on the gettext ``.po`` files.

You can do this step manually, or add it to your build process.

Adding a new language
~~~~~~~~~~~~~~~~~~~~~

As noted above, ``android2po`` will automatically process all the
languages it can find, based on the .po files that exist. To add a
new language, simply run

    $ a2po init {LANGUAGE CODES}

For example:

    $ a2po init de fr

This will create both new .po and strings.xml files for German and French.

You are also free to simply create the appropriate ``strings.xml`` files
yourself, and let

    $ a2po init

initialize their proper .po counterparts (in case of the ``init`` command,
the languages found in the Android resource directory will be processed).


Configuration file
~~~~~~~~~~~~~~~~~~

A configuration file can be used to avoid manually specifying all the
required options. The format of the file is simply a list of command
line option, each specified on a line of it's own. For example::

    --no-template
    # Paths - don't specify --android, default location is used.
    --gettext ../locale

As you can see, comments are supported by using ``#``, and the mechanism
to automatically try to detect the directories for .po files and Android
``strings.xml`` files is still in place if you don't specify locations
explicitly.

The configuration file may be specified by using the ``--config`` option.
Alternatively, if a ``.android2po`` file is found in the project directory,
it will be used.

See ``--help`` for a list of possible configuration options. There's also
an example configuration file in ``example.config`` that you can have a
look at, or use as a template for your own.


Plurals support
~~~~~~~~~~~~~~~

``<plurals>`` are supported, but merit some additional explanation.

Android's plural support is based on CLDR_ keywords like ``"one"`` and
``"many"``. The rules specifying which quantity ``n`` maps to which keyword
are built into Android itself, by way of the CLDR database. It is important to
understand that a keyword like "one" may be used for quantities other then
``1``.

In the gettext system, on the other hand, each catalog has the ability to
define the plural rules it wants to use itself, via an expression like
``nplurals=2; plural=((n == 1) ? 0 : 1)``. The expression returns the index
of the string to use for the quantity ``n``.

android2po converts between those two system in the following way:

* When writing .po files, it will generate a plural rule expression like
  above based on the CLDR data, custom-fit for the language in question.
  The result is a .po file that defines as many plural forms as required
  for the language, and your translation tool will ask for a different
  string for each plural form.

* During import, it will generate a ``<plurals>`` tag with the correct quantity
  keywords based on it's knowledge (CLDR) about which such keywords the
  language supports.

* The ``init`` command, having to convert existing ``<plurals>`` tags to
  gettext, will pick those quantity keywords the language supports, and ignore
  others (and display a warning in those cases).

* The ``export`` command will ensure that the catalog uses the correct plural
  definition, but it otherwise does not have to deal with individual plural
  forms / quantities.

If this is confusing, consider the issue: Android lets you define a number
of different quantity keywords for each ``<plurals>`` element, but ignores all
keywords that are not supported by the language (see `this erroneous bug
report <http://code.google.com/p/android/issues/detail?id=8287>`_).
gettext only allows you to define a fixed number of plural rules, as many
as the language purports to require via the catalog's plural rule expression.

To cleanly convert between the two systems, we are forced to ignore keywords
in an Android XML resource that are really not supported - but only if Android
itself would also ignore them. So view this as essentially a validation
feature.

A final note: plurals can be complex (and there are many languages) and the
CLDR database is regularly updated. In French, whether 0 is treated as plural
or singular possibly even `depends on the dialect
<https://developer.mozilla.org/en/Localization_and_Plurals>`_. As
such, you may find that different plural rules for the same languages are in
use in the wild. ``android2po`` uses the CLDR rules, but not necessarily the
same version as Android does, and Android presumably will upgrade their CLDR
version over time as well. I think the goal here would be to always make
``android2po`` use a reasonably recent version of the CLDR data, and accept
that old Android versions with outdated plural information might not be able
to correctly internationalize some plural strings into into those languages
where the data is incorrect.

Further reading:

The CLDR plural system and rules
    http://unicode.org/repos/cldr-tmp/trunk/diff/supplemental/language_plural_rules.html
    http://cldr.unicode.org/index/cldr-spec/plural-rules

Plural information about various languages:
    http://translate.sourceforge.net/wiki/l10n/pluralforms
    https://translations.launchpad.net/+languages
    https://developer.mozilla.org/en/Localization_and_Plurals

.. _CLDR: http://cldr.unicode.org/index/cldr-spec/plural-rules



Understanding / Debugging the android2po
----------------------------------------

If something doesn't work as expected, it may be helpful to understand
which files are processed how and when:

On ``init``, ``android2po`` will take your language-neutral (English)
``values/strings.xml`` file and convert it to a .pot template.

Further on ``init``, if there are existing ``values-{lang}/strings.xml`` files,
it will take the strings from there, match them with the strings in the
language-neutral ``values/strings.xml`` file, and generate .po files for these
languages which already contain translations, in addition to the template.
This is the **only** time that the ``values-{lang}/strings.xml`` files will
be looked at and considered.

On ``export``, ``android2po`` will take the language-neutral
``values/strings.xml`` file, generate a new .pot template, and then merge the
new template into any existing .po catalogs, i.e. update the .po catalogs for
each language with the changes. This is how gettext normally works
(``msgmerge``). The ``values-{lang}/strings.xml`` files do not play a role here.

On 'import', ``android2po`` will only look at the .po catalogs for each
language and generate ``values-{lang}/strings.xml`` files, without looking at
anything else.



Notes
-----

Initially based on:
    http://code.google.com/p/openintents/source/browse/tools/Androidxml2po/androidxml2po.bash


Links of interest:
~~~~~~~~~~~~~~~~~~

http://www.gnu.org/software/hello/manual/gettext/PO-Files.html
    GNU PO file format docs.

http://docs.oasis-open.org/xliff/v1.2/xliff-profile-po/xliff-profile-po-1.2.html
    Explains the gettext format according to how xliff interprets it.

http://www.artfulbits.com/Android/aiLocalizer.aspx
    App to localize Android xml string files directly. They seems to be
    involved with the Ukrainian translation of Android itself.

http://groups.google.com/group/android-platform/browse_thread/thread/a2626195205e8543
    Notes that Google internally manages Android translations in their
    own system.

    There is a converter from and to XLIFF in ``frameworks/base/tools/localize``,
    which might be what they are using. It looks pretty decent too. Why
    isn't this promoted more?

https://launchpad.net/intltool
    Converts to and from .po und "can be extended to support other types
    of XML" - sounds like something we could've used? It's Perl though,
    ugh.
