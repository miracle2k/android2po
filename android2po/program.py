"""Implements the command line interface.
"""

import os, sys
from os import path
import re
import getopt
from lxml import etree
from babel.messages import pofile


__all__ = ('main', 'run',)


class UnsupportedOptionsError(Exception):
    pass


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


def cmd_export(default_file, languages, output_dir, options):
    """The export command.
    """
    initial = options.pop('--initial', None) != None
    overwrite = options.pop('--overwrite', None) != None
    if options:
        raise UnsupportedOptionsError()
    if overwrite and initial:
        print "Error: Cannot both specify --initial and --overwrite"
        return 1

    # Create the gettext output dir, if necessary
    if not path.exists(output_dir):
        print "Created %s " % output_dir
        # TODO: we should only create this if it was automatically found
        os.makedirs(output_dir)

    # Update the template file in either case
    # TODO: Should this really be generated in every case, or do we
    # want to enable the user to set fixed meta data, and simply
    # merge subsequent updates in? Note this may affect the --initial
    # mode below, since it uses the template.
    print "Generating template.pot"
    template_pot_file = path.join(output_dir, 'template.pot')
    default_po = xml2po(default_file)
    write_catalog(template_pot_file, default_po)

    if initial or overwrite:
        for code, filename in languages.items():
            po_file = path.join(output_dir, "%s.po" % code)
            if path.exists(po_file) and not overwrite:
                print "%s.po exists, skipping." % code
            else:
                print "Generating %s.po..." % code,
                lang_po, unmatched = xml2po(default_file, filename)
                write_catalog(po_file, lang_po)
                print "%d strings processed, %d translated." % (
                    # Make sure we don't count the header.
                    len(lang_po),
                    len([m for m in lang_po if m.string and m.id]))
                if unmatched:
                    print ("Warning: xml for %s contains strings "
                           "not found in default file: %s" % (
                                code, ", ".join(unmatched)))

    else:
        for code, filename in languages.items():
            po_file = path.join(output_dir, "%s.po" % code)
            if not path.exists(po_file):
                print ("Warning: Skipping %s, .po file doesn't exist. "
                       "Use --initial.") % code
                continue

            print "Processing %s" % code
            lang_po = read_catalog(po_file)
            lang_po.update(default_po)
            # TODO: Should we include previous?
            write_catalog(po_file, lang_po, include_previous=False)


def cmd_import(default_file, languages, output_dir, options):
    """The import command.
    """
    if options:
        raise UnsupportedOptionsError()

    for code, filename in languages.items():
        po_filename = path.join(output_dir, "%s.po" % code)
        if not path.exists(po_filename):
            print "Warning: Skipping %s, .po file doesn't exist." % code
            continue
        print "Processing %s" % code

        xml_dom = po2xml(read_catalog(po_filename))
        write_xml(filename, xml_dom)


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
    options, arguments = getopt.getopt(argv[1:], '',
        ['android=', 'gettext=', 'initial', 'overwrite'])
    options = dict(options)

    handlers = {
        'import': cmd_import,
        'export': cmd_export,
    }

    try:
        func = handlers[arguments[0]]
        if len(arguments) > 1:
            raise IndexError()
    except (KeyError, IndexError):
        print "Error: Expected a single argument, out of: %s" % \
            ", ".join(handlers)
        return 1

    # Determine the directories to use
    resource_dir = options.pop('--android', None)
    gettext_dir = options.pop('--gettext', None)

    if not resource_dir or not gettext_dir:
        project_dir = find_project_dir()
        if not project_dir:
            print "Error: Android project directory not found. Make " \
                  "sure you are inside a project, or specify both " \
                  "--android and --gettext manually."
            return 1
        print "Using Android project in '%s'" % project_dir
        resource_dir = resource_dir or path.join(project_dir, 'res')
        gettext_dir = gettext_dir or path.join(project_dir, 'locale/')

    # Find all the languages.
    default_file, languages = collect_languages(resource_dir)
    print "Found %d language(s): %s" % (len(languages), ", ".join(languages))

    # Run with the rest of the options, which are now considered
    # command-specific.
    try:
        return func(default_file, languages, gettext_dir, options)
    except UnsupportedOptionsError:
        # Hacky - we export all supported options to be pop'ed by the
        # command handler function.
        print "Error: Unsupported options: %s" % ", ".join(options.keys())
        return 1


def run():
    """Simplified interface to main().
    """
    sys.exit(main(sys.argv) or 0)