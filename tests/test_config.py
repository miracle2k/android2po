"""Test reading and parsing the configuration file.
"""

from __future__ import unicode_literals

from io import StringIO
from nose.tools import assert_raises
from android2po.program import read_config, CommandError


def test_valid_args():
    c = read_config(StringIO('--gettext xyz\n--android foo'))
    assert c.gettext_dir == 'xyz'
    assert c.resource_dir == 'foo'


def test_invalid_args():
    assert_raises(CommandError, read_config, StringIO('--gettext xyz\n--verbose'))


def test_comments():
    c = read_config(StringIO('''
# This is a comment
--gettext xyz
   # This is a comment with whitespace upfront
'''))
    assert c.gettext_dir == 'xyz'


def test_whitespace():
    """Whitespace in front of lines or at the end is ignored.
    """
    c = read_config(StringIO('''   --gettext xyz  '''))
    assert c.gettext_dir == 'xyz'


def test_path_rebase():
    """Paths in the config file are made relative to their location.
    """
    # In Python 2.6, you can't set StringIO object's name attribute, so this
    # allows us to mock an opened file in 2.6+.
    class MockFile(StringIO):
        name = None
        def __init__(self, name, buffer_=None):
            super(MockFile, self).__init__(buffer_)
            self.name = name
    file = MockFile('/opt/proj/android/shared/.config', '''--gettext ../gettext\n--android ../res''')
    c = read_config(file)
    print(c.gettext_dir)
    assert c.gettext_dir == '/opt/proj/android/gettext'
    assert c.resource_dir == '/opt/proj/android/res'
