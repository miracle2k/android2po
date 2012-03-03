"""Various conversion-special cases.
"""

from __future__ import absolute_import

from StringIO import StringIO
from lxml import etree
from babel.messages import Catalog
from nose.tools import assert_raises
from android2po import xml2po, po2xml, read_xml, write_xml
from ..helpers import TempProject, TestWarnFunc


def xmlstr2po(string):
    return xml2po(read_xml(StringIO(string)))


def test_trailing_whitespace():
    # [bug] Make sure that whitespace after the <string> tag does not
    # end up as part of the value.
    catalog = xmlstr2po(
        '<resources><string name="foo">bar</string>    \t\t  </resources>')
    assert list(catalog)[1].id == 'bar'


def test_translatable():
    """Strings marked as translatable=False will be skipped.
    """
    catalog = xmlstr2po(
        '<resources><string name="foo" translatable="false">bar</string></resources>')
    assert len(catalog) == 0

    catalog = xmlstr2po(
        '<resources><string name="foo" translatable="true">bar</string></resources>')
    assert list(catalog)[1].id == 'bar'

    catalog = xmlstr2po(
        '<resources><string-array name="foo" translatable="false"><item>bla</item></string-array></resources>')
    assert len(catalog) == 0


def test_formatted():
    """Strings with "%1$s" and other Java-style format markers
       will be marked as c-format in the gettext flags.
    """
    catalog = xmlstr2po(
        '<resources><string name="foo">foo %1$s bar</string></resources>')
    assert "c-format" in list(catalog)[1].flags

    catalog = xmlstr2po(
        '<resources><string name="foo">foo %% bar</string></resources>')
    assert "c-format" not in list(catalog)[1].flags

    catalog = xmlstr2po(
        '<resources><string name="foo">foo</string></resources>')
    assert "c-format" not in list(catalog)[1].flags

    catalog = xmlstr2po(
        '<resources><string-array name="foo"><item>foo %1$s bar</item></string-array></resources>')
    assert "c-format" in list(catalog)[1].flags

    catalog = xmlstr2po(
        '<resources><string-array name="foo"><item>foo %% bar</item></string-array></resources>')
    assert "c-format" not in list(catalog)[1].flags

    catalog = xmlstr2po(
        '<resources><string-array name="foo"><item>bar</item></string-array></resources>')
    assert "c-format" not in list(catalog)[1].flags

    # Babel likes to add python-format
    catalog = xmlstr2po(
        '<resources><string name="foo">foo %s bar</string></resources>')
    assert "c-format" in list(catalog)[1].flags
    assert not "python-format" in list(catalog)[1].flags

    catalog = xmlstr2po(
        '<resources><string-array name="foo"><item>foo %s bar</item></string-array></resources>')
    assert "c-format" in list(catalog)[1].flags
    assert not "python-format" in list(catalog)[1].flags

    # Ensure that Babel doesn't add python-format on update ("export")
    # either. Yes, this is hard to get rid of.
    p = TempProject(default_xml={'foo': 'with %s format'})
    try:
        p.program('init', {'de': ''})
        p.program('export')
        catalog = p.get_po('de.po')
        assert not 'python-format' in list(catalog)[1].flags
    finally:
        p.delete()


def test_invalid_xhtml():
    """Ensure we can deal with broken XML in messages.
    """
    c = Catalog()
    c.add('Foo', '<i>Tag is not closed', context="foo")

    # [bug] This caused an exception in 16263b.
    dom = write_xml(po2xml(c))

    # The tag was closed automatically (our loose parser tries to fix errors).
    assert etree.tostring(dom) == '<resources><string name="foo"><i>Tag is not closed</i></string></resources>'


def test_untranslated():
    """Test that by default, untranslated strings are not included in the
    imported XML.
    """
    catalog = Catalog()
    catalog.add('green', context='color1')
    catalog.add('red', 'rot', context='color2')
    assert po2xml(catalog) == {'color2': 'rot'}

    # If with_untranslated is passed, then all strings are included.
    # Note that arrays behave differently (they always include all
    # strings), and this is tested in test_string_arrays.py).
    assert po2xml(catalog, with_untranslated=True) ==\
           {'color1': 'green', 'color2': 'rot'}


class Xml2PoTest:
    """Helper to test xml2po() with ability to check warnings.
    """
    @classmethod
    def make_raw(cls, content):
        logger = TestWarnFunc()
        return xml2po(read_xml(StringIO(content), warnfunc=logger),
                      warnfunc=logger), logger.logs

    @classmethod
    def make(cls, name, value):
        return cls.make_raw('<resources><string name="%s">%s</string></resources>' % (
            name, value))


class TestAndroidResourceReferences(Xml2PoTest):
    """Dealing with things like @string/app_name is not quite
    as straightforward as one might think.

    Note that the low-level escaping is tested in test_text.py.
    """

    def test_not_exported(self):
        """Strings with @-references are not being included during
        export.
        """
        catalog, logs = self.make('foo', '@string/app_name')
        assert len(catalog) == 0

        # A log message was printed
        assert 'resource reference' in logs[0]

        # Leading whitespace is stripped, as usual...
        catalog, _ = self.make('foo', '     @string/app_name     ')
        assert len(catalog) == 0

        # ...except if this is HTML.
        catalog, _ = self.make('foo', '@string/app_name<b>this is html</b>')
        assert len(catalog) == 1

    def test_string_array(self):
        """string-arrays that include @references are even more
        complicated. We don't currently support them properly, and
        need to raise a warning.
        """
        catalog, logs = self.make_raw('''
              <resources><string-array name="test">
                  <item>no-ref</item>
                  <item>@ref</item>
                  <item>@seems <b>like a ref</b></item>
              </string-array></resources>''')
        # One item, the reference, will be missing.
        assert len(catalog) == 2

        # A warning was printed
        assert 'resource reference' in logs[0]


def test_empty_resources():
    """Empty resources are removed and not included in a catalog.
    """
    catalog, logs = Xml2PoTest.make('foo', '     ')
    assert len(catalog) == 0
    assert 'empty' in logs[0]

    catalog, logs = Xml2PoTest.make_raw('''
        <resources>
            <string-array name="test">
                <item></item>
                <item>          </item>
            </string-array>
        </resources>
    ''')
    assert len(catalog) == 0
    assert 'empty' in logs[0]
    assert 'empty' in logs[1]


class TestComments:
    """Test the processing of comments in xml files.
    """

    def test_string(self):
        catalog = xmlstr2po(
        '''<resources>
              <!-- Comment 1 -->
              <!-- Comment 2 -->
              <string name="string1">value1</string>
              <string name="string2">value2</string>
           </resources>''')
        # TODO: Should those be stripped? Otherwise formatted (linebreaks etc)?
        assert catalog.get('value1', context='string1').auto_comments == [' Comment 1 ', ' Comment 2 ']
        assert catalog.get('value2', context='string2').auto_comments == []

    def test_string_array(self):
        catalog = xmlstr2po(
        '''<resources>
              <!-- Comment 1 -->
              <!-- Comment 2 -->
              <string-array name="array">
                  <item>item1</item>
                  <!-- this will be ignored -->
                  <item>item2</item>
              </string-array>
              <string name="string">value</string>
           </resources>''')
        assert catalog.get('item1', context='array:0').auto_comments == [' Comment 1 ', ' Comment 2 ']
        assert catalog.get('item2', context='array:1').auto_comments == [' Comment 1 ', ' Comment 2 ']
        assert catalog.get('value', context='string').auto_comments == []

    def test_translatable(self):
        """[bug] Make sure translatable=false and comments play nice together.
        """
        catalog = xmlstr2po(
        '''<resources>
              <!-- Comment 1 -->
              <!-- Comment 2 -->
              <string name="string1" translatable="false">value1</string>
              <string name="string2">value2</string>
           </resources>''')
        # The comments of string1 do not end up with string2.
        assert catalog.get('value2', context='string2').auto_comments == []

    def test_nameless(self):
        """This is an edge-case, but we don't (can't) process strings
        without a name. Comments are not passed along there either.
        """
        catalog = xmlstr2po(
        '''<resources>
              <!-- Comment 1 -->
              <!-- Comment 2 -->
              <string>value1</string>
              <string name="string2">value2</string>
           </resources>''')
        # The comments of string1 do not end up with string2.
        assert catalog.get('value2', context='string2').auto_comments == []
