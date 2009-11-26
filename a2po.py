#!/usr/bin/env python
# encoding: utf8
"""
a2po -- Convert Android string resources to gettext .po files, and
import them right back.

Author: Michael Elsdörfer <michael@elsdoerfer.com>

Licensed under BSD.

TODO: Add support for --verbosity, --quiet options.
TODO: Use the -l option?
"""

import os, sys
import shutil
from os import path
import re
import getopt
from xml.dom import minidom
import xml2po


# Same as the xml2po script uses by default.
xml2po_options = {
    'mark_untranslated'   : False,
    'expand_entities'     : True,
    'expand_all_entities' : False,
}


class UnsupportedOptionsError(Exception):
    pass


LANG_DIR = re.compile(r'^values(?:-(\w\w))?$')


def export(default_file, languages, output_dir, options):
    """The export command.
    """
    initial = options.pop('--initial', None) != None
    if options:
        raise UnsupportedOptionsError()

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
    xml2po = make_xml2po('pot', template_pot_file)
    xml2po.to_pot([default_file])

    if initial:
        try:
            import polib
        except ImportError:
            print "Error: polib (http://code.google.com/p/polib/) required " \
                  "to use --initial."
            return 1

        default_xml = load_xml_strings(default_file)
        default_xml = dict((v,k) for k, v in default_xml.iteritems())

        for code, filename in languages.items():
            po_file = path.join(output_dir, "%s.po" % code)
            if path.exists(po_file):
                print "%s.po exists, skipping." % code
            else:
                print "Generating %s.po..." % code,
                lang_xml = load_xml_strings(filename)

                # We could generate those po-files from scratch,
                # but that would mean we have essentially two different
                # generation routines; our own, and xml2po - potentially
                # with differing meta data etc. So for now, copy the
                # template we just generated and edit it instead.
                #
                # There is also a potential data disconnect - we have to
                # match what we read from the language xml files with what
                # xml2po generated based on the default resource xml.
                # This is actually a pretty real concern, since it depends
                # on how data is normalized too (say, replacing entities,
                # trimming whitespace, both of which xml2po does).
                shutil.copy2(template_pot_file, po_file)
                po = polib.pofile(po_file)

                count_strings = count_trans = 0
                for entry in po:
                    count_strings += 1

                    if not entry.msgid in default_xml:
                        print "Error: Cannot find resource name for \"%s...\", skipping." % \
                            entry.msgid.replace('\n', '\\n').replace('\r', '\\r')[:30]
                        continue
                    name = default_xml[entry.msgid]
                    if name in lang_xml:
                        count_trans += 1
                        entry.msgstr = lang_xml[name]

                        # Remove so we know which one we handled.
                        del lang_xml[name]

                po.save()

                print "%d strings, %d translations processed." % (
                    count_strings, count_trans)

                # If there are still strings left from the translation
                # file, show a warning that we can't handle those.
                if lang_xml:
                    print ("Warning: xml for %s contains strings "
                           "not found in default file: %s" % (
                                code, ", ".join(lang_xml)))

    else:
        print ""   # Improves formatting
        for code, filename in languages.items():
            po_file = path.join(output_dir, "%s.po" % code)
            if not path.exists(po_file):
                print ("Warning: Skipping %s, .po file doesn't exist. "
                       "Use --initial.") % code
                continue

            xml2po = make_xml2po('update')
            xml2po.update([default_file], po_file)


def import_(default_file, languages, output_dir, options):
    """The import command.
    """
    if options:
        raise UnsupportedOptionsError()

    for code, filename in languages.items():
        mo_file = path.join(output_dir, "%s.mo" % code)
        if not path.exists(mo_file):
            # TODO: The xml2po script runs msgfmt to create the .mo,
            # optionally; we currently require the user to compile it.
            print "Warning: Skipping %s, .mo file doesn't exist." % code
            continue
        print "Processing %s" % code
        xml2po = make_xml2po('merge', filename)
        xml2po.merge(mo_file, default_file)


def make_xml2po(operation, output='-'):
    return xml2po.Main('basic', operation, output, xml2po_options)


def load_xml_strings(filename, normfunc=None):
    """Load all resource names from an Android strings.xml resource file.
    """
    result = {}
    doc = minidom.parse(filename)
    for tag in doc.documentElement.getElementsByTagName('string'):
        if not tag.attributes.has_key('name'):
            continue
        name = tag.attributes['name'].nodeValue
        if name in result:
            print "Error: %s contains duplicate string names: %s" % (filename, name)
        result[name] = "".join([n.toxml() for n in tag.childNodes])
        if normfunc:
            result[name] = normfunc(result[name])
    return result


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
        ['android=', 'gettext=', 'initial'])
    options = dict(options)

    handlers = {
        'import': import_,
        'export': export,
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


if __name__ == '__main__':
    sys.exit(main(sys.argv) or 0)

