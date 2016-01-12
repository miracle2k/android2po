# -*- coding: utf-8 -*-
"""Android supports plurals. Make sure we can handle them properly.
"""

from __future__ import unicode_literals

from io import StringIO, BytesIO

from babel.messages.catalog import Catalog
from android2po import xml2po, po2xml, read_xml
from android2po.env import Language
from babel.messages.mofile import write_mo
from babel.support import Translations
from ..helpers import TestWarnFunc


def xmlstr2po(string):
    return xml2po(read_xml(StringIO(string)))


def catalog_to_translations(catalog):
    """
    Helper function which converts catalog object to translation
    """
    buf = BytesIO()
    write_mo(buf, catalog, use_fuzzy=True)
    buf.seek(0)
    return Translations(fp=buf)


def test_xml_to_po_conversion_ru_pl():
    mapping = {
        'ru': {
            0: 'loc many',  # 0 яблок
            1: 'loc one',   # 1 яблоко
            2: 'loc few',   # 2 яблока
            5: 'loc many',  # 5 яблок
            21: 'loc one',  # 21 яблоко
        },
        'pl': {
            0: 'loc many',  # 0 jabłek
            1: 'loc one',   # 1 jabłko
            2: 'loc few',   # 2 jabłka
            22: 'loc few',  # 22 jabłka
            25: 'loc many',  # 25 jabłek
        }

    }
    for lang in ['ru', 'pl']:
        catalog, _ = xml2po(read_xml(StringIO('''
            <resources>
                <plurals name="plurals_test">
                    <item quantity="one">one</item>
                    <item quantity="other">other</item>
                </plurals>
            </resources>
        ''')), read_xml(StringIO('''
            <resources>
                <plurals name="plurals_test">
                    <item quantity="one">loc one</item>
                    <item quantity="few">loc few</item>
                    <item quantity="many">loc many</item>
                    <item quantity="other">loc other</item>
                </plurals>
            </resources>
        '''), language=Language(lang)), warnfunc=TestWarnFunc())

        # message
        msg = list(catalog)[1]
        assert msg.string == ('loc one', 'loc few', 'loc many', 'loc other')

        # translation works properly
        trans = catalog_to_translations(catalog)
        for num, form in mapping[lang].items():
            assert trans.unpgettext('plurals_test', 'one', 'other', num) == form


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
        ('ro one', 'ro few', 'ro other')]

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
    catalog.add(('foo', 'foos'), ('one', 'few', 'many', 'other'), context='foo')
    assert po2xml(catalog) == {'foo': {
        'few': 'few', 'many': 'many', 'one': 'one', 'other': 'other'}}


def test_write_incomplete_plural():
    """Test behaviour with incompletely translated plurals in .po."""
    catalog = Catalog()
    catalog.language = Language('bs') # Bosnian
    catalog.add(('foo', 'foos'), ('one', '', 'many', ''), context='foo')
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
    assert xml == {'foo': {'one': 'a', 'other': None, 'few': 'b'}}


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

