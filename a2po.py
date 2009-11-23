#!/usr/bin/env python
# encoding: utf8
"""
a2po -- Convert Android string resources to gettext .po files, and 
import them right back.

Author: Michael Elsdörfer <michael@elsdoerfer.com>

Licensed under BSD.

TODO: Add support for --verbosity, --quiet options.
"""

import os, sys
from os import path
import re
import getopt
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


def make_xml2po(operation, output):
    return xml2po.Main('basic', operation, output, xml2po_options)


def export(default_file, languages, output_dir, options):
    """The export command.
    """
    initial = options.pop('--initial', None)
    if options:
        raise UnsupportedOptionsError()
        
    if initial:
        # TODO: create gettext dir if necessary here
        # seems like we will have to do this ourselves (matching up 
        # android xml name= strings).
        # Be sure not to override existing files.
        print "--initial mode currently not yet supported."
        return 1
        
    else:
        print ""   # Improves formatting
        for code, filename in languages.items():
            po_file = path.join(output_dir, "%s.po" % code)
            if not path.exists(po_file):
                print "Warning: Skipping %s, .po file doesn't exist. Use --initial." % code
                continue
            
            xml2po = make_xml2po('update', '-')
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
        ['android=', 'gettext=', 'initial='])
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

