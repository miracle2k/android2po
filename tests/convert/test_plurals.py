"""Android supports plurals. Make sure we can handle them properly.
"""

from __future__ import unicode_literals

from StringIO import StringIO
from babel.messages.catalog import Catalog
from android2po import xml2po, po2xml, read_xml
from android2po.env import Language
from ..helpers import TestWarnFunc


def xmlstr2po(string):
    return xml2po(read_xml(StringIO(string)))


def test_read_master_xml():
    """Convert a master XML resource to a catalog, ensure that the
    plurals' msgid/msgid_plural values are correctly set.

    (what the export command does).
    """
    catalog = xmlstr2po('''
        <resources>
            <plurals name="foo">
                <item quantity="one">bar</item>
                <item quantity="other">bars</item>
            </plurals>
        </resources>
    ''')
    assert len(list(catalog)) == 2
    assert [m.context for m in catalog if m.id] == ['foo']
    assert [m.id for m in catalog if m.id] == [('bar', 'bars')]


def test_read_language_xml():
    """Convert a XML resource to a catalog, while matching strings
    up with translations from another resource.

    (what the init command does).
    """
    wfunc = TestWarnFunc()

    catalog, _ = xml2po(read_xml(StringIO('''
        <resources>
            <plurals name="foo">
                <item quantity="one">one</item>
                <item quantity="other">other</item>
            </plurals>
        </resources>
    ''')), read_xml(StringIO('''
        <resources>
            <plurals name="foo">
                <item quantity="one">ro one</item>
                <item quantity="few">ro few</item>
                <item quantity="many">ro many</item>
                <item quantity="other">ro other</item>
            </plurals>
        </resources>
    '''),
            language=Language('ro')), # Romanian
            warnfunc=wfunc)

    # A warning has been written for the unsupported quantity
    assert len(wfunc.logs) == 1
    assert 'uses quantity "many", which is not supported ' in wfunc.logs[0]

    assert [m.id for m in catalog if m.id] == [('one', 'other')]
    # Note: Romanian does not use the "many" string, so it is not included.
    assert [m.string for m in catalog if m.id] == [
        ('ro few', 'ro one', 'ro other')]

    # Make sure the catalog has the proper header
    assert catalog.num_plurals == 3
    print(catalog.plural_expr)
    assert catalog.plural_expr == '(((n == 0) || ((n != 1) && (((n % 100) >= 1 && (n % 100) <= 19)))) ? 1 : (n == 1) ? 0 : 2)'


def test_write():
    """Test a basic po2xml() call.

    (what the import command does).
    """
    catalog = Catalog()
    catalog.language = Language('bs') # Bosnian
    catalog.add(('foo', 'foos'), ('few', 'many', 'one', 'other'), context='foo')
    assert po2xml(catalog) == {'foo': {
        'few': 'few', 'many': 'many', 'one': 'one', 'other': 'other'}}


def test_write_incomplete_plural():
    """Test behaviour with incompletely translated plurals in .po."""
    catalog = Catalog()
    catalog.language = Language('bs') # Bosnian
    catalog.add(('foo', 'foos'), ('', 'many', 'one', ''), context='foo')
    print(po2xml(catalog))
    assert po2xml(catalog) == {'foo': {
        'few': '', 'many': 'many', 'one': 'one', 'other': ''}}


def test_write_incorrect_plural():
    """Test what happens when the .po catalog contains the wrong
    plural information.
    """
    catalog = Catalog()
    catalog.language = Language('lt') # Lithuanian
    # Lithuanian has three plurals, we define 2.
    catalog._num_plurals, catalog._plural_expr = 2, '(n != 1)'
    catalog.add(('foo', 'foos'), ('a', 'b',), context='foo')

    wfunc = TestWarnFunc()
    xml = po2xml(catalog, warnfunc=wfunc)

    # A warning was written
    assert len(wfunc.logs) == 1
    assert '2 plurals, we expect 3' in wfunc.logs[0]

    # The missing plural is empty
    assert xml == {'foo': {'few': 'a', 'other': None, 'one': 'b'}}


def test_write_ignore_untranslated_plural():
    """An untranslated plural is not included in the XML.
    """
    catalog = Catalog()
    catalog.language =  Language('en')
    catalog.add(('foo', 'foos'), context='foo')
    assert po2xml(catalog) == {}

    # Even with ``with_untranslated``, we still do not include
    # empty plural (they would just block access to the untranslated
    # master version, which we cannot copy into the target).
    assert po2xml(catalog) == {}

