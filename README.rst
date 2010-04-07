android2po
==========

Convert Android string resources to gettext .po files, and import them
right back.

The goal is to remove as many syntax elements required by the Android
string resource files when exporting, to present the text to translators
in as easy a format as possible; and correctly writing everything back
to Android on import while keeping the generated XML files easily
readable as well (i.e. no unnecessary escaping).


Requirements
------------

The following Python modules are required, but will mostly be
auto-installed. See ``Installation`` below.

babel >= 1.0dev (only the dev version has support for contexts)
    http://babel.edgewall.org/

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

Note: The development version of babel is required. Installing the
dev version is a bit complicated than usually, so both the ``setup.py``
file and the ``requirements.pip`` file link to a custom distribution
I made for android2po. If you prefer to install the babel SVN version
yourself, you need to follow the instructions on this page:

    http://babel.edgewall.org/wiki/SubversionCheckout

Usage
~~~~~

The basic idea is that:

* ``values/strings.xml`` holds the reference strings in their
  original language (the gettext ``msgid`` fields).

* The gettext .po files generated and updated by this script contain
  the reference version of the translations.

* The ``values-XX/strings.xml`` files are fully generated based on
  your ``.po`` files, should not be modified manually.

Aside from your authority strings.xml file, you usually will want to keep
your file .po files in source control; The generated language-specific
``strings.xml`` files then contain no additional information, and do not
need to be source controlled, though you are free to if you like.

The environment
~~~~~~~~~~~~~~~

Two be able to run, the script necessarily needs to know about two
filesystem locations: The directory where your Android resources are
located, and the directory where the gettext .po files should be stored:

    $ a2po --android myproject/res --gettext myproject/locale COMMAND

However, to make things easier, the program will automatically try to
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
* The script automatically processes all the languages found in the
  Android resource directory.

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
control, right?!):

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
strings (in your authority ``values/strings.xml`` file), and now
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

As noted above, ``android2po`` will only process languages it can
find in your resource directory. To add a new language, simply run

    $ a2po init {LANGUAGE CODES}

For example:

    $ a2po init de fr

This will create both new .po and strings.xml files for German and French.

Of course, you are also free to simply create the appropriate
``strings.xml`` files yourself, and let

    $ a2po init

initialize their proper .po counterparts.


Configuration file
~~~~~~~~~~~~~~~~~~

A configuration file can be used to avoid manually specifying all the
required options. The format of the file is simply a list of command
line option, each specified on a line of it's own. For example:

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