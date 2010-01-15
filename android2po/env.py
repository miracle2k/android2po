from __future__ import absolute_import

from os import path


__all__ = ('Environment', 'Language',)


class Language(object):
    """Represents a single language.
    """

    def __init__(self, code, env):
        self.code = code
        self.env = env

    @property
    def xml_path(self):
        # Android uses a special language code format for the region part
        parts = tuple(self.code.split('_', 2))
        if len(parts) == 2:
            android_code = "%s-r%s" % parts
        else:
            android_code = "%s" % parts
        return path.join(self.env.config.resource_dir,
                         'values-%s/strings.xml' % android_code)

    @property
    def po_path(self):
        return path.join(self.env.config.gettext_dir, '%s.po' % self.code)

    def has_xml(self):
        return path.exists(self.xml_path)

    def has_po(self):
        return path.exists(self.po_path)


class Environment(object):

    def __init__(self):
        self.languages = []
        self.default_file = None
        self.options = None
        self.config = None
