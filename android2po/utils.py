__all__ = ('AttrDict',)


class AttrDict(dict):
    """Dict that allows attribute access.

    Based on:
        http://mail.python.org/pipermail/python-list/2009-October/1223601.html
    """
    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__ = self

    def copy(self):
        return AttrDict(self)

    def __repr__(self):
        return 'AttrDict(' + dict.__repr__(self) + ')'

    @classmethod
    def fromkeys(self, seq, value = None):
        return AttrDict(dict.fromkeys(seq, value))

    @classmethod
    def dictify(self, d):
        """Convert a nested structure of standard ``dict`` objects into
        a structure of ``AttrDict`` objects instead.
        """
        result = AttrDict(d)
        for k, v in result.items():
            if isinstance(v, dict):
                result[k] = AttrDict(v)
        return result
