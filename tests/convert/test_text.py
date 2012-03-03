# coding: utf8
"""Test the actual conversion of the text inside an Android xml file
and a gettext .po file; since the rules of both formats differ, the
actual characters/bytes of each version will differ, while still
representing the same localizable message.

Tests in here ensure that this conversation happens correctly; that is,
as closely to the way Android itself processes it's format as possible,
without modifying a string (in terms of significant content).

This currently follows the behavior I was seeing on an emulator running
the Android 1.6 SDK release, with an application compiled against the
2.0 SDK release.
"""

from __future__ import absolute_import

import re
from StringIO import StringIO
from lxml import etree
from babel.messages import Catalog
from nose.tools import assert_raises
from android2po import xml2po, po2xml, read_xml, write_xml
from ..helpers import TestWarnFunc


class TestFromXML():
    """Test reading from Android's XML format.
    """

    @classmethod
    def assert_convert(cls, xml, po=None, namespaces={}, warnfunc=None):
        """Helper that passes the string in ``xml`` through our xml
        parsing mechanism, and checks the resulting po catalog string
        against ``po``.

        If ``po`` is not given, we check against ``xml`` instead, i.e.
        expect the string to remain unchanged.
        """
        key = 'test'
        extra = {}
        warnfunc = warnfunc or TestWarnFunc()
        xmltree = read_xml(StringIO(
            '<resources %s><string name="%s">%s</string></resources>' % (
                " ".join(['xmlns:%s="%s"' % (name, url)
                          for name, url in namespaces.items()]),
                key, xml)), warnfunc=warnfunc)
        catalog = xml2po(xmltree, warnfunc=warnfunc)
        match = po if po is not None else xml
        for message in catalog:
            if message.context == key:
                #print "'%s' == '%s'" % (message.id, match)
                print repr(match), '==', repr(message.id)
                assert message.id == match
                break
        else:
            raise KeyError(warnfunc.logs)

    @classmethod
    def assert_convert_error(cls, xml, error_match):
        """Ensure that the given xml resource string cannot be processed and
        results in the given error.
        """
        wfunc = TestWarnFunc()
        key = 'test'
        catalog = xml2po(read_xml(
            StringIO('<resources><string name="%s">%s</string></resources>' % (
                key, xml)), warnfunc=wfunc))
        assert not catalog.get(xml, context=key)
        for line in wfunc.logs:
            if error_match in line:
                return
        assert False, "error output not matched"

    def test_helpers_negative(self):
        """Ensure that the helper functions we use (self.assert_*) work
        by calling them in a way in which they should fail.
        """
        assert_raises(AssertionError, self.assert_convert_error, r'good', '')
        assert_raises(AssertionError, self.assert_convert_error, r'',
                      'will not be found 12345')

    def test_basic(self):
        """Test some basic string variations.
        """
        # No nested tags.
        self.assert_convert('bar')
        # Nested tags only.
        self.assert_convert('<b>world</b>')
        # [bug] Trailing text + nested tags.
        self.assert_convert('hello <b>world</b>')
        # Multiple levels of nesting.
        self.assert_convert('<b><u>hello</u> world</b>')

    def test_tags_and_attributes(self):
        """Test certain XML-inherited syntax elements, in particular,
        that attributes of nested tags are rendered properly.

        I haven't actually tested if Android even supports them, but
        there should be no damage from our side in persisting them.
        If they, say, aren't allowed, the developer will have to deal
        with it anyway.
        """
        self.assert_convert('<b name="">foo</b>')
        # Order is persisted.
        self.assert_convert('<b k1="1" k2="2" k3="3">foo</b>')
        # Quotes are normalized.
        self.assert_convert('<b k2=\'2\'>foo</b>', '<b k2="2">foo</b>')

        # Since we can't know whether a tag was self-closing, such
        # tags are going to be expanded when going through us.
        self.assert_convert('<b />', '<b></b>')

    def test_namespaces(self):
        """Some AOSP projects like to include xliff tags to annotate
        strings with more information for translators.
        """

        # Test namespaces that we know about; thos can be put into the
        # .po file without a xmlns attribute; the downside is that we
        # must enforce a certain prefix, and can't just use whatever the
        # user defined.
        self.assert_convert('Shortcut <foo:g id="name" example="Browser">%s</foo:g> already exists',
                            'Shortcut <xliff:g id="name" example="Browser">%s</xliff:g> already exists',
                            namespaces={'foo': 'urn:oasis:names:tc:xliff:document:1.2'})

        # Test with an unknown namespace. We must ensure that the namespace
        # url is added to the tag we write to the .po file, or we won't be
        # able to properly generate the namespace back when importing (since
        # we have no other place to store the namespace url).
        self.assert_convert('Shortcut <my:g>%s</my:g> already exists',
                            'Shortcut <my:g xmlns:my="urn:custom">%s</my:g> already exists',
                            namespaces={'my': 'urn:custom'})


    def test_whitespace(self):
        """Test various whitespace handling scenarios.
        """
        # Intermediate whitespace is collapsed.
        self.assert_convert('a      b       c', 'a b c')
        # Leading and trailing whitespace is removed completely only
        # if no tags are nested.
        self.assert_convert('    a  ', 'a')
        # If there are nested tags, normal whitespace collapsing rules
        # apply at the beginning and end of the string instead.
        self.assert_convert('    <b></b>  ', ' <b></b> ')
        # Whitespace collapsing does not reach beyond a nested tag, i.e.
        # each text between two tags manages it's whitespace independently.
        self.assert_convert('   <b>   <u>    </u>  </b>  ', ' <b> <u> </u> </b> ')

        # Newlines and even tabs are considered whitespace as well.
        self.assert_convert('a    \n\n   \n   \n\n  b', 'a b')
        self.assert_convert('a  \t\t   \t  b', 'a b')
        # [bug] Edge case in which a non-significant newline/tab used to
        # end up in the output (when the last whitespace character was
        # such a newline or tab (or other whitespace other than 'space').
        self.assert_convert('a\n\n\nb', 'a b')
        self.assert_convert('a\t\t\tb', 'a b')
        # [bug] This is a related edge case: A single non-significant
        # newline or tab must not be maintained as an actual newline/tab,
        # but as a space.
        self.assert_convert('\n<b></b>', ' <b></b>')

        # An all whitespace string isn't even included.
        assert_raises(KeyError, self.assert_convert, '   ', '')

        # Quoting protects whitespace.
        self.assert_convert('"    a     b    "', '    a     b    ')

    def test_escaping(self):
        """Test escaping.
        """
        self.assert_convert(r'new\nline',  'new\nline')
        self.assert_convert(r'foo:\tbar',  'foo:\tbar')
        self.assert_convert(r'my name is \"earl\"',  'my name is "earl"')
        self.assert_convert(r'my name is \'earl\'',  'my name is \'earl\'')
        self.assert_convert(r'\\',  '\\')

        # Test a practical case of a double-backslash protecting an
        # escape sequence.
        self.assert_convert(r'\\n',  r'\n')

        # XXX: Android seems to even normalize inserted newlines:
        #    r'\n\n\n\n\n' (as a literal string) ends up as ''
        #    r'a\n\n\n\n\n' (as a literal string) ends up as 'a'
        #    r'a\n\n\n\n\nb' (as a literal string) ends up as 'a\nb'
        # It doesn't do the same for tabs:
        #    r'a\t\t\t\tb' has the tabs included
        # Actually! This only seems to be the case when you output the
        # string using the log; setting it to the caption of a textview,
        # for example, keeps the multiple linebreaks.

        # @ is used to reference other resources, but if it's escaped,
        # we want a raw @ instead. Note that for this to work well,
        # we need to make sure we don't include unescaped @-resource
        # reference at all in the gettext catalogs.
        self.assert_convert(r'\@string/app_name', '@string/app_name')
        self.assert_convert(r'foo \@test bar', 'foo @test bar')

        # A double slash can be used to protect escapes.
        self.assert_convert(r'new\\nline',  'new\\nline')

        # Edge case of having a backslash as the last char; Android
        # handles this as expected (removes it), and we also handle it
        # as expected from us: We keep it unchanged.
        # [bug] Used to throw an exception.
        self.assert_convert('edge-case\\')

    def test_unicode_sequences(self):
        """Test unicode escape codes.
        """
        # The simple cases.
        self.assert_convert(r'\u2022',  u'•')
        self.assert_convert(r'\u21F6',  u'⇶')    # uppercase hex
        self.assert_convert(r'\u21f6',  u'⇶')    # lowercase hex
        self.assert_convert(r'\u21f65',  u'⇶5')

        # The error cases.
        self.assert_convert_error(r'\uzzzz', 'bad unicode')
        self.assert_convert_error(r'\u fin',  'bad unicode')
        self.assert_convert_error(r'\u12 fin',  'bad unicode')
        self.assert_convert_error(r'\uzzzz foo',  'bad unicode')
        # Special cases due to how Python's int() works - it ignores
        # trailing or leading whitespace, which can cause incorrect
        # sequences to be converted nontheless.
        self.assert_convert_error(r'\u     |', 'bad unicode')
        self.assert_convert_error(r'\u  11', 'bad unicode')
        self.assert_convert_error(r'\u11   |', 'bad unicode')
        self.assert_convert_error(r'\u11 |', 'bad unicode')
        self.assert_convert_error(r'\u11\t\t', 'bad unicode')

        # Of course, this wouldln't be the Android resource format
        # if there weren't again special rules about how this works
        # when we are at the end of a string; incomplete sequences
        # are allowed here, with the missing digets assumed to be
        # zero (big-endian).
        self.assert_convert(r'\u219',  u'ș')
        self.assert_convert(r'\u21',  u'!')
        # Different from other special cases, a trailing whitespace
        # is not allowed here though.
        # XXX Making this work right: It's not entirely straightforward
        # due to the string being trimmed before the unicode unescaping
        # code get's it's hands on it.
        #self.assert_convert_error(r'\u21 ',  'bad unicode')


    def test_unknown_escapes(self):
        """Test an unknown escape sequence is removed.
        """
        wfunc = TestWarnFunc()
        self.assert_convert(r'foo:\kbar',  'foo:bar', warnfunc=wfunc)
        assert len(wfunc.logs) == 1
        assert 'unsupported escape' in wfunc.logs[0]

    def test_quoting(self):
        """Android allows quoting using a "..." syntax.
        """
        # With multiple quote-blocks: whitespace is preserved within
        # the blocks, collapsed outside of them.
        self.assert_convert('   a"    c"   d  ', 'a    c d')
        # Test the special case of unbalanced quotes, which seems to
        # cause whitespace protection ONLY until the last block till
        # the end of the string, which *is* collapsed. Of course, in
        # this case we could assume that the standard tail trimming
        # is responsible for that phenomenon...
        self.assert_convert('"   a   b   ', '   a   b')
        # ...however, we are seeing the same thing when using nested
        # tags. Quoting cannot span across tag boundaries, and if you
        # try and thus have unbalanced quotes, you are still seeing
        # the strange behavior of the trailing whitespace not being
        # protected.
        self.assert_convert('"   a    b   <b></b>', '   a    b <b></b>')

        # Quoting also protects other kinds of whitespace.
        self.assert_convert('"   \n\t\t   \n\n "', '   \n\t\t   \n\n ')

        # Test an apostrophe inside quotes; we don't care much though,
        # we don't try to recreate Android's stricter error handling.
        # Instead, we just let it through in either case.
        self.assert_convert('"\'"', '\'')       # standalone   '
        self.assert_convert('"\\\'"', '\'')     # escaped:     \'

        # Quoting also works with the &quot; entity
        self.assert_convert('&quot;    &quot;', '    ')

    def test_entitites(self):
        """Test that various kinds of XML entities are correctly transcoded.
        """
        # Standard entities are decoded for the .po file.
        self.assert_convert('FAQ &amp; Help', 'FAQ & Help')
        self.assert_convert('Let&apos;s go!', 'Let\'s go!')
        self.assert_convert('A &#126; B', 'A ~ B')

        # An exception are &lt; and &gt; because we need to be able to
        # differentiate between actual nested tags in the XML and encoded
        # tags when converting back, those entities need to be persisted.
        self.assert_convert('&lt;b&gt;bold&lt;/b&gt;')

    def test_strange_escaping(self):
        """TODO: There is a somewhat strange phenomenon in the Android
        parser that we don't handle yet.
           (1)  'a            '   yields   'a'    but
           (2)  'a  \ '           yields   'a '   and
           (3)  'a   \z   '       yields   'a '.
           (4)  'a \ \ \ \ '      yields   'a'
        (2) and (3) would look like a \-sequence counting as a break for
        whitespace collapsing, but (4) doesn't fit into this explanation.
        """
        pass


class TestToXML():
    """Test writing to Android XML files.
    """

    @classmethod
    def assert_convert(cls, po, xml=None, namespaces={}):
        """Helper that passes the string in ``po`` through our po
        to xml converter, and checks the resulting xml string value
        against ``xml``.

        If ``xml`` is not given, we check against ``po`` instead, i.e.
        expect the string to remain unchanged.
        """
        key = 'test'
        catalog = Catalog()
        catalog.add(po, po, context=key)
        warnfunc = TestWarnFunc()
        dom = write_xml(po2xml(catalog, warnfunc=warnfunc), warnfunc=warnfunc)
        elem = dom.xpath('/resources/string[@name="%s"]' % key)[0]
        elem_as_text = etree.tostring(elem, encoding=unicode)
        value = re.match("^[^>]+>(.*)<[^<]+$", elem_as_text).groups(1)[0]
        match = xml if xml is not None else po
        print "'%s' == '%s'" % (value, match)
        print repr(value), '==', repr(match)
        assert value == match

        # If ``namespaces`` are set, the test expects those to be defined
        # in the root of the document
        for prefix, uri in namespaces.items():
            assert dom.nsmap[prefix] == uri

        # In this case, the reverse (converting back to po) always needs to
        # give us the original again, so this allows for a nice extra check.
        if not match:    # Skip this if we are doing a special, custom match.
            TestFromXML.assert_convert(match, po, namespaces)

        return warnfunc

    def test_basic(self):
        """Test some basic string variations.
        """
        # No nested tags.
        self.assert_convert('bar')
        # Nested tags.
        self.assert_convert('<b>foo</b>')
        # Multiple levels of nesting.
        self.assert_convert('<b><u>foo</u>bar</b>')

    def test_whitespace(self):
        """Test whitespace from the .po file is properly quoted within
        the xml file.
        """
        # In the default case, we can copy the input 1:1
        self.assert_convert('hello world')
        # However, if the input contains consecutive whitespace that would
        # be collapsed, we simply escape the whole thing.
        self.assert_convert('hello     world', '"hello     world"')
        self.assert_convert(' before and after ', '" before and after "')

        # If nested tags are used, the quoting needs to happen separately
        # for each block.
        self.assert_convert('   <b>inside</b>  ', '"   "<b>inside</b>"  "')
        self.assert_convert('<b>  inside  </b>bcd', '<b>"  inside  "</b>bcd')
        # As we know, if there are no need tags, leading and trailing
        # whitespace is trimmed fully. We thus need to protect it even if
        # there is just a single space. We currently handle this very roughly,
        # be just quoting any such whitespace, even if it's not strictly
        # necessary. TODO: This could be improved!
        self.assert_convert(' a ', '" a "')
        self.assert_convert('<b>hello</b> world', '<b>hello</b>" world"')

        # Note newlines and tabs here; while they are considered collapsible
        # inside Android's XML format, we only put significant whitespace
        # our .po files. Ergo, when importing, multiple newlines (or tabs)
        # will either need to be quoted, or escaped. We chose the latter.
        self.assert_convert('a \n\n\n b \t\t\t c', 'a \\n\\n\\n b \\t\\t\\t c')

    def test_namespaces(self):
        """Some AOSP projects like to include xliff tags to annotate
        strings with more information for translators.
        """

        # Test a namespace prefix that is know to us. Such prefixes may
        # be used in the .po file (and generated by us for .po files),
        # without the need to define that prefix via an xmlns attribute
        # on the tag in question itself.
        #
        # Usage of such a prefix in any string causes the prefix/namespaces
        # to be defined at the root-level.
        self.assert_convert('Shortcut <xliff:g id="name" example="Browser">%s</xliff:g> already exists',
                            '"Shortcut "<xliff:g id="name" example="Browser">%s</xliff:g>" already exists"',
                            namespaces={'xliff': 'urn:oasis:names:tc:xliff:document:1.2'})

        # Test with an unknown namespace. We don't really do anything
        # special here, we just require that the prefix be defined directly
        # on the tag in question.
        self.assert_convert('A <my:g xmlns:my="urn:custom">%s</my:g> B',
                            '"A "<my:g xmlns:my="urn:custom">%s</my:g>" B"')

    def test_entities(self):
        """Test entity conversion when putting stuff into XML.
        """
        # A raw amp is properly encoded.
        self.assert_convert('FAQ & Help', 'FAQ &amp; Help')
        # Encoded tags are maintained literally, are not further escaped.
        self.assert_convert('&lt;b&gt;bold&lt;/b&gt;', '&lt;b&gt;bold&lt;/b&gt;')

        # apos and quot are not using the entity, but the raw character;
        # although both need to be escaped, of course, see the
        # separate testing we do for that.
        self.assert_convert("'", "\\'")
        self.assert_convert('"', '\\"')

    def test_escaping(self):
        # Quotes are escaped.
        self.assert_convert('Let\'s go', 'Let\\\'s go')
        self.assert_convert('Pete "the horn" McCraw', 'Pete \\"the horn\\" McCraw')
        # The apos is even escaped when quoting is already applied. This
        # is not strictly necessary, but doesn't hurt and is easier for us.
        # Patches to improve that behavior are welcome, of course.
        self.assert_convert('   \'   ', '"   \\\'   "')

        # Newlines and tabs are replaced by their escape sequences;
        # whitespace we always consider significant in .po, so multiple
        # newlines/tabs are not collapsed.
        self.assert_convert('line1\n\n\nline3', 'line1\\n\\n\\nline3')
        self.assert_convert('line1\t\t\tline3', 'line1\\t\\t\\tline3')

        # Also, backslash are escaped into double backslashes.
        self.assert_convert('\\', r'\\')

        # @ is used to reference other resources and needs to be escaped.
        self.assert_convert('@string/app_name', r'\@string/app_name')
        self.assert_convert('foo @test bar', r'foo \@test bar')

        # Test a practical case of a double backslash used to protect
        # what would otherwise be considered a escape sequence.
        self.assert_convert('\\n', r'\\n')

        # Unicode escape sequences get converted to the actual unicode
        # character on export (see issue #6), but there is not good way
        # for us to decide which characters we should escape on import.
        # Fortunately, the resource files are unicode, so it's ok if we
        # place the actual codepoint there.
        self.assert_convert(u'•', u'•')

    def test_invalid_xhtml(self):
        """The .po contains invalid XHTML."""
        wfunc = self.assert_convert('<b>foo</b', xml='<b>foo</b>')
        assert 'contains invalid XHTML' in wfunc.logs[0]
