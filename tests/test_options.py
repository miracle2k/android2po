"""Tests for each of the various configuration options.
"""

from nose.tools import assert_raises
from tests.helpers import ProgramTest


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