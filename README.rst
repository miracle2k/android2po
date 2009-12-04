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

babel > 0.9.4 (with context support; currently, this means using an SVN checkout)
    http://babel.edgewall.org/

lxml
    http://codespeak.net/lxml/

Since the .po files this script generates use contexts (``msgctx``),
that's what you're gettext software will have to support as well.


Installation
------------

    $ python setup.py install


To install the dependencies, in particular the SVN version of babel, you
can use ``pip``:

    $ pip install -r requirements.pip


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
need to be source controlled as well.

The script by default expects to be run from within a standard Android
project directory tree (identified by a ``AndroidManifest.xml`` at it's
root level), with a ``res`` directory holding the resources.
The .po files by default are stored in a root level ``locale`` directory
as ``locale/xx.po``.

You can specify both locations manually:

    $ a2po --android ../my-resources COMMAND

The script automatically process all the languages found in your resource
directory.

Initial setup
~~~~~~~~~~~~~

When switching to ``android2po``, you will first want to create an
initial export of your current translations.

    $ a2po --initial export

This will ignore any languages for which a ``.po`` file already exists.
You can use the ``--overwrite`` flag to force an initial export of the
XML files of all existing languages:

    $ a2po --overwrite export

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
find in your resource directory. To add a new language, create an
empty ``strings.xml`` at the appropriate location (e.g.
``values-XX/strings.xml`` file), and then run

    $ a2po --initial export

to generate a ``.po`` counterpart. Alternatively, you also can simply
copy the ``template.dot`` file the script also generates to the proper
``xx.po`` file manually.


Notes
-----

Initially based on:
    http://code.google.com/p/openintents/source/browse/tools/Androidxml2po/androidxml2po.bash