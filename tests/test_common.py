from StringIO import StringIO
from lxml import etree
from babel.messages import catalog
from android2po import xml2po, po2xml


def test_common():
    # [bug] Make sure that whitespace after the <string> tag does not
    # end up as part of the value.
    catalog = xml2po(StringIO(
        '<resources><string name="foo">bar</string>    \t\t  </resources>'))
    assert list(catalog)[1].id == 'bar'
    
    
def test_invalid_xhtml():
    """Ensure we can deal with broken XML in messages.
    """
    c = catalog.Catalog()
    c.add('Foo', '<i>Tag is not closed', context="foo")
    
    # [bug] This caused an exception in 16263b.
    dom = po2xml(c)
    
    # The tag was closed automatically (our loose parser tries to fix errors).
    assert etree.tostring(dom) == '<resources><string name="foo"><i>Tag is not closed</i></string></resources>'