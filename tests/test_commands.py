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
from helpers import ProgramTest


class TestImport(ProgramTest):

    def test_missing_po(self):
        """Test that we an handle a missing .po file during import
        without crashing.
        """
        p = self.setup_project(languages=['de'])
        # Ensure that the corresponding .po file doesn't exist
        assert_raises(IOError, p.get_po, 'de.po')
        # Still, the program runs fine
        p.program('import')