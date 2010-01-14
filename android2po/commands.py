from __future__ import absolute_import

import os
from os import path
from lxml import etree
from babel.messages import pofile

from .convert import xml2po, po2xml


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


def write_catalog(filename, catalog, **kwargs):
    """Write a babel message catalog to file.

    This is a simple shortcut around pofile.write_po().
    """
    file = open(filename, 'wb+')
    try:
        pofile.write_po(file, catalog, **kwargs)
        file.flush()
    finally:
        file.close()


def write_xml(filename, xmldom):
    """Helper that writes out a DOM to a file.

    TODO: It would be cool if this could try to recreate the formatting
    of the original xml file.
    """
    ENCODING = 'utf-8'
    file = open(filename, 'wb+')
    try:
        file.write(etree.tostring(xmldom, xml_declaration=True,
                                  encoding=ENCODING, pretty_print=True))
        file.flush()
    finally:
        file.close()


class CmdInterface(object):
    """Helpers for printing."""

    def p(self, s, nl=True):
        """Print standard message."""
        if not self.env.options.quiet:
            if nl:
                print s
            else:
                print s,

    def v(self, s):
        """Print verbose message."""
        if not self.env.options.verbose:
            print s

    def i(self, s):
        """Print important message."""
        print s


class Command(CmdInterface):
    """Abstract base command class.
    """

    @classmethod
    def setup_arg_parser(cls, argparser):
        """A command should register it's sub-arguments here with the
        given argparser instance.
        """

    def __init__(self, env):
        """Will be initialized with the parsed command options, and
        an environment object that contains information about the
        project we are running inside.
        """
        self.env = env

    def export(self):
        raise NotImplementedError()


class BaseExportingCommand(Command):

    def generate_po(self, code, env, xml_file, po_file):
        """Helper to generate a .po file.

        ``code`` - the language code.
        ``env`` - the current environment.
        ``xml_file`` - the language xml file.
        ``po_file`` - the place to store the .po file at.
        """
        self.p("Generating %s.po..." % code, nl=False)
        lang_po, unmatched = xml2po(env.default_file, xml_file)
        write_catalog(po_file, lang_po)
        self.p("%d strings processed, %d translated." % (
            # Make sure we don't count the header.
            len(lang_po),
            len([m for m in lang_po if m.string and m.id])))
        if unmatched:
            self.i("Warning: xml for %s contains strings "
                   "not found in default file: %s" % (
                        code, ", ".join(unmatched)))


class InitCommand(BaseExportingCommand):
    """The init command; to initialize new languages.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        parser.add_argument('language', nargs='*',
            help='Language code to initialize. If none given, all '+
                 'languages lacking a .po file will be initialized.')

    def execute(self):
        env, options, config = self.env, self.env.options, self.env.config

        languages = options.language
        if not languages:
            languages = env.languages.keys()

        for code in languages:
            if not code in env.languages:
                # we actually need to create an empty strings.xml
                filename = path.join(config.resource_dir,
                                     'values-%s' % code,
                                     'strings.xml')
                dir = path.dirname(filename)
                if not path.exists(dir):
                    os.makedirs(dir)
                f = open(filename, 'wb')
                try:
                    f.write("""<?xml version='1.0' encoding='utf-8'?>\n<resources>\n</resources>""")
                finally:
                    f.close()
            else:
                filename = env.languages[code]

            po_file = path.join(config.gettext_dir, "%s.po" % code)
            if path.exists(po_file):
                self.i("%s.po exists, skipping." % code)
            else:
                self.generate_po(code, env, filename, po_file)


class ExportCommand(BaseExportingCommand):
    """The export command.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--initial', action='store_true',
            help='Create .po files for new languages based their XML '+
                  'files')
        group.add_argument('--overwrite', action='store_true',
            help='Recreate .po files for all languages from their XML '+
                 'counterparts')

    def execute(self):
        env, options, config = self.env, self.env.options, self.env.config

        # Create the gettext output directory, if necessary
        if not path.exists(config.gettext_dir):
            self.p("Created %s " % config.gettext_dir)
            # TODO: we should only create this if it was automatically found
            os.makedirs(config.gettext_dir)

        # Update the template file in either case
        # TODO: Should this really be generated in every case, or do we
        # want to enable the user to set fixed meta data, and simply
        # merge subsequent updates in? Note this may affect the --initial
        # mode below, since it uses the template.
        self.p("Generating template.pot")
        template_pot_file = path.join(config.gettext_dir, 'template.pot')
        default_po = xml2po(env.default_file)
        write_catalog(template_pot_file, default_po)

        if options.initial or options.overwrite:
            for code, filename in env.languages.items():
                po_file = path.join(config.gettext_dir, "%s.po" % code)
                if path.exists(po_file) and not options.overwrite:
                    self.i("%s.po exists, skipping." % code)
                else:
                    self.generate_po(code, env, filename, po_file)

        else:
            for code, filename in env.languages.items():
                po_file = path.join(config.gettext_dir, "%s.po" % code)
                if not path.exists(po_file):
                    self.i("Warning: Skipping %s, .po file doesn't exist. "
                           "Use --initial." % code)
                    continue

                self.p("Processing %s" % code)
                # If we do not provide a locale, babel will consider this
                # catalog a template and always write out the default
                # header. It seemingly does not consider the "Language"
                # header inside the file at all, and indeed deletes it.
                # TODO: It deletes all headers it doesn't know, and
                # overrides others. That sucks.
                lang_po = read_catalog(po_file, locale=code)
                lang_po.update(default_po)
                # TODO: Should we include previous?
                write_catalog(po_file, lang_po, include_previous=False)


class ImportCommand(Command):
    """The import command.
    """

    def execute(self):
        for code, filename in self.env.languages.items():
            po_filename = path.join(self.env.config.gettext_dir, "%s.po" % code)
            if not path.exists(po_filename):
                self.i("Warning: Skipping %s, .po file doesn't exist." % code)
                continue
            self.p("Processing %s" % code)

            xml_dom = po2xml(read_catalog(po_filename))
            write_xml(filename, xml_dom)
