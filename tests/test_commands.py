"""TOOD: We need to test the basic command functionality, ensuring that
at it's core, import, export and init are operative, create the files they
should create, skip the files they should skip when they should be skipped,
etc. In particular, we should test both the case of multiple XML input files
(strings.xml, arrays.xml), and the case of only single source.

"test_options" tests the commands in combination with specific options and
will thus ensure that commands run, but does not check that they do the
right thing.
"""

from nose.tools import assert_raises
from babel.messages import Catalog
from android2po.convert import StringArray
from helpers import ProgramTest


class TestExport(ProgramTest):

    def test_export_with_empty_master_xml(self):
        """[Regression] Test that export works fine if the master
        resource is empty."""
        p = self.setup_project(xml_langs=['de'])
        p.write_xml(data="""<resources></resources>""", lang='de')
        p.write_po(Catalog('de'))
        assert not '[failed]' in p.program('export')


class TestImport(ProgramTest):

    pass


class TestPlurals(ProgramTest):
    """Test plural support on the program level.

    Low-level plural tests are in convert/
    """

    def test_init(self):
        """Test that the init command generates the proper plural form."""
        p = self.setup_project()
        p.write_xml(data="""<resources></resources>""")
        p.write_xml(data="""<resources></resources>""", lang='ja')
        p.program('init')
        catalog = p.get_po('ja.po')
        assert catalog.num_plurals == 1
        assert catalog.plural_expr == '(0)'

    def test_export(self):
        """Test that the export command maintains the proper plural form,
        and actually replaces an incorrect one."""
        p = self.setup_project()
        p.write_xml(data="""<resources></resources>""")
        p.write_xml(data="""<resources></resources>""", lang='ja')

        # Generate a catalog with different plural rules than we expect
        catalog = Catalog('ja')
        catalog._num_plurals, catalog._plural_expr = 2, '(n < 2)'
        p.write_po(catalog)

        # Export should override the info
        assert 'Plural-Forms header' in p.program('export')
        catalog = p.get_po('ja.po')
        assert catalog.num_plurals == 1
        assert catalog.plural_expr == '(0)'


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

    def runprogram(self, project, command, args={}, **kw):
        """Helper to run the given command in quiet mode. The warnings
        we test for here should appear even there.
        """
        args['--quiet'] = True
        return project.program(command, args, **kw)

    def test_nocontext(self):
        """Some strings in the .po file do not have a context set.
        """
        p = self.setup_project()
        c = self.mkcatalog()
        c.add('s', 'v',)  # no context!
        p.write_po(c, 'de.po')
        assert 'no context' in self.runprogram(p, 'import', expect=1)
        assert len(p.get_xml('de')) == 1

    def test_duplicate_aray_index(self):
        """An encoded array in the .po file has the same index twice.
        """
        p = self.setup_project()
        c = self.mkcatalog()
        c.add('t1', 'v1', context='myarray:1')
        c.add('t2', 'v2', context='myarray:1')
        p.write_po(c, 'de.po')
        assert 'Duplicate index' in self.runprogram(p, 'import', expect=1)
        xml = p.get_xml('de')
        assert len(xml) == 2
        assert len(xml['myarray']) == 1

    def test_invalid_xhtml(self):
        """XHTML in .po files may be invalid; a forgiving parser will be
        used as a fallback.
        """
        p = self.setup_project()
        c = self.mkcatalog()
        c.add('s', 'I am <b>bold', context='s')
        p.write_po(c, 'de.po')
        assert 'invalid XHTML' in self.runprogram(p, 'import')
        assert p.get_xml('de')['s'].text == 'I am <b>bold</b>'

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
        p.write_xml(data={'s1': StringArray([])})
        assert 'is empty' in self.runprogram(p, 'init')
        assert len(p.get_po('template.pot')) == 0

    def test_type_mismatch(self):
        """A resource name is string-array in the reference file, but a
        normal string in the translation.
        """
        p = self.setup_project(xml_langs=['de'])
        p.write_xml(data={'s1': StringArray(['value'])})
        p.write_xml(data={'s1': 'value'}, lang='de')
        assert 'string-array in the reference' in self.runprogram(p, 'init')
        assert len(p.get_po('template.pot')) == 1

    def test_invalid_resource_xml(self):
        """Resource xml files are so broken we can't parse them.
        """
        # Invalid language resource
        p = self.setup_project(xml_langs=['de'])
        p.write_xml(data="""<resources><string name="s1"> ...""", lang='de')
        assert 'Failed parsing' in self.runprogram(p, 'init', expect=1)
        assert_raises(IOError, p.get_po, 'de.po')

        # Invalid default resource
        p = self.setup_project()
        p.write_xml(data="""<resources><string name="s1"> ...""")
        assert 'Failed parsing' in self.runprogram(p, 'init', expect=1)
        assert_raises(IOError, p.get_po, 'template.pot')
