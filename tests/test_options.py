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