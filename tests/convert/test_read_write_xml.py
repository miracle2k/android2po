"""Test converting from our internal ``ResourceTree`` structure to and from
actual XML.

The other tests validate only the ``ResourceTree`` created. Note that the
escaping details etc. are tested in test_text.py.
"""

from lxml import etree
from android2po.convert import write_xml, Plurals, StringArray


def c(dom):
    print etree.tostring(write_xml(dom))
    return etree.tostring(write_xml(dom))


class TestWriteXML(object):

    def test_string(self):
        assert c({'foo': 'bar'}) == \
            '<resources><string name="foo">bar</string></resources>'

    def test_plurals(self):
        assert c({'foo': Plurals({'one': 'bar', 'other': 'bars'})}) == \
            '<resources><plurals name="foo"><item quantity="one">bar</item><item quantity="other">bars</item></plurals></resources>'

    def test_arrays(self):
        assert c({'foo': StringArray(['bar1', 'bar2'])}) == \
            '<resources><string-array name="foo"><item>bar1</item><item>bar2</item></string-array></resources>'
