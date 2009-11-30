#!/usr/bin/env python
# encoding: utf8
"""
a2po -- Convert Android string resources to gettext .po files, and
import them right back.

Author: Michael Elsdörfer <michael@elsdoerfer.com>

Licensed under BSD.

TODO: Use a better options parser.

Resources:
    http://www.gnu.org/software/hello/manual/gettext/PO-Files.html
"""

import os, sys
from os import path
import re
import getopt
import codecs
from lxml import etree
from babel.messages import pofile, Catalog

try:
    from colletions import OrderedDict
except ImportError:
    # http://code.activestate.com/recipes/576693/
    from UserDict import DictMixin

    class OrderedDict(dict, DictMixin):

        def __init__(self, *args, **kwds):
            if len(args) > 1:
                raise TypeError('expected at most 1 arguments, got %d' % len(args))
            try:
                self.__end
            except AttributeError:
                self.clear()
            self.update(*args, **kwds)

        def clear(self):
            self.__end = end = []
            end += [None, end, end]         # sentinel node for doubly linked list
            self.__map = {}                 # key --> [key, prev, next]
            dict.clear(self)

        def __setitem__(self, key, value):
            if key not in self:
                end = self.__end
                curr = end[1]
                curr[2] = end[1] = self.__map[key] = [key, curr, end]
            dict.__setitem__(self, key, value)

        def __delitem__(self, key):
            dict.__delitem__(self, key)
            key, prev, next = self.__map.pop(key)
            prev[2] = next
            next[1] = prev

        def __iter__(self):
            end = self.__end
            curr = end[2]
            while curr is not end:
                yield curr[0]
                curr = curr[2]

        def __reversed__(self):
            end = self.__end
            curr = end[1]
            while curr is not end:
                yield curr[0]
                curr = curr[1]

        def popitem(self, last=True):
            if not self:
                raise KeyError('dictionary is empty')
            key = reversed(self).next() if last else iter(self).next()
            value = self.pop(key)
            return key, value

        def __reduce__(self):
            items = [[k, self[k]] for k in self]
            tmp = self.__map, self.__end
            del self.__map, self.__end
            inst_dict = vars(self).copy()
            self.__map, self.__end = tmp
            if inst_dict:
                return (self.__class__, (items,), inst_dict)
            return self.__class__, (items,)

        def keys(self):
            return list(self)

        setdefault = DictMixin.setdefault
        update = DictMixin.update
        pop = DictMixin.pop
        values = DictMixin.values
        items = DictMixin.items
        iterkeys = DictMixin.iterkeys
        itervalues = DictMixin.itervalues
        iteritems = DictMixin.iteritems

        def __repr__(self):
            if not self:
                return '%s()' % (self.__class__.__name__,)
            return '%s(%r)' % (self.__class__.__name__, self.items())

        def copy(self):
            return self.__class__(self)

        @classmethod
        def fromkeys(cls, iterable, value=None):
            d = cls()
            for key in iterable:
                d[key] = value
            return d

        def __eq__(self, other):
            if isinstance(other, OrderedDict):
                return len(self)==len(other) and \
                       all(p==q for p, q in  zip(self.items(), other.items()))
            return dict.__eq__(self, other)

        def __ne__(self, other):
            return not self == other


class UnsupportedOptionsError(Exception):
    pass


def _load_xml_strings(file):
    """Load all resource names from an Android strings.xml resource file.
    """
    result = OrderedDict()
    doc = etree.parse(file)
    for tag in doc.xpath('/resources/string'):
        if not 'name' in tag.attrib:
            continue
        name = tag.attrib['name']
        if name in result:
            print "Error: %s contains duplicate string names: %s" % (filename, name)
            continue

        if tag.text:
            # Simple case, no nested tags, entities already decoded.
            value = tag.text
            # Tags however, are true, which we do not want here; a &lt;
            # needs to end up in the translation as a &lt; so it needs to
            # be in the .po file as an &lt;
            # TODO: In theory, it might be possible to note the fact the fact
            # that those chars need to end up encoded in some .po comment,
            # and thus let the translator work without the encoding.
            value = value.replace('<', '&lt;')
            value = value.replace('>', "&gt;")
        else:
            # We need to extract the whole subtree as a string.
            value = "".join([etree.tostring(x, encoding=unicode) for x in tag.iterdescendants()])
            value = value.strip()

            # TODO: Support more entities, like numerics?
            # Note that we do not translate < and >; since Android strings can
            # be HTML, let HTML be edited as-is in gettext; We just don't to
            # bother the translator with those entities, especially for strings
            # that do NOT have any HTML.
            value = value.replace('&amp;', '&')
            value = value.replace('&quot;', '"')
            value = value.replace('&apos;', "'")
        # Android requires us to specify linebreaks in resources as "\n".
        # However, writing that into the .po a) breaks babel
        # (http://babel.edgewall.org/ticket/198), and b) doesn't seem
        # to be the best solution anyway. Instead, what we do is:
        #    * We ignore all *actual* linebreaks, since they are
        #      meaningless in Android anyway.
        #    * We replace all \n sequences with actual linebreaks.
        # On import, we reverse the effect.
        value = value.replace('\n', '').replace(r'\n', '\n')
        result[name] = value
    return result


def xml2po(file, translations=None):
    """Return the Android string resource in ``file`` as a babel
    .po catalog.

    If given, the Android string resource in ``translations`` will be
    used for the translated values. In this case, the returned value
    is a 2-tuple (catalog, unmatched), with the latter being a list of
    Android string resource names that are in the translated file, but
    not in the original.
    """
    original_strings = _load_xml_strings(file)
    trans_strings = _load_xml_strings(translations) if translations else None

    catalog = Catalog()
    for name, org_value in original_strings.iteritems():
        trans_value = u""
        if trans_strings:
            trans_value = trans_strings.pop(name, trans_value)

        catalog.add(org_value, trans_value, context=name)
        # Would it be too much to ask for add() to return the message?
        # TODO: Bring this back when we can ensure it won't be added
        # during export/update() either.
        #catalog.get(org_value, context=name).flags.discard('python-format')

    if trans_strings is not None:
        # At this point, trans_strings only contains those for which
        # no original existed.
        return catalog, trans_strings.keys()
    else:
        return catalog


def po2xml(catalog):
    """Convert the gettext catalog in ``catalog`` to an XML DOM.

    This currently relies entirely in the fact that we can use the context
    of each message to specify the Android resource name (which we need
    to do to handle duplicates, but this is a nice by-product). However
    that also means we cannot handle arbitrary catalogs.

    The latter would in theory be possible by using the original,
    untranslated XML to match up a messages id to a resource name, but
    right now we don't support this (and it's not clear it would be
    necessary, even).
    """
    loose_parser = etree.XMLParser(recover=True)

    root_el = etree.Element('resources')
    for message in catalog:
        if not message.id:
            # This is the header
            continue

        if not message.string:
            # Untranslated.
            continue

        # See the corresponding replace() in _load_xml_strings().
        value = message.string.replace('\n', r'\n')

        # The translations may contain arbitrary XHTML, which we need
        # to inject into the DOM to properly output. That means parsing
        # it first. That means we have to deal with potential errors
        # here. It's ok though, if we wouldn't do it, we ultimately
        # would simply end up generating an invalid resource file.
        value = value.replace('&', '&amp;')
        value = value.replace('"', '&quot;')
        value = value.replace("'", '&apos;')
        value_to_parse = "<string>%s</string>" % value
        try:
            string_el = etree.fromstring(value_to_parse)
        except etree.XMLSyntaxError:
            string_el = etree.fromstring(value_to_parse, loose_parser)
            print "Error: Translation contains invalid XHTML (for resource %s)" % message.context

        string_el.attrib['name'] = message.context
        root_el.append(string_el)
    return root_el


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
                    len(lang_po)-1,
                    len([m for m in lang_po if m.string and m.id])-1)
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


if __name__ == '__main__':
    sys.exit(main(sys.argv) or 0)

