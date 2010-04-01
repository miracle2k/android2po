from StringIO import StringIO
from lxml import etree
from babel.messages import Catalog
from nose.tools import assert_raises
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

    def mkcatalog(locale='de'):
        """Helper that returns a gettext catalog with one message
        already added.

        Tests can add a broken message and then ensure that at least
        the valid message still was processed.
        """
        c = Catalog(locale='de')
        c.add('valid_message', 'valid_value', context='valid_message')
        return c

    def runprogram(self, project, command, args={}):
        """Helper to run the given command in quiet mode. The warnings
        we test for here should appear even there.
        """
        args['--quiet'] = True
        return project.program(command, args)

    def test_nocontext(self):
        """Some strings in the .po file do not have a context set.
        """
        p = self.setup_project(languages=['de'])
        c = self.mkcatalog()
        c.add('s', 'v',)  # no context!
        p.write_po(c, 'de.po')
        assert 'no context' in self.runprogram(p, 'import')
        assert len(p.get_xml('de')) == 1

    def test_duplicate_aray_index(self):
        """An encoded array in the .po file has the same index twice.
        """
        p = self.setup_project(languages=['de'])
        c = self.mkcatalog()
        c.add('t1', 'v1', context='myarray:1')
        c.add('t2', 'v2', context='myarray:1')
        p.write_po(c, 'de.po')
        assert 'Duplicate index' in self.runprogram(p, 'import')
        xml = p.get_xml('de')
        assert len(xml) == 2
        assert len(xml['myarray']) == 1

    def test_invalid_xhtml(self):
        """XHTML in .po files may be invalid; a forgiving parser will be
        used as a fallback.
        """
        p = self.setup_project(languages=['de'])
        c = self.mkcatalog()
        c.add('s', 'I am <b>bold', context='s')
        p.write_po(c, 'de.po')
        assert 'invalid XHTML' in self.runprogram(p, 'import')
        assert p.get_xml('de')['s'] == 'I am <b>bold</b>'

    # XXX test_duplicate_context

    def test_duplicate_resource_string(self):
        """A resource XML file could contain a string twice.
        """
        p = self.setup_project()
        p.write_xml(data="""<resources><string name="s1">foo</string><string name="s1">bar</string></resources>""")
        assert 'Duplicate resource' in self.runprogram(p, 'init')
        assert len(p.get_po('template.pot')) == 1

    def test_empty_stringarray(self):
        """A warning is shown if a string array is empty.
        """
        p = self.setup_project()
        # TODO: Can use a dict after .convert refactoring
        p.write_xml(data="""<resources><string-array name="s1"></string-array></resources>""")
        assert 'is empty' in self.runprogram(p, 'init')
        assert len(p.get_po('template.pot')) == 0

    def test_type_mismatch(self):
        """A resource name is string-array in the reference file, but a
        normal string in the translation.
        """
        p = self.setup_project(languages=['de'])
        # TODO: Can use dicts after .convert refactoring
        p.write_xml(data="""<resources><string-array name="s1"><item>value</item></string-array></resources>""")
        p.write_xml(data="""<resources><string name="s1">value</string></resources>""", lang='de')
        assert 'string-array in the reference' in self.runprogram(p, 'init')
        assert len(p.get_po('template.pot')) == 1

    def test_invalid_resource_xml(self):
        """Resource xml files are so broken we can't parse them.
        """
        # Invalid language resource
        p = self.setup_project(languages=['de'])
        p.write_xml(data="""<resources><string name="s1"> ...""", lang='de')
        assert 'Failed parsing' in self.runprogram(p, 'init')
        assert_raises(IOError, p.get_po, 'de.po')

        # Invalid default resource
        p = self.setup_project()
        p.write_xml(data="""<resources><string name="s1"> ...""")
        assert 'Failed parsing' in self.runprogram(p, 'init')
        assert_raises(IOError, p.get_po, 'template.pot')