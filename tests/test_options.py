"""Tests for each of the various configuration options.
"""

from nose.tools import assert_raises
from tests.helpers import ProgramTest, SystemExitCaught, NonZeroReturned
from babel.messages import Catalog


class TestNoTemplate(ProgramTest):
    """Template pot file can be disabled.
    """

    def test(self):
        # By default, a template file is created.
        p1 = self.setup_project()
        p1.program('export')
        p1.get_po('template.pot')

        # With the right option, we don't see one.
        p2 = self.setup_project()
        p2.program('export', {'--no-template': True})
        assert_raises(IOError, p2.get_po, 'template.pot')


class TestTemplateName(ProgramTest):

    def test(self):
        """The name of the template file can be configured.
        """
        p = self.setup_project()
        p.program('export', {'--template': 'foobar1234.pot'})
        p.get_po('foobar1234.pot')

    def test_with_var(self):
        """The name of the template file can contain a %s placeholder.
        If it does, it will be replaced by the name of the corresponding
        xml file, even if only a single kind of xml file is used.
        """
        p = self.setup_project()
        p.program('export', {'--template': 'foobar-%s-1234.pot'})
        p.get_po('foobar-strings-1234.pot')


class TestIgnores(ProgramTest):

    def test_init(self):
        """Test that ignores work during 'init'.
        """
        p = self.setup_project(default_xml={'app_name': 'Foo', 'nomatch': 'bar'})
        p.program('init', {'de': '', '--ignore': 'app_name'})
        po = p.get_po('de.po')
        assert po._messages.values()[0].id == 'bar'   # at least once bother to check the actual content
        assert len(p.get_po('template.pot')) == 1

    def test_export(self):
        """Test that ignores work during 'export'.
        """
        p = self.setup_project(default_xml={'app_name': 'Foo', 'nomatch': 'bar'})
        p.program('init', {'de': '', '--ignore': 'app_name'})
        assert len(p.get_po('de.po')) == 1
        assert len(p.get_po('template.pot')) == 1

    def test_regex(self):
        """Test support for regular expressions.
        """
        p = self.setup_project(default_xml={'pref_x': '123', 'nomatch': 'bar'})
        p.program('init', {'de': '', '--ignore': '/^pref_/'})
        assert len(p.get_po('de.po')) == 1

    def test_no_partials(self):
        """Test that non-regex ignores do not match partially.
        """
        p = self.setup_project(default_xml={'pref_x': '123', 'nomatch': 'bar'})
        p.program('init', {'de': '', '--ignore': 'pref'})
        assert len(p.get_po('de.po')) == 2

    def test_multiple(self):
        """Test that multiple ignores work fine.
        """
        p = self.setup_project(default_xml={'pref_x': '123', 'app_name': 'Foo'})
        p.program('init', {'de': '', '--ignore': ('app_name', '/pref/')})
        assert len(p.get_po('de.po')) == 0


class TestIgnoreFuzzy(ProgramTest):
    """Test the --ignore-fuzzy option.
    """

    def test(self):
        p = self.setup_project(languages=['de'])
        c = Catalog(locale='de')
        c.add('en1', 'de1', flags=('fuzzy',), context='foo')
        c.add('en2', 'de2', context='bar')
        p.write_po(c, 'de.po')
        p.program('import', {'--ignore-fuzzy': True})
        xml = p.get_xml('de')
        assert not 'foo' in xml
        assert 'bar' in xml


class TestIgnoreMinComplete(ProgramTest):
    """Test the --ignore-min-complete option.
    """

    def test(self):
        p = self.setup_project(languages=['de'])

        c = Catalog(locale='de')
        c.add('translated', 'value', context='translated')
        c.add('missing1', context='missing1')
        c.add('missing2', context='missing2')
        c.add('missing3', context='missing3')
        p.write_po(c, 'de.po')

        # At first, we require half the strings to be available.
        # This is clearly not the case in the catalog above.
        p.program('import', {'--require-min-complete': '0.5'})
        assert len(p.get_xml('de')) == 0

        # Now, only require 25% - this should just make the cut.
        p.program('import', {'--require-min-complete': '0.25'})
        assert len(p.get_xml('de')) == 1

    def test_fuzzy(self):
        """This option is affected by the --ignore-fuzzy flag. If
        it is set, fuzzy strings are not counted towards the total.
        """
        p = self.setup_project(languages=['de'])

        c = Catalog(locale='de')
        c.add('translated', 'value', context='translated')
        c.add('fuzzy', 'value', context='fuzzy', flags=('fuzzy',))
        p.write_po(c, 'de.po')

        # When fuzzy strings are counted, the catalog above is 100%
        # complete.
        p.program('import', {'--require-min-complete': '1'})
        assert len(p.get_xml('de')) == 2

        # If they aren't, it won't make the cut and the result should
        # be no strings at all being written.
        p.program('import', {'--require-min-complete': '1',
                             '--ignore-fuzzy': True})
        assert len(p.get_xml('de')) == 0

    def test_multiple_pos(self):
        """If the language writes to multiple .po files, those are
        all counted together. Either all of them will be written,
        or none of them will be.
        """
        p = self.setup_project(languages=['de'])
        p.write_xml(kind='strings')
        p.write_xml(kind='arrays')

        # Create two catalogs, one fully translated, the other one not
        # at all.
        c = Catalog(locale='de')
        c.add('translated', 'value', context='translated')
        p.write_po(c, 'strings-de.po')

        c = Catalog(locale='de')
        c.add('untranslated', context='untranslated')
        p.write_po(c, 'arrays-de.po')

        # If we require 100% completness on import, both files will
        # be empty, even though one of them is fully translated. But
        # the second drags down the total of the group.
        p.program('import', {'--require-min-complete': '1'})
        assert len(p.get_xml('de', kind='strings')) == 0
        assert len(p.get_xml('de', kind='arrays')) == 0

    def test_clear(self):
        """Explicitely test that if we ignore a language, the xml
        file is overwritten with an empty version. Just not processing
        it is not enough.
        """
        p = self.setup_project()

        # We start out with one string in the XML
        p.write_xml({'string1': 'value1'}, lang='de')
        assert len(p.get_xml('de')) == 1

        c = Catalog(locale='de')
        c.add('string1', context='string1')
        p.write_po(c, 'de.po')

        # Now after the import, the resource file is empty.
        p.program('import', {'--require-min-complete': '1'})
        assert len(p.get_xml('de')) == 0

    def test_error(self):
        """Check that the argument is properly validated.
        """
        p = self.setup_project()
        assert_raises(SystemExitCaught, p.program, 'import', {'--require-min-complete': '3'})
        assert_raises(SystemExitCaught, p.program, 'import', {'--require-min-complete': 'asdf'})


class TestLayoutAndDomain(ProgramTest):
    """Test the --layout and --domain options.
    """

    def test_default_layout(self):
        """The default layout."""
        p = self.setup_project(languages=['de'])
        p.program('init')
        p.get_po('de.po')

    def test_default_with_groups(self):
        """The default while groups are being used.
        """
        p = self.setup_project(languages=['de'])
        p.write_xml({}, kind='arrays')
        p.program('init')
        p.get_po('arrays-de.po')

    def test_default_with_domain(self):
        """The default when a domain is given.
        """
        p = self.setup_project(languages=['de'])
        p.program('init', {'--domain': 'a2potest'})
        p.get_po('a2potest-de.po')

    def test_default_with_groups_and_domain(self):
        """The default with both groups being used and a domain given.
        """
        p = self.setup_project(languages=['de'])
        p.write_xml({}, kind='arrays')
        p.program('init', {'--domain': 'a2potest'})
        p.get_po('a2potest-arrays-de.po')

    def test_gnu(self):
        """Test --layout gnu.
        """
        p = self.setup_project(languages=['de'])
        p.program('init', {'--layout': 'gnu'})
        p.get_po('de/LC_MESSAGES/android.po')

    def test_gnu_with_groups(self):
        """Test --layout gnu.
        """
        p = self.setup_project(languages=['de'])
        p.write_xml({}, kind='arrays')
        p.program('init', {'--layout': 'gnu'})
        p.get_po('de/LC_MESSAGES/strings-android.po')

    def test_gnu_with_domain(self):
        """Test --layout gnu.
        """
        p = self.setup_project(languages=['de'])
        p.program('init', {'--layout': 'gnu', '--domain': 'a2potest'})
        p.get_po('de/LC_MESSAGES/a2potest.po')

    def test_gnu_with_groups_and_domain(self):
        """Test --layout gnu.
        """
        p = self.setup_project(languages=['de'])
        p.write_xml({}, kind='arrays')
        p.program('init', {'--layout': 'gnu', '--domain': 'a2potest'})
        p.get_po('de/LC_MESSAGES/strings-a2potest.po')

    def test_custom_requires_locale(self):
        """A custom --layout always requires a "locale" placeholder.
        """
        p = self.setup_project(languages=['de'])
        assert_raises(NonZeroReturned,
                      p.program, 'init', {'--layout': 'mylocation.po'})
        p.program('init', {'--layout': '%(locale)s.po'})

    def test_custom_requires_domain_var(self):
        """A custom --layout requires a "domain" placeholder if a custom
        domain is given.
        """
        p = self.setup_project(languages=['de'])
        assert_raises(NonZeroReturned,
                      p.program, 'init', {'--domain': 'a2potest',
                                          '--layout': '%(locale)s.po'})
        p.program('init', {'--domain': 'a2potest',
                           '--layout': '%(locale)s-%(domain)s.po'})

    def test_custom_requires_group_var(self):
        """A custom --layout requires a "group" placeholder if groups
        are being used.
        """
        p = self.setup_project(languages=['de'])
        p.write_xml({}, kind='arrays')
        assert_raises(NonZeroReturned,
                      p.program, 'init', {'--layout': '%(locale)s.po'})
        p.program('init', {'--layout': '%(locale)s-%(group)s.po'})
