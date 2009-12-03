"""Test the actual conversion of the text inside an Android xml file
and a gettext .po file; since the rules of both formats differ, the
actual characters/bytes of each version will differ, while still
representing the same localizable message.

Tests in here ensure that this conversation happens correctly; that is,
as closely to the way Android itself processes it's format as possible,
without modifying a string (in terms of significant content).

This currently follows the behavior I was seeing on an emulator using the
Android 2.0 SDK release.
"""

from android2po import xml2po
from StringIO import StringIO


def assert_convert(xml, po=None):
    """Helper that passes the string in ``xml`` through our xml
    parsing mechanism, and checks the resulting po catalog string
    against ``po``.

    If ``po`` is not given, we check against ``xml`` instead, i.e.
    expect the string to remain unchanged.
    """
    key = 'foo'
    catalog = xml2po(StringIO(
        '<resources><string name="%s">%s</string></resources>' % (key, xml)))
    match = po if po is not None else xml
    for message in catalog:
        if message.context == key:
            #print "'%s' == '%s'" % (message.id, match)
            print repr(message.id), '==', repr(match)
            assert message.id == match
            break
    else:
        raise KeyError()


class TestFromXML():
    """Test reading from Android's XML format.
    """

    def test_basic(self):
        """Test some basic string variations.
        """
        # No nested tags.
        assert_convert('bar')
        # Nested tags only.
        assert_convert('<b>world</b>')
        # [bug] Trailing text + nested tags.
        assert_convert('hello <b>world</b>')
        # Multiple levels of nesting.
        assert_convert('<b><u>hello</u> world</b>')

    def test_tags_and_attributes(self):
        """Test certain XML-inherited syntax elements, in particular,
        that attributes of nested tags are rendered properly.

        I haven't actually tested if Android even supports them, but
        there should be no damage from our side in persisting them.
        If they, say, aren't allowed, the developer will have to deal
        with it anyway.
        """
        assert_convert('<b name="">foo</b>')
        # Order is persisted.
        assert_convert('<b k1="1" k2="2" k3="3">foo</b>')
        # Quotes are normalized.
        assert_convert('<b k2=\'2\'>foo</b>', '<b k2="2">foo</b>')

        # Since we can't know whether a tag was self-closing, such
        # tags are going to be expanded when going through us.
        assert_convert('<b />', '<b></b>')

    def test_whitespace(self):
        """Test various whitespace handling scenarios.
        """
        # Intermediate whitespace is collapsed.
        assert_convert('a      b       c', 'a b c')
        # Leading and trailing whitespace is removed completely only
        # if no tags are nested.
        assert_convert('    a  ', 'a')
        # If there are nested tags, normal whitespace collapsing rules
        # apply at the beginning and end of the string instead.
        assert_convert('    <b></b>  ', ' <b></b> ')
        # Whitespace collapsing does not reach beyond a nested tag, i.e.
        # each text between two tags manages it's whitespace independently.
        assert_convert('   <b>   <u>    </u>  </b>  ', ' <b> <u> </u> </b> ')

        # Newlines and even tabs are considered whitespace as well.
        assert_convert('a    \n\n   \n   \n\n  b', 'a b')
        assert_convert('a  \t\t   \t  b', 'a b')

        # Quoting protects whitespace.
        assert_convert('"    a     b    "', '    a     b    ')

    def test_escaping(self):
        """Test escaping.
        """
        assert_convert(r'new\nline',  'new\nline')
        assert_convert(r'foo:\tbar',  'foo:\tbar')
        assert_convert(r'my name is \"earl\"',  'my name is "earl"')
        assert_convert(r'my name is \'earl\'',  'my name is \'earl\'')
        assert_convert(r'\\',  '\\')

        # XXX: Android seems to even normalize inserted newlines:
        #    r'\n\n\n\n\n' (as a literal string) ends up as ''
        #    r'a\n\n\n\n\n' (as a literal string) ends up as 'a'
        #    r'a\n\n\n\n\nb' (as a literal string) ends up as 'a\nb'
        # It doesn't do the same for tabs:
        #    r'a\t\t\t\tb' has the tabs included
        # Actually! This only seems to be the case when you output the
        # string using the log; setting it to the caption of a textview,
        # for example, keeps the multiple linebreaks.

        # A double slash can be used to protect escapes.
        assert_convert(r'new\\nline',  'new\\nline')

        # Edge case of having a backslash as the last char; Android
        # handles this as expected (removes it), and we also handle it
        # as expected from us: We keep it unchanged.
        # [bug] Used to throw an exception.
        assert_convert('edge-case\\')

    def test_quoting(self):
        """Android allows quoting using a "..." syntax.
        """
        # With multiple quote-blocks: whitespace is preserved within
        # the blocks, collapsed outside of them.
        assert_convert('   a"    c"   d  ', 'a    c d')
        # Test the special case of unbalanced quotes, which seems to
        # cause whitespace protection ONLY until the last block till
        # the end of the string, which *is* collapsed. Of course, in
        # this case we could assume that the standard tail trimming
        # is responsible for that phenomenon...
        assert_convert('"   a   b   ', '   a   b')
        # ...however, we are seeing the same thing when using nested
        # tags. Quoting cannot span across tag boundaries, and if you
        # try and thus have unbalanced quotes, you are still seeing
        # the strange behavior of the trailing whitespace not being
        # protected.
        assert_convert('"   a    b   <b></b>', '   a    b <b></b>')

        # Test an apostrophe inside quotes; we don't care much though,
        # we don't try to recreate Android's stricter error handling.
        # Instead, we just let it through in either case.
        assert_convert('"\'"', '\'')       # standalone   '
        assert_convert('"\\\'"', '\'')     # escaped:     \'

        # Quoting also works with the &quot; entity
        assert_convert('&quot;    &quot;', '    ')

    def test_entitites(self):
        """Test that various kinds of XML entities are correctly transcoded.
        """
        # Standard entities are decoded for the .po file.
        assert_convert('FAQ &amp; Help', 'FAQ & Help')
        assert_convert('Let&apos;s go!', 'Let\'s go!')
        assert_convert('A &#126; B', 'A ~ B')

        # An exception are &lt; and &gt; because we need to be able to
        # differentiate between actual nested tags in the XML and encoded
        # tags when converting back, those entities need to be persisted.
        assert_convert('&lt;b&gt;bold&lt;/b&gt;')

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