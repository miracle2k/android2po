"""TODO: Test basic environment handling (ensuring the correct config file
is used in the correct circumstances, the project directory is automatically
detected, the proper directories assumed etc).
"""

from tests.helpers import ProgramTest


class TestConfig(ProgramTest):

    def test_with_option(self):
        """Regression test: Make sure we can deal with config files that
        have values.
        """
        p = self.setup_project(config="")
        # This used to raise an AssertionError.
        p.program('init')