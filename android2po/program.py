"""Implements the command line interface.
"""

from __future__ import absolute_import

import os, sys
from os import path
import re
import argparse
from lxml import etree
from babel.messages import pofile

from .utils import AttrDict
from .convert import xml2po, po2xml


__all__ = ('main', 'run',)


def read_catalog(filename):
    """Helper to read a catalog from a .po file.
    """
    file = open(filename, 'rb')
    try:
        return pofile.read_po(file)
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
        if not self.options.quiet:
            if nl:
                print s
            else:
                print s,

    def v(self, s):
        """Print verbose message."""
        if not self.options.verbose:
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

    def __init__(self, env, options):
        """Will be initialized with the parsed command options, and
        an environment object that contains information about the
        project we are running inside.
        """
        self.env, self.options = env, options

    def export(self):
        raise NotImplementedError()


class ExportCommand(Command):
    """The export command.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        parser.add_argument('--initial', action='store_true',
            help='Create .po files for new languages based their XML '+
                  'files')
        parser.add_argument('--overwrite', action='store_true',
            help='Recreate .po files for all languages from their XML '+
                 'counterparts')

    def execute(self):
        env = self.env
        options = self.options

        # TODO: Can argparse resolve this?
        if options.overwrite and options.initial:
            self.i("Error: Cannot both specify --initial and --overwrite")
            return 1

        # Create the gettext output directory, if necessary
        if not path.exists(env.gettext_dir):
            self.p("Created %s " % env.gettext_dir)
            # TODO: we should only create this if it was automatically found
            os.makedirs(env.gettext_dir)

        # Update the template file in either case
        # TODO: Should this really be generated in every case, or do we
        # want to enable the user to set fixed meta data, and simply
        # merge subsequent updates in? Note this may affect the --initial
        # mode below, since it uses the template.
        self.p("Generating template.pot")
        template_pot_file = path.join(env.gettext_dir, 'template.pot')
        default_po = xml2po(env.default_file)
        write_catalog(template_pot_file, default_po)

        if options.initial or options.overwrite:
            for code, filename in env.languages.items():
                po_file = path.join(env.gettext_dir, "%s.po" % code)
                if path.exists(po_file) and not options.overwrite:
                    self.i("%s.po exists, skipping." % code)
                else:
                    self.p("Generating %s.po..." % code, nl=False)
                    lang_po, unmatched = xml2po(env.default_file, filename)
                    write_catalog(po_file, lang_po)
                    self.p("%d strings processed, %d translated." % (
                        # Make sure we don't count the header.
                        len(lang_po),
                        len([m for m in lang_po if m.string and m.id])))
                    if unmatched:
                        self.i("Warning: xml for %s contains strings "
                               "not found in default file: %s" % (
                                    code, ", ".join(unmatched)))

        else:
            for code, filename in env.languages.items():
                po_file = path.join(env.gettext_dir, "%s.po" % code)
                if not path.exists(po_file):
                    self.i("Warning: Skipping %s, .po file doesn't exist. "
                           "Use --initial.") % code
                    continue

                self.p("Processing %s" % code)
                lang_po = read_catalog(po_file)
                lang_po.update(default_po)
                # TODO: Should we include previous?
                write_catalog(po_file, lang_po, include_previous=False)


class ImportCommand(Command):
    """The import command.
    """

    def execute(self):
        for code, filename in self.env.languages.items():
            po_filename = path.join(self.env.gettext_dir, "%s.po" % code)
            if not path.exists(po_filename):
                self.i("Warning: Skipping %s, .po file doesn't exist." % code)
                continue
            self.p("Processing %s" % code)

            xml_dom = po2xml(read_catalog(po_filename))
            write_xml(filename, xml_dom)


COMMANDS = {
    'export': ExportCommand,
    'import': ImportCommand,
}


def find_project_dir():
    """Try to find the Android project directory we are currently in.
    """
    cur = os.getcwdu()

    while True:
        expected_path = path.join(cur, 'AndroidManifest.xml')
        if path.exists(expected_path) and path.isfile(expected_path):
            return cur

        old = cur
        cur = path.normpath(path.join(cur, path.pardir))
        if cur == old:
            # No further change, we are probably at root level.
            # TODO: Is there a better way? Is path.ismount suitable?
            break

    return None


LANG_DIR = re.compile(r'^values(?:-(\w\w))?$')

def collect_languages(resource_dir):
    languages = {}
    default_file = None
    for name in os.listdir(resource_dir):
        filename = path.join(resource_dir, name, 'strings.xml')
        if not path.isfile(filename):
            continue
        match = LANG_DIR.match(name)
        if not match:
            continue
        code = match.groups()[0]
        if code == None:
            default_file = filename
        else:
            languages[code] = filename

    return default_file, languages


def main(argv):
    from . import get_version
    parser = argparse.ArgumentParser(
        description='Convert Android string resources to gettext .po '+
                    'files, an import them back.',
        epilog='Written by: Michael Elsdoerfer <michael@elsdoerfer.com>',
        version=get_version(),
        # To override the -v option auto-generated by 'version'
        conflict_handler='resolve')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='be extra verbose')
    parser.add_argument('--quiet', '-q', action='store_true', help='be extra quiet')
    parser.add_argument('--android', metavar='DIR',
        help='Android resource directory ($PROJECT/res by default)')
    parser.add_argument('--gettext', metavar='DIR',
        help='directory containing the .po files ($PROJECT/locale by default)')
    subparsers = parser.add_subparsers(dest="command")

    for name, cmdclass in COMMANDS.items():
        cmd_parser = subparsers.add_parser(name)
        cmdclass.setup_arg_parser(cmd_parser)

    options = parser.parse_args(argv[1:])

    # Determine the directories to use
    resource_dir = options.android
    gettext_dir = options.gettext

    if not resource_dir or not gettext_dir:
        project_dir = find_project_dir()
        if not project_dir:
            print "Error: Android project directory not found. Make " \
                  "sure you are inside a project, or specify both " \
                  "--android and --gettext manually."
            return 1
        if options.verbose:
            print "Using Android project in '%s'" % project_dir
        resource_dir = resource_dir or path.join(project_dir, 'res')
        gettext_dir = gettext_dir or path.join(project_dir, 'locale/')

    # Find all the languages.
    default_file, languages = collect_languages(resource_dir)
    if not options.quiet:
        print "Found %d language(s): %s" % (len(languages), ", ".join(languages))

    # Setup an instance of the command class, then execute it.
    env = AttrDict({
        'languages': languages,
        'default_file': default_file,
        'gettext_dir': gettext_dir,
        'resource_dir': resource_dir,
    })
    cmd = COMMANDS[options.command](env, options)
    return cmd.execute()


def run():
    """Simplified interface to main().
    """
    sys.exit(main(sys.argv) or 0)