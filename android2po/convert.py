"""Contains the functions that do the hard work.

TODO: I would like to refactor this at some point. Right now, the xml=>po
process is already split into the read_xml() to convert an XML file into
a dict representation, and then converting this dict into a catalog.

You'd like to split the write process in the base way, so that we can write
Android resources XMLs by simply giving the data as a dict.

Here's how it could look like:

[FILE/STRING] -> read_xml [DICT] -> xml2po -> [CATALOG] -> po2xml -> [DICT] -> write_xml/build_xml

xml2po would be split from read_xml() for good, i.e. it would only accept
dicts, not filenames or file objects.
"""

from itertools import chain
from compat import OrderedDict
from lxml import etree
from babel.messages import Catalog


__all__ = ('xml2po', 'po2xml', 'read_xml', 'InvalidResourceError',)


class InvalidResourceError(Exception):
    pass


class UnsupportedResourceError(Exception):
    """A resource in a XML file can't be processed.
    """
    def __init__(self, reason):
        self.reason = reason


WHITESPACE = ' \n\t'     # Whitespace that we collapse
EOF = None


# Some AOSP projects like to include xliff:* tags to annotate
# strings with more information for translators. This is actually harder
# to support than it might look like: We want the translators to see at
# least a tag called "xliff", not the namespace URIs, but we currently
# don't have a way to define namespaces in the .po files (comments?),
# so in order to properly generate an XML on import, we can only deal
# with a fixed list of namespace that we now about.
KNOWN_NAMESPACES = {
    'urn:oasis:names:tc:xliff:document:1.2': 'xliff',
}


# The methods here sometimes need to notify the caller about warnings
# processing on; this is why they all take a ``warn_func`` argument.
# By default, if no warnfunc is passed, this dummy will be used.
dummy_warn = lambda message, severity=None: None

# The translation class that holds information about the translations
# themselves.
# TODO: It might be worth considering whether string-arrays should be
# implemented as a Translation instance that knows it's an array, rather
# than a list of Translation objects, as is currently the case; in
# particular, since comments, as currently implemented, are per
# string-array anyway, and are just repeated for each item.
class Translation():
    text = ""
    comments = []
    formatted = False

    def __init__(self, text, comments, formatted):
        self.text = text
        self.comments = comments
        self.formatted = formatted


def get_element_text(tag, name, warnfunc=dummy_warn):
    """Return a tuple of the contents of the lxml ``element`` with the
    Android specific stuff decoded and whether the text includes
    formatting codes.

    "Contents" isn't just the text; it handles nested HTML tags as well.
    """

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
        active_percent = False
        active_escape = False
        formatted = False
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
                    # Replace by a single space, will get rid of
                    # non-significant newlines/tabs etc.
                    text[i-space_count : i] = ' '
                    i -= space_count + 1
                space_count = 0
            elif space_count == 1:
                # At this point we have a single whitespace character,
                # but it might be a newline or tab. If we write this
                # kind of insignificant whitespace into the .po file,
                # it will be considered significant on import. So,
                # make sure that this kind of whitespace is always a
                # standard space.
                text[i-1] = ' '
                space_count = 0
            else:
                space_count = 0

            # Handle quotes
            if c == '"' and not active_escape:
                active_quote = not active_quote
                del text[i]
                i -= 1

            # If the string is run through a formatter, it will have
            # percentage signs for String.format
            if c == '%' and not active_escape:
                active_percent = not active_percent
            elif not active_escape and active_percent:
                formatted = True
                active_percent = False

            # Handle escapes
            if c == '\\':
                if not active_escape:
                    active_escape = True
                else:
                    # A double-backslash represents a single;
                    # simply deleting the current char will do.
                    del text[i]
                    i -= 1
                    active_escape = False
            else:
                if active_escape:
                    # Handle the limited amount of escape codes
                    # that we support.
                    # TODO: What about \r, or \r\n?
                    if c is EOF:
                        # Basically like any other char, but put
                        # this first so we can use the ``in`` operator
                        # in the clauses below without issue.
                        pass
                    elif c == 'n':
                        text[i-1 : i+1] = '\n'  # an actual newline
                        i -= 1
                    elif c == 't':
                        text[i-1 : i+1] = '\t'  # an actual tab
                        i -= 1
                    elif c in '"\'@':
                        text[i-1 : i] = ''        # remove the backslash
                        i -= 1
                    elif c == 'u':
                        # Unicode sequence. Android is nice enough to deal
                        # with those in a way which let's us just capture
                        # the next 4 characters and raise an error if they
                        # are not valid (rather than having to use a new
                        # state to parse the unicode sequence).
                        # Exception: In case we are at the end of the
                        # string, we support incomplete sequences by
                        # prefixing the missing digits with zeros.
                        # Note: max(len()) is needed in the slice due to
                        # trailing ``None`` element.
                        max_slice = min(i+5, len(text)-1)
                        codepoint_str = "".join(text[i+1 : max_slice])
                        if len(codepoint_str) < 4:
                            codepoint_str = u"0" * (4-len(codepoint_str)) + codepoint_str
                        print repr(codepoint_str)
                        try:
                            # We can't trust int() to raise a ValueError,
                            # it will ignore leading/trailing whitespace.
                            if not codepoint_str.isalnum():
                                raise ValueError(codepoint_str)
                            codepoint = unichr(int(codepoint_str, 16))
                        except ValueError:
                            raise UnsupportedResourceError('bad unicode escape sequence')

                        text[i-1 : max_slice] = codepoint
                        i -= 1
                    else:
                        # All others, remove, like Android does as well.
                        # However, Android does so silently, we show a
                        # warning so the dev can fix the problem.
                        warnfunc(('Resource "%s": removing unsupported '
                                  'escape sequence "%s"') % (
                                    name, "".join(text[i-1 : i+1])), 'warning')
                        text[i-1 : i+1] = ''
                        i -= 1
                    active_escape = False

            i += 1

        # Join the string together again, but w/o EOF marker
        return "".join(text[:-1]), formatted

    def get_tag_name(elem):
        """For tags without a namespace, returns ("tag", None).
        For tags with a known-namespace, returns ("prefix:tag", None).
        For tags with an unknown-namespace, returns ("tag", ("prefix", "ns"))
        """
        if elem.prefix:
            namespace = elem.nsmap[elem.prefix]
            raw_name = elem.tag[elem.tag.index('}')+1:]
            if namespace in KNOWN_NAMESPACES:
                return "%s:%s" % (KNOWN_NAMESPACES[namespace], raw_name), None
            return "%s:%s" % (elem.prefix, raw_name), (elem.prefix, namespace)
        return elem.tag, None

    # We need to recreate the contents of this tag; this is more
    # complicated than you might expect; firstly, there is nothing
    # built into lxml (or any other parser I have seen for that
    # matter). While it is possible to use ``etree.tostring``
    # to render this tag and it's children, this still would give
    # us valid XML code; when in fact we want to decode everything
    # XML (including entities), *except* tags. Much more than that
    # though, the processing rules the Android xml format needs
    # require custom processing anyway.
    value = u""
    formatted = False
    for ev, elem  in etree.iterwalk(tag, events=('start', 'end',)):
        is_root = elem == tag
        has_children = len(tag) > 0
        if ev == 'start':
            if not is_root:
                # Take care of the tag name, namespace and attributes.
                # Since we can't store namespace urls in a .po file, dealing
                # with (unknown) namespaces requires generating a xmlns
                # attribute.
                # TODO: We are currently not dealing correctly with
                # attribute values that need escaping.
                tag_name, to_declare = get_tag_name(elem)
                params = ["%s=\"%s\"" % (k, v) for k, v in elem.attrib.items()]
                if to_declare:
                    name, url = to_declare
                    params.append('xmlns:%s="%s"' % (name, url))
                params_str = " %s" % " ".join(params) if params else ""
                value += u"<%s%s>" % (tag_name, params_str)
            if elem.text is not None:
                t = elem.text
                # Leading/Trailing whitespace is removed completely
                # ONLY if there are no nested tags. Handle this before
                # calling ``convert_text``, so that whitespace
                # protecting quotes can still be considered.
                if is_root and not has_children and len(tag) == 0:
                    t = t.strip(WHITESPACE)

                # Resources that start with @ reference other resources.
                # While we aren't particularily interested in converting
                # those, we also can't do it right now because we wouldn't
                # be able to differ between literal @ characters and the
                # reference syntax during import.
                #
                # While it may seem a bit early to deal with this here, we
                # have no choice, because the caller needs *some* way of
                # differentating between an escaped literal '@' and this
                # kind of resource-reference. Since we unescape literals,
                # we need to do something with the reference-@.
                if is_root and not has_children and t and t[0] == '@':
                    raise UnsupportedResourceError(
                        'resource references (%s) are not supported' % t)

                converted_value, elem_formatted = convert_text(t)
                if elem_formatted:
                    formatted = True
                value += converted_value
        elif ev == 'end':
            # The closing root tag has no info for us at all.
            if not is_root:
                tag_name, _ = get_tag_name(elem)
                value += u"</%s>" % tag_name
                if elem.tail is not None:
                    converted_value, elem_formatted = convert_text(elem.tail)
                    if elem_formatted:
                        formatted = True
                    value += converted_value

    # Babel can't handle empty msgids, even when using a unique context;
    # not sure if this is a general gettext limitation, but it's not
    # unlikely that other tools would have problems, so it's for the better
    # in any case.
    if value == u'':
        raise UnsupportedResourceError('empty resources not supported')
    return value, formatted


def read_xml(file, warnfunc=dummy_warn):
    """Load all resource names from an Android strings.xml resource file.

    The result is a dict of ``name => value``, `with ``value`` being
    either a string (a single string tag), a list (a string-array tag) or
    a dict (a plurals tag).
    """
    result = OrderedDict()
    comment = []

    try:
        doc = etree.parse(file)
    except etree.XMLSyntaxError, e:
        raise InvalidResourceError(e)

    for tag in doc.getroot():
        if tag.tag == etree.Comment:
            comment.append(tag.text)
            continue
        if not 'name' in tag.attrib:
            comment = []
            continue
        if 'translatable' in tag.attrib:
            translatable = tag.attrib['translatable']
            if translatable == 'false':
                comment = []
                continue
        name = tag.attrib['name']
        if name in result:
            warnfunc('Duplicate resource id found: %s, ignoring.' % name,
                     'warning')
            comment = []
            continue

        if tag.tag == 'string':
            try:
                text, formatted = get_element_text(tag, name, warnfunc)
            except UnsupportedResourceError, e:
                warnfunc('"%s" has been skipped, reason: %s' % (
                    name, e.reason), 'info')
            else:
                translation = Translation(text, comment, formatted)
                result[name] = translation
            comment = []
        elif tag.tag == 'string-array':
            result[name] = list()
            for child in tag.findall('item'):
                try:
                    text, formatted = get_element_text(child, name, warnfunc)
                except UnsupportedResourceError, e:
                    # XXX: We currently can't handle this, because even if
                    # we write out a .po file with the proper array
                    # indices, and items like this one missing, during
                    # import we still need to write out those items that
                    # we have now skipped, since the Android format is only
                    # a simple list of items, i.e. we need to specify the
                    # fully array, and can't override individual items on
                    # a per-translation basis.
                    #
                    # To fix this, we have two options: Either we support
                    # annotating gettext messages, in which case we could
                    # indicate whether or not a message like this was a
                    # reference and should be escaped or not. Or, better,
                    # the import process would need to use information from
                    # the default strings.xml file to fill the vacancies.
                    warnfunc(('Warning: The array "%s" contains that can\'t '+
                              'be processed (reason: %s) - the array will be '
                              'incomplete') % (name, e.reason), 'warning')
                else:
                    translation = Translation(text, comment, formatted)
                    result[name].append(translation)
            # Reset the comments after all the children have been processed.
            comment = []

        # TODO:
        #elif tag.tag == 'plurals':
        #    result[name] = dict()
        #    <for child in tag.find('item'):
        #        result[name].append(read_value)

    return result


def xml2po(file, translations=None, filter=None, warnfunc=dummy_warn):
    """Return the Android string resource in ``file`` as a babel
    .po catalog.

    If given, the Android string resource in ``translations`` will be
    used for the translated values. In this case, the returned value
    is a 2-tuple (catalog, unmatched), with the latter being a list of
    Android string resource names that are in the translated file, but
    not in the original.

    Both arguments may also be an already loaded dict of xml strings,
    as returned by ``read_xml``.
    """
    original_strings = file if isinstance(file, dict) else read_xml(file, warnfunc)
    trans_strings = None
    if translations is not None:
        trans_strings = translations \
                      if isinstance(translations, dict) \
                      else read_xml(translations, warnfunc)

    catalog = Catalog()
    for name, org_value in original_strings.iteritems():
        if filter and filter(name):
            continue

        trans_value = None
        if trans_strings:
            trans_value = trans_strings.pop(name, trans_value)

        if isinstance(org_value, list):
            # a string-array, write as "name:index"
            if len(org_value) == 0:
                warnfunc("Warning: string-array '%s' is empty" % name, 'warning')
                continue

            if trans_value and not isinstance(trans_value, list):
                warnfunc(('""%s" is a string-array in the reference file, '
                          'but not in the translation.') % name, 'warning')
                # makes further processing easier if we can assume
                # this is a list
                trans_value = []
            elif trans_value is None:
                trans_value = []

            for index, item in enumerate(org_value):
                item_trans = trans_value[index].text if index < len(trans_value) else u''
                if item.text == item_trans:
                    item_trans = u''

                # If the string has formatting markers, indicate it in the gettext output
                flags = []
                if item.formatted:
                    flags.append('c-format')

                ctx = "%s:%d" % (name, index)
                catalog.add(item.text, item_trans, auto_comments=item.comments,
                            flags=flags, context=ctx)

        else:
            if trans_value and org_value.text == trans_value.text:
                trans_value = None

            # a normal string
            flags = []

            # If the string has formatting markers, indicate it in the gettext output
            if org_value.formatted:
                flags.append('c-format')

            catalog.add(org_value.text, trans_value.text if trans_value else u'',
                        flags=flags, auto_comments=org_value.comments, context=name)

    if trans_strings is not None:
        # At this point, trans_strings only contains those for which
        # no original existed.
        return catalog, trans_strings.keys()
    else:
        return catalog


def write_to_dom(elem_name, value, message, namespaces=None, warnfunc=dummy_warn):
    """Create a DOM object with the tag name ``elem_name``, containing
    the string ``value`` formatted according to Android XML rules.

    The result might be a <string>-tag, or a <item>-tag as found as
    children of <string-array>, for example.

    It might feel awkward at first that the Android-XML formatting
    does not happen in a separate method, but is part of the creation
    of a tag, but due to us having to do certain formatting based on
    child DOM elements that ``value`` may include, the two fit
    naturally together (see the POSTPROCESS section of this function).

    If one of our supported namespace prefixes is used within nested tags
    inside ``value``, the appropriate data is added to the
    ``namespaces`` dict, if given, so the caller may generate the
    proper declarations.
    """

    loose_parser = etree.XMLParser(recover=True)

    if value is None:
        value = ''

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
    #
    # Namespace handling complicates things a bit. We want the value
    # we inject to support nested XML with certain supported namespace
    # prefixes, but lxml doesn't seem to allow us to predefine those
    # (https://answers.launchpad.net/lxml/+question/111660).
    # So we use a wrapping element with xmlns attributes that we ignore
    # after parsing.
    namespace_text = " ".join(['xmlns:%s="%s"' % (prefix, ns) for ns, prefix in KNOWN_NAMESPACES.items()])
    value_to_parse = "<root %s><%s>%s</%s></root>" % (namespace_text, elem_name, value, elem_name)
    try:
        elem = etree.fromstring(value_to_parse)
    except etree.XMLSyntaxError, e:
        elem = etree.fromstring(value_to_parse, loose_parser)
        warnfunc(('Message %s contains invalid XHTML (%s); Falling back to '
                  'loose parser.') % (message.context, e), 'warning')

    # Within the generated DOM, search for use of one of our supported
    # namespace prefixes, so we can keep track of which namespaces have
    # been used.
    if namespaces is not None:
        for c in elem.iterdescendants():
            if c.prefix:
                nsuri = c.nsmap[c.prefix]
                if nsuri in KNOWN_NAMESPACES:
                    namespaces[KNOWN_NAMESPACES[nsuri]] = nsuri
    # Then, proceed with the actual element that we wanted to create.
    elem = elem[0]

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
        # Strictly speaking, @ only needs to be escaped when
        # it's the first character. But, since our target XML
        # files are basically generate-only and unlikely to be
        # edited by a user, don't bother with pretty.
        text = text.replace('@', '\\@')
        return text

    # POSTPROCESS
    for child_elem in elem.iter():
        # Strictly speaking, we wouldn't want to touch things
        # like the root elements tail, but it doesn't matter here,
        # since they are going to be empty string anyway.
        child_elem.text = quote(escape(child_elem.text))
        child_elem.tail = quote(escape(child_elem.tail))

    return elem


def po2xml(catalog, with_untranslated=True, filter=None, warnfunc=dummy_warn):
    """Convert the gettext catalog in ``catalog`` to an XML DOM.

    This currently relies entirely in the fact that we can use the context
    of each message to specify the Android resource name (which we need
    to do to handle duplicates, but this is a nice by-product). However
    that also means we cannot handle arbitrary catalogs.

    The latter would in theory be possible by using the original,
    untranslated XML to match up a messages id to a resource name, but
    right now we don't support this (and it's not clear it would be
    necessary, even).

    If ``with_untranslated`` is given, then strings in the catalog
    that have no translation are written out with the original id. In
    the case of a string-array, if ``with_untranslated`` is NOT
    specified, then only strings that DO have a translation are written
    out, potentially causing the array to be incomplete.
    TODO: This should not be the case: Arrays should always contain
    all elements, whether translated or not (using an empty string
    instead). When writing tests for this, make sure we generally test
    the with_untranslated mode, i.e. also the behavior for normal strings.
    """
    # First, process the catalog into a Python sort-of-tree structure.
    # We can't write directly to the XML output, since stuff like
    # string-array items are not guaranteed to appear in the correct
    # order in the calalog. We "xml tree" pulls these things together.
    # It is quite similar to the structure returned by read_xml().
    xml_tree = OrderedDict()
    for message in catalog:
        if not message.id:
            # This is the header
            continue

        if not message.string and not with_untranslated:
            # Untranslated.
            continue

        if not message.context:
            warnfunc(('Ignoring message "%s": has no context; somebody other '+
                      'than android2po seems to have added to this '+
                      'catalog.') % message.id, 'error')
            continue

        if filter and filter(message):
            continue

        value = message.string or message.id

        if ':' in message.context:
            # A colon indicates a string array; collect all the
            # strings of this array with their indices, so when
            # we're done processing the whole catalog, we can
            # sort by index and restore the proper array order.
            name, index = message.context.split(':', 2)
            xml_tree.setdefault(name, {})
            if index in xml_tree[name]:
                warnfunc(('Duplicate index %s in array "%s"; ignoring '+
                          'the message. The catalog has possibly been '+
                          'corrupted.') % (index, name), 'error')
            xml_tree[name][index] = value
        else:
            xml_tree[message.context] = value

    # Convert the xml tree we've built into an actual Android XML DOM.
    root_tags = []
    namespaces_used = {}
    for name, value in xml_tree.iteritems():
        if isinstance(value, dict):
            # string-array - first, sort by index
            array_el = etree.Element('string-array')
            array_el.attrib['name'] = name
            for k in sorted(value, cmp=lambda x,y: cmp(int(x), int(y))):
                item_el = write_to_dom('item', value[k], message, namespaces_used, warnfunc)
                array_el.append(item_el)
            root_tags.append(array_el)
        else:
            # standard string
            string_el = write_to_dom('string', value, message, namespaces_used, warnfunc)
            string_el.attrib['name'] = name
            root_tags.append(string_el)

    # Generate the root element, define the namespaces that have been
    # used across all of our child elements.
    root_el = etree.Element('resources', nsmap=namespaces_used)
    for e in root_tags:
        root_el.append(e)
    return root_el
