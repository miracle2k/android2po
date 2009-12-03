from android2po import xml2po
from StringIO import StringIO


def test_common():
    # [bug] Make sure that whitespace after the <string> tag does not
    # end up as part of the value.
    catalog = xml2po(StringIO(
        '<resources><string name="foo">bar</string>    \t\t  </resources>'))
    assert list(catalog)[1].id == 'bar'