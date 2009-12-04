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
from itertools import chain
import re
import getopt
import codecs
from lxml import etree
from babel.messages import pofile, Catalog


__all__ = ('main',)
__version__ = (1, 0, 1)


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


WHITESPACE = ' \n\t'     # Whitespace that we collapse
EOF = None


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

        def convert_text(text):
            """This is called for every distinct block of text, as they
            are separated by tags.

            It handles most of the Android syntax rules: quoting, escaping,
            collapsing duplicate whitespace etc.
            """
            # '<' and '>' as literal characters inside a text need to be
            # escaped; this is because we need to differentiate them to
            # actual tags inside a resource string which we write to the
            # .po file as literal '<', '>' characters. As a result, if the
            # user puts &lt; inside his Android resource file, this is how
            # it will end up in the .po file as well.
            # We only do this for '<' and '<' right now, which is of course
            # a hack. We'd need to process at least &amp; as well, because
            # right now '&lt;' and '&amp;lt;' both generate the same on
            # import. However, if we were to do that, a simple non-HTML
            # text like "FAQ & Help" would end up us "FAQ &amp; Help" in
            # the .po - not particularly nice.
            # TODO: I can see two approaches to solve this: Handle things
            # differently depending on whether there are nested tags. We'd
            # be able to handle both '&amp;lt;' in a HTML string and output
            # a nice & character in a plaintext string.
            # Option 2: It might be possible to note the type of encoding
            # we did in a .po comment. That would even allow us to present
            # a string containing tags encoded using entities (but not actual
            # nested XML tags) using plain < and > characters in the .po
            # file. Instead of a comment, we could change the import code
            # to require a look at the original resource xml file to
            # determine which kind of encoding was done.
            text = text.replace('<', '&lt;')
            text = text.replace('>', "&gt;")

            # We need to collapse multiple whitespace while paying
            # attention to Android's quoting and escaping.
            space_count = 0
            active_quote = False
            escaped = False
            i = 0
            text = list(text) + [EOF]
            while i < len(text):
                c = text[i]

                # Handle whitespace collapsing
                if c is not EOF and c in WHITESPACE:
                    space_count += 1
                elif space_count > 1:
                    # Remove duplicate whitespace; Pay attention: We
                    # don't do this if we are currently inside a quote,
                    # except for one special case: If we have unbalanced
                    # quotes, e.g. we reach eof while a quote is still
                    # open, we *do* collapse that trailing part; this is
                    # how Android does it, for some reason.
                    if not active_quote or c is EOF:
                        del text[i-space_count:i-1]
                        i -= space_count + 1
                    space_count = 0
                else:
                    space_count = 0

                # Handle quotes
                if c == '"' and not escaped:
                    active_quote = not active_quote
                    del text[i]
                    i -= 1

                # Handle escapes
                if c == '\\':
                    if not escaped:
                        escaped = True
                    else:
                        # A double-backslash represents a single;
                        # simply deleting the current char will do.
                        del text[i]
                        i -= 1
                        escaped = False
                else:
                    if escaped:
                        # Handle the limited amount of escape codes
                        # that we support.
                        # TODO: What about \r, or \r\n?
                        if c is EOF:
                            # Basically like any other char, but put
                            # this first so we can use the ``in`` operator
                            # in the clauses below without issue.
                            pass
                        elif c == 'n':
                            text[i-1:i+1] = '\n'  # an actual newline
                            i -= 1
                        elif c == 't':
                            text[i-1:i+1] = '\t'  # an actual tab
                            i -= 1
                        elif c in '"\'':
                            text[i-1:i] = ''    # remove the backslash
                            i -= 1
                        else:
                            # All others, we simply keep unmodified.
                            # Android itself actually seems to remove them,
                            # but this is for the developer to resolve;
                            # we're not trying to recreate the Android
                            # parser 100%, merely handle those aspects that
                            # are relevant to convert the text back and
                            # forth without loss.
                            pass
                        escaped = False


                i += 1

            # Join the string together again, but w/o EOF marker
            return "".join(text[:-1])

        # We need to recreate the contents of this tag; this is more
        # complicated as you might expect; firstly, there is nothing
        # built into lxml (or any other parse I have seen for that
        # matter). While it is possible to use the ``etree.tostring``
        # to render this tag and it's children, this still would give
        # us valid XML code; when in fact we want to decode everything
        # XML (including entities), *except* tags. Much more than that
        # though, the processing rules the Android xml format needs
        # require custom processing anyway.
        value = u""
        for ev, elem  in etree.iterwalk(tag, events=('start', 'end',)):
            is_root = elem == tag
            if ev == 'start':
                if not is_root:
                    # TODO: We are currently not dealing correctly with
                    # attribute values that need escaping.
                    params = "".join([" %s=\"%s\"" % (k, v) for k, v in elem.attrib.items()])
                    value += u"<%s%s>" % (elem.tag, params)
                if elem.text is not None:
                    t = elem.text
                    # Leading/Trailing whitespace is removed completely
                    # ONLY if there are now nested tags. Handle this before
                    # calling ``convert_text``, so that whitespace
                    # protecting quotes can still be considered.
                    if elem == tag and len(tag) == 0:
                        t = t.strip(WHITESPACE)
                    value += convert_text(t)
            elif ev == 'end':
                # The closing root tag has no info for us at all.
                if not is_root:
                    value += u"</%s>" % elem.tag
                    if elem.tail is not None:
                        value += convert_text(elem.tail)

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

        value = message.string

        # PREPROCESS
        # The translations may contain arbitrary XHTML, which we need
        # to inject into the DOM to properly output. That means parsing
        # it first.
        # This will now get really messy, since certain XML entities
        # we have unescaped for the translators convenience, while the
        # tag entities &lt; and &gt; we have not, to differentiate them
        # from actual nested tags. Is there any good way to restore this
        # properly?
        # TODO: In particular, the code below will once we do anything
        # bit more complicated with entities, like &amp;amp;lt;
        value = value.replace('&', '&amp;')
        value = value.replace('&amp;lt;', '&lt;')
        value = value.replace('&amp;gt;', '&gt;')

        # PARSE
        value_to_parse = "<string>%s</string>" % value
        try:
            string_el = etree.fromstring(value_to_parse)
        except etree.XMLSyntaxError:
            string_el = etree.fromstring(value_to_parse, loose_parser)
            print "Error: Translation contains invalid XHTML (for resource %s)" % message.context

        def quote(text):
            """Return ``text`` surrounded by quotes if necessary.
            """
            if text is None:
                return

            # If there is trailing or leading whitespace, even if it's
            # just a single space character, we need quoting.
            needs_quoting = text.strip(WHITESPACE) != text

            # Otherwise, there might be collapsible spaces inside the text.
            if not needs_quoting:
                space_count = 0
                for c in chain(text, [EOF]):
                    if c is not EOF and c in WHITESPACE:
                        space_count += 1
                        if space_count >= 2:
                            needs_quoting = True
                            break
                    else:
                        space_count = 0

            if needs_quoting:
                return '"%s"' % text
            return text

        def escape(text):
            """Escape all the characters we know need to be escaped
            in an Android XML file."""
            if text is None:
                return
            text = text.replace('\\', '\\\\')
            text = text.replace('\n', '\\n')
            text = text.replace('\t', '\\t')
            text = text.replace('\'', '\\\'')
            text = text.replace('"', '\\"')
            return text

        # POSTPROCESS
        for element in string_el.iter():
            # Strictly speaking, we wouldn't want to touch things
            # like the root elements tail, but it doesn't matter here,
            # since they are going to be empty string anyway.
            element.text = quote(escape(element.text))
            element.tail = quote(escape(element.tail))

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


def run():
    sys.exit(main(sys.argv) or 0)