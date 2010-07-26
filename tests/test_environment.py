"""TODO: Test basic environment handling (ensuring the correct config file
is used in the correct circumstances, the project directory is automatically
detected, the proper directories assumed etc).
"""

from tests.helpers import ProgramTest, NonZeroReturned
from nose.tools import assert_raises


class TestCollect(ProgramTest):
    """Make sure we support any XML resource file, including non-standard
    names besides strings.xml, arrays.xml etc.
    """

    def test(self):
        p = self.setup_project(default_xml=False)
        p.write_xml(kind='strings')
        p.write_xml(kind='arrays')
        p.write_xml(kind='file-with-strings', data={'foo': 'bar'})
        p.write_xml(kind='empty-file')
        p.write_xml(kind='file-with-other-stuff',
                    data="""<resources><color name="white">#ffffffff</color></resources>""")
        p.program('init')

        # It's important that we only load files which actually contain
        # translatable strings, and ignore files which only have other
        # resources.
        p.get_po('file-with-strings.pot')
        assert_raises(IOError, p.get_po, 'empty-file.pot')
        assert_raises(IOError, p.get_po, 'file-with-other-stuff.pot')
        # Those are special, and will always be included.
        p.get_po('strings.pot')
        p.get_po('arrays.pot')

    def test_error(self):
        """If any of the default XML files has an error.
        """
        p = self.setup_project(default_xml=False)
        p.write_xml(kind='broken-file',  data="""not really xml""")
        assert_raises(NonZeroReturned, p.program, 'init')


class TestConfig(ProgramTest):

    def test_with_option(self):
        """Regression test: Make sure we can deal with config files that
        have values.
        """
        p = self.setup_project(config="")
        # This used to raise an AssertionError.
        p.program('init')