"""Android supports string-arrays. Make sure we can handle them properly.
"""

from android2po import xml2po, po2xml
from StringIO import StringIO
from lxml import etree
from babel.messages.catalog import Catalog


def test_read_template():
    """Test basic read.
    """
    catalog = xml2po(StringIO('''
        <resources>
            <string-array name="colors">
                <item>red</item>
                <item>green</item>
            </string-array>
        </resources>
    '''))
    assert len(list(catalog)) == 3
    assert [m.context for m in catalog if m.id] == ['colors:0', 'colors:1']


def test_read_order():
    """Test that a strings of a string-array have the same position
    in the final catalog as the string-array had in the xml file, e.g.
    order is maintained for the string-array.
    """
    catalog = xml2po(StringIO('''
        <resources>
            <string name="before">foo</string>
            <string-array name="colors">
                <item>red</item>
                <item>green</item>
            </string-array>
            <string name="after">bar</string>
        </resources>
    '''))
    assert len(list(catalog)) == 5
    assert [m.context for m in catalog if m.id] == [
                'before', 'colors:0', 'colors:1', 'after']


def test_read_language():
    """Test that when reading a translated xml file, the translations
    of a string array are properly matched up with to strings in the
    untranslated template.
    """
    catalog, _ = xml2po(StringIO('''
        <resources>
            <string-array name="colors">
                <item>red</item>
                <item>green</item>
            </string-array>
        </resources>
    '''), StringIO('''
        <resources>
            <string-array name="colors">
                <item>rot</item>
                <item>gruen</item>
            </string-array>
        </resources>
    '''))

    assert len(list(catalog)) == 3
    assert [m.context for m in catalog if m.id] == ['colors:0', 'colors:1']
    assert [m.id for m in catalog if m.id] == ['red', 'green']
    assert [m.string for m in catalog if m.id] == ['rot', 'gruen']


def test_write():
    """Test writing a basic catalog.
    """
    catalog = Catalog()
    catalog.add('green', context='colors:0')
    catalog.add('red', context='colors:1')
    assert etree.tostring(po2xml(catalog, with_untranslated=True)) == \
        '<resources><string-array name="colors"><item>green</item><item>red</item></string-array></resources>'


def test_write_order():
    """Test that when writing a catalog with string-arrays, order is
    maintained; both of the string-array tag in the list of all strings,
    as well as the array strings themselves.
    """
    catalog = Catalog()
    catalog.add('foo', context='before')
    catalog.add('red', context='colors:1')
    catalog.add('green', context='colors:0')
    catalog.add('bar', context='after')
    assert etree.tostring(po2xml(catalog, with_untranslated=True)) == \
        '<resources><string name="before">foo</string><string-array name="colors"><item>green</item><item>red</item></string-array><string name="after">bar</string></resources>'

def test_write_skipped_ids():
    """Test that catalogs were ids are missing are written properly out
    as well.
    """
    # TODO: We currently simply maintain order, but shouldn't we instead
    # write out missing ids as empty strings? If the source file says
    # colors:9, that likely means the dev. expects 8 strings before it.
    catalog = Catalog()
    catalog.add('red', context='colors:9')
    catalog.add('green', context='colors:4')
    assert etree.tostring(po2xml(catalog, with_untranslated=True)) == \
        '<resources><string-array name="colors"><item>green</item><item>red</item></string-array></resources>'