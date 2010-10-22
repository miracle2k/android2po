"""Various conversion-special cases.
"""

from __future__ import absolute_import

from StringIO import StringIO
from lxml import etree
from babel.messages import Catalog
from nose.tools import assert_raises
from android2po import xml2po, po2xml
from ..helpers import ProgramTest


def test_trailing_whitespace():
    # [bug] Make sure that whitespace after the <string> tag does not
    # end up as part of the value.
    catalog = xml2po(StringIO(
        '<resources><string name="foo">bar</string>    \t\t  </resources>'))
    assert list(catalog)[1].id == 'bar'


def test_translatable():
    """Strings marked as translatable=False will be skipped.
    """
    catalog = xml2po(StringIO(
        '<resources><string name="foo" translatable="false">bar</string></resources>'))
    assert len(catalog) == 0

    catalog = xml2po(StringIO(
        '<resources><string name="foo" translatable="true">bar</string></resources>'))
    assert list(catalog)[1].id == 'bar'

    catalog = xml2po(StringIO(
        '<resources><string-array name="foo" translatable="false"><item>bla</item></string-array></resources>'))
    assert len(catalog) == 0


def test_invalid_xhtml():
    """Ensure we can deal with broken XML in messages.
    """
    c = Catalog()
    c.add('Foo', '<i>Tag is not closed', context="foo")

    # [bug] This caused an exception in 16263b.
    dom = po2xml(c)

    # The tag was closed automatically (our loose parser tries to fix errors).
    assert etree.tostring(dom) == '<resources><string name="foo"><i>Tag is not closed</i></string></resources>'


class TestAndroidResourceReferences:
    """Dealing with things like @string/app_name is not quite
    as straightforward as one might think.

    Note that the low-level escaping is tested in test_text.py.
    """

    def make_raw(self, content):
        class Log():
            logs = []
            def __call__(self, msg, severity):
                self.logs.append(msg)
        logger = Log()
        return xml2po(StringIO(content), warnfunc=logger), logger.logs

    def make(self, name, value):
        return self.make_raw('<resources><string name="%s">%s</string></resources>' % (
            name, value))

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
