from StringIO import StringIO
from lxml import etree
from babel.messages import Catalog
from android2po import xml2po, po2xml
from helpers import ProgramTest


def test_common():
    # [bug] Make sure that whitespace after the <string> tag does not
    # end up as part of the value.
    catalog = xml2po(StringIO(
        '<resources><string name="foo">bar</string>    \t\t  </resources>'))
    assert list(catalog)[1].id == 'bar'


def test_invalid_xhtml():
    """Ensure we can deal with broken XML in messages.
    """
    c = Catalog()
    c.add('Foo', '<i>Tag is not closed', context="foo")

    # [bug] This caused an exception in 16263b.
    dom = po2xml(c)

    # The tag was closed automatically (our loose parser tries to fix errors).
    assert etree.tostring(dom) == '<resources><string name="foo"><i>Tag is not closed</i></string></resources>'


class TestDealWithBrokenInput(ProgramTest):
    """Make sure we can handle broken input.
    """

    def test_nocontext(self):
        """Some strings in the .po file do not have a context set.
        """
        p = self.setup_project(languages=['de'])
        c = Catalog(locale='de')
        c.add('s', 'v',)  # no context!
        p.write_po(c, 'de.po')
        # We don't crash, and the xml will be empty
        p.program('import')
        assert len(p.get_xml('de')) == 0