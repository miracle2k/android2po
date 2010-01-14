from __future__ import absolute_import


__all__ = ('Environment',)


class Environment(object):

    def __init__(self):
        self.languages = None
        self.default_file = None
        self.options = None
        self.config = None