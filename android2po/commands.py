from __future__ import absolute_import

import os
from os import path
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from lxml import etree
from babel.messages import pofile, Catalog
from babel.core import UnknownLocaleError

from . import convert
from .env import Language
from .termcolors import colored


__all__ = ('CommandError', 'ExportCommand', 'ImportCommand', 'InitCommand',)


class CommandError(Exception):
    pass


def read_catalog(filename, **kwargs):
    """Helper to read a catalog from a .po file.
    """
    file = open(filename, 'rb')
    try:
        return pofile.read_po(file, **kwargs)
    finally:
        file.close()


def catalog2string(catalog, **kwargs):
    """Helper that returns a babel message catalog as a string.

    This is a simple shortcut around pofile.write_po().
    """
    sf = StringIO.StringIO()
    pofile.write_po(sf, catalog, **kwargs)
    return sf.getvalue()


def xml2string(xmldom):
    """Helper that returns the DOM of an XML as a string.

    TODO: It would be cool if this could try to recreate the formatting
    of the original xml file.
    """
    ENCODING = 'utf-8'
    return etree.tostring(xmldom, xml_declaration=True,
                          encoding=ENCODING, pretty_print=True)


def xml2po(env, *a, **kw):
    """Wrapper around the base xml2po() that uses the filters configured
    by the environment.
    """
    def xml_filter(name):
        for filter in env.config.ignores:
            if filter.match(name):
                return True
    kw['filter'] = xml_filter
    return convert.xml2po(*a, **kw)


def po2xml(env, *a, **kw):
    """Wrapper around the base po2xml() that uses the filters configured
    by the environment.
    """
    def po_filter(message):
        if env.config.ignore_fuzzy and message.fuzzy:
            return True
    kw['filter'] = po_filter
    return convert.po2xml(*a, **kw)


def get_catalog_counts(catalog):
    """Return 3-tuple (total count, number of translated strings, number
    of fuzzy strings), based on the given gettext catalog.
    """
    # Make sure we don't count the header
    return (len(catalog),
            len([m for m in catalog if m.string and m.id]),
            len([m for m in catalog if m.string and m.id and m.fuzzy]))


def ensure_directories(cmd, path):
    """Ensure that the given directory exists.
    """
    # Collect all the individual directories we need to create.
    # Yes, I know about os.makedirs(), but I'd like to print out
    # every single directory created.
    needs_creating = []
    while not path.exists():
        if path in needs_creating:
            break
        needs_creating.append(path)
        path = path.dir

    for path in reversed(needs_creating):
        cmd.w.action('mkdir', path)
        os.mkdir(path)


def write_file(cmd, filename, content, update=True, action=None,
               ignore_exists=False):
    """Helper that writes a file, while sending the proper actions
    to the command's writer for stdout display of what's going on.

    ``content`` may be a callable. This is useful if you would like
    to exploit the ``update=False`` check this function provides,
    rather than doing that yourself before bothering to generate the
    content you want to write.

    When ``update`` is not set, then if the file already exists we don't
    change or overwrite it.

    If a Writer.Action is given in ``action``, it will be used to print
    out messages. Otherwise, a new action will be started using the
    filename as the text. If ``action`` is ``False``, nothing will be
    printed.
    """
    if action is None:
        action = cmd.w.begin(filename)

    if filename.exists():
        if not update:
            if ignore_exists:
                # Downgade level of this message
                action.update(severity='info')
            action.done('exists')
            return False
        else:
            old_hash = filename.hash()
    else:
        old_hash = None

    ensure_directories(cmd, filename.dir)

    f = open(filename, 'wb')
    try:
        if callable(content):
            content = content()
        f.write(content)
        f.flush()
    finally:
        f.close()

    if not action is False:
        if old_hash is None:
            action.done('created')
        elif old_hash != filename.hash():
            action.done('updated')
        else:
            # Note that this is merely for user information. We
            # nevertheless wrote a new version of the file, we can't
            # actually determine a change without generating the new
            # version.
            action.done('unchanged')
    return True


class Command(object):
    """Abstract base command class.
    """

    def __init__(self, env, writer):
        self.env = env
        self.w = writer

    @classmethod
    def setup_arg_parser(cls, argparser):
        """A command should register it's sub-arguments here with the
        given argparser instance.
        """

    def execute(self):
        raise NotImplementedError()


class InitCommand(Command):
    """The init command; to initialize new languages.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        parser.add_argument('language', nargs='*',
                            help='Language code to initialize. If none given, all '+
                            'languages lacking a .po file will be initialized.')

    def generate_templates(self, update=True):
        """Generate the .pot templates. Returns the catalog objects as a
        kind -> catalog dict.

        TODO: Write a test that this happens during both the "export"
        and the "init" command (the latter is new).
        """
        env = self.env
        default_catalogs = {}
        something_written = False
        for kind in self.env.xmlfiles:
            template_pot = self.env.default.po(kind)
            if not env.config.no_template:
                action = self.w.begin(template_pot)
            default_catalog = xml2po(self.env, self.env.default.xml(kind))
            default_catalogs[kind] = default_catalog
            if not env.config.no_template:
                # Note that this is always rendered with "ignore_exists",
                # i.e. we only log this action if we change the template.
                if write_file(self, template_pot,
                              content=lambda: catalog2string(default_catalog),
                              action=action, ignore_exists=True, update=update):
                    something_written = True
        return default_catalogs, something_written

    def generate_po(self, target_po_file, default_data, language_data=None,
                    language_data_files=None, update=True, ignore_exists=False):
        """Helper to generate a .po file.

        ``default_data`` is the collective data from the language neutral XML
        files, and this is what the .po we generate will be based on.

        ``language_data`` is collective data from the corresponding
        language-specific XML files, in case such data is available.

        ``language_data_files`` is the list of files that ``language_data``
        is based upon. This is because in some cases multiple XML files
        might need to be combined into one gettext catalog.

        If ``update`` is not set than we will bail out early
        if the file doesn't exist.
        """
        action = self.w.begin(target_po_file)

        # This is a function so that it only will be run if write_file()
        # actually needs it.
        def make_catalog():
            if language_data is not None:
                action.message('Using existing translations from %s' % ", ".join(
                    [l.rel for l in language_data_files]))
                lang_catalog, unmatched = xml2po(self.env, default_data,
                                                 language_data)
                if unmatched:
                    action.message("Existing translation XML files for this "
                                   "language contains strings not found in the "
                                   "default XML files: %s" % (", ".join(unmatched)))
            else:
                action.message('No corresponding XML exists, generating catalog '+
                               'without translations')
                lang_catalog = xml2po(self.env, default_data)

            catalog = catalog2string(lang_catalog)

            num_total, num_translated, _ = get_catalog_counts(lang_catalog)
            action.message("%d strings processed, %d translated." % (
                num_total, num_translated))
            return catalog

        return write_file(self, target_po_file, content=make_catalog,
                          action=action, update=update,
                          ignore_exists=ignore_exists)

    def _iterate(self, language, require_translation=True):
        """Yield 4-tuples in the form of: (
            target .po file,
            source xml data,
            translated xml data,
            list of files translated xml data was read from
        )

        This is implemeted as a separate iterator so that later on we can
        also support a mechanism in which multiple xml files are stored in
        one .po file, i.e. on export, multiple xml files needs to be able
        to yield into a single .po target.
        """
        for kind in self.env.xmlfiles:
            language_po = language.po(kind)
            language_xml = language.xml(kind)

            language_data = None
            if not language_xml.exists():
                if require_translation:
                    # It's easily possible that say a arrays.xml only
                    # exists in values/, but not in values-xx/.
                    self.w.action('skipped', language_po)
                    self.w.message('%s doesn\'t exist' % language_po.rel)
                    continue
            else:
                language_data = convert.read_xml(language_xml)

            template_data = convert.read_xml(self.env.default.xml(kind))
            yield language_po, template_data, language_data, [language_xml]

    def execute(self):
        env = self.env

        if env.options.language:
            languages = []
            for code in env.options.language:
                languages.append(Language(code, env))
        else:
            languages = env.languages

        # First, make sure the templates exist. This makes the "init"
        # command everything needed to boostrap.
        _, something_done = self.generate_templates(update=False)

        # Only show [exists] actions if a specific language was requested.
        show_exists = not bool(env.options.language)

        for language in languages:
            # For each language, generate a .po file. In case a language
            # already exists (that is, it's xml files exist, use the
            # existing translations for the new gettext catalog).
            for (target_po,
                 template_data,
                 lang_data,
                 lang_files) in self._iterate(language, require_translation=False):
                if self.generate_po(target_po, template_data, lang_data, lang_files,
                                    update=False,
                                    ignore_exists=show_exists):
                    something_done = True

            # Also for each language, generate the empty .xml resource files.
            # This will make us pick up the language on subsequent runs.
            for kind in self.env.xmlfiles:
                if write_file(self, language.xml(kind),
                              """<?xml version='1.0' encoding='utf-8'?>\n<resources>\n</resources>""",
                              update=False, ignore_exists=show_exists):
                    something_done = True

        if not something_done:
            self.w.action('info', 'Nothing to do.', 'default')


class ExportCommand(InitCommand):
    """The export command.

    Inherits from ``InitCommand`` to be able to use ``generate_templates``.
    Both commands need to write the templates.
    """

    def execute(self):
        env = self.env
        w = self.w

        # First, always update the template files. Note that even if
        # template generation is disabled, we still need to have the
        # catalogs at least in memory for the updating process later on.
        #
        # TODO: Should this really be generated in every case, or do we
        # want to enable the user to set fixed meta data, and simply
        # merge subsequent updates in?
        default_catalogs, _ = self.generate_templates()

        initial_warning = False

        for language in env.languages:
            for kind in self.env.xmlfiles:
                target_po = language.po(kind)
                if not target_po.exists():
                    w.action('skipped', target_po)
                    w.message('File does not exist yet. '+
                              'Use the \'init\' command.')
                    initial_warning = True
                    continue

                action = w.begin(target_po)
                # If we do not provide a locale, babel will consider this
                # catalog a template and always write out the default
                # header. It seemingly does not consider the "Language"
                # header inside the file at all, and indeed deletes it.
                # TODO: It deletes all headers it doesn't know, and
                # overrides others. That sucks.
                try:
                    lang_catalog = read_catalog(target_po, locale=language.code)
                except UnknownLocaleError:
                    action.done('failed', status='%s is not a valid locale' % language.code)
                else:
                    lang_catalog.update(default_catalogs[kind])
                    # TODO: Should we include previous?
                    write_file(self, target_po,
                               catalog2string(lang_catalog, include_previous=False),
                               action=action)

        if initial_warning:
            print ""
            print colored("Warning: One or more .po files were skipped "+\
                  "because  they did not exist yet. Use the 'init' command "+\
                  "to generate them for the first time.",
                  fg='magenta', opts=('bold',))


class ImportCommand(Command):
    """The import command.
    """

    def process(self, language):
        """Process importing the given language.
        """

        # In order to implement the --require-min-complete option, we need
        # to first determine the translation status across all .po catalogs
        # for this language. We can keep the catalogs in memory because we
        # will need them later anyway.
        catalogs = {}
        count_total = 0
        count_translated = 0
        for kind in self.env.xmlfiles:
            language_po = language.po(kind)
            if not language_po.exists():
                continue
            catalogs[kind] = catalog = read_catalog(language_po)
            ntotal, ntrans, nfuzzy = get_catalog_counts(catalog)
            count_total += ntotal
            count_translated += ntrans
            if self.env.config.ignore_fuzzy:
                count_translated -= nfuzzy

        # Compare our count with what is required, if anything.
        skip_due_to_incomplete = False
        min_required = self.env.config.min_completion
        if count_total == 0:
            actual_completeness = 1
        else:
            actual_completeness = count_translated / float(count_total)
        if min_required:
            skip_due_to_incomplete = actual_completeness < min_required

        # Now loop through the list of target files, and either create
        # them, or print a status message for each indicating that they
        # were skipped.
        for kind in self.env.xmlfiles:
            language_xml = language.xml(kind)
            action = self.w.begin(language_xml)

            if skip_due_to_incomplete:
                # TODO: Creating a catalog object here is kind of clunky.
                # Idially, we'd refactor convert.py so that we can use a
                # dict to represent a resource XML file.
                write_file(self, language_xml,
                       xml2string(po2xml(self.env, Catalog(locale=language.code))),
                       action=False)
                action.done('skipped', status=('%s catalogs aren\'t '
                                               'complete enough - %.2f done' % (
                                                   language.code,
                                                   actual_completeness)))
                continue

            if not language_po.exists():
                self.w.action('skipped', language_xml)
                self.w.message('%s doesn\'t exist' % language_po.rel, 'warning')
                continue

            write_file(self, language_xml,
                       xml2string(po2xml(self.env, catalogs[kind])),
                       action=action)

    def execute(self):
        for language in self.env.languages:
            self.process(language)
