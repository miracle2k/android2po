from __future__ import absolute_import

import os
from os import path
from lxml import etree
from babel.messages import pofile

from .convert import xml2po, po2xml
from .env import Language


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

    def generate_po(self, language):
        """Helper to generate a .po file.
        """
        self.p("Generating %s.po...\n" % language.code, nl=False)
        for file, file_ext, file_po, file_pot in self.env.xmlfiles:
            lang_po, unmatched = xml2po(file, language.xml_file(file_ext))
            write_catalog(language.po_file(file_po), lang_po)
            self.p("%s: %d strings processed, %d translated." % (
                file_ext,
                # Make sure we don't count the header.
                len(lang_po),
                len([m for m in lang_po if m.string and m.id])))
            if unmatched:
                 self.i("Warning: xml for %s contains strings "
                        "not found in default file: %s" % (
                            language.code, ", ".join(unmatched)))


class InitCommand(BaseExportingCommand):
    """The init command; to initialize new languages.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        parser.add_argument('language', nargs='*',
            help='Language code to initialize. If none given, all '+
                 'languages lacking a .po file will be initialized.')

    def execute(self):
        env = self.env

        if env.options.language:
            languages = []
            for code in env.options.language:
                languages.append(Language(code, env))
        else:
            languages = env.languages

        for language in languages:
            for file, file_ext, file_po, file_pot in self.env.xmlfiles:
                if not language.has_xml(file_ext):
                    dir = path.dirname(language.xml_file(file_ext))
                    if not path.exists(dir):
                        os.makedirs(dir)
                    f = open(language.xml_file(file_ext), 'wb')
                    try:
                        f.write("""<?xml version='1.0' encoding='utf-8'?>\n<resources>\n</resources>""")
                    finally:
                        f.close()

                if path.exists(language.po_file(file_po)):
                    self.i("%s exists, skipping." % (file_po % language.code))
                else:
                    self.generate_po(language)


class ExportCommand(BaseExportingCommand):
    """The export command.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--initial', action='store_true',
            help='create .po files for new languages based their XML '+
                  'files')
        group.add_argument('--overwrite', action='store_true',
            help='recreate .po files for all languages from their XML '+
                 'counterparts')

    def execute(self):
        env = self.env

        for file, file_ext, file_po, file_pot in self.env.xmlfiles:
            # Update the template file in either case
            # TODO: Should this really be generated in every case, or do we
            # want to enable the user to set fixed meta data, and simply
            # merge subsequent updates in? Note this may affect the --initial
            # mode below, since it uses the template.
            if not env.no_template:
                self.p("Generating %s" % file_pot)
            template_pot_file = path.join(env.gettext_dir, file_pot)
            default_po = xml2po(file)
            if not env.no_template:
                write_catalog(template_pot_file, default_po)

            if env.options.initial or env.options.overwrite:
                for language in env.languages:
                    if language.has_po(file_po) and not env.options.overwrite:
                        self.i("%s exists, skipping." % file_po)
                    else:
                        self.generate_po(language)

            else:
                for language in env.languages:
                    if not language.has_po(file_po):
                        self.i("Warning: Skipping %s, .po file doesn't exist. "
                               "Use --initial." % language.code)
                        continue

                    self.p("Processing %s" % language.code)
                    # If we do not provide a locale, babel will consider this
                    # catalog a template and always write out the default
                    # header. It seemingly does not consider the "Language"
                    # header inside the file at all, and indeed deletes it.
                    # TODO: It deletes all headers it doesn't know, and
                    # overrides others. That sucks.
                    lang_po = read_catalog(language.po_file(file_po),
                        locale=language.code)
                    lang_po.update(default_po)
                    # TODO: Should we include previous?
                    write_catalog(language.po_file(file_po),
                        lang_po, include_previous=False)


class ImportCommand(Command):
    """The import command.
    """

    def execute(self):
        for file, file_ext, file_po, file_pot in self.env.xmlfiles:
            for language in self.env.languages:
                if not path.exists(language.po_file(file_po)):
                    self.i("Warning: Skipping %s, .po file doesn't exist." % language.code)
                    continue
                po_file = language.po_file(file_po)
                self.p("Processing %s" % po_file)

                xml_dom = po2xml(read_catalog(po_file))
                write_xml(language.xml_file(file_ext), xml_dom)
