import os
from os import path


__all__ = ('Path', 'Writer',)


class Path(unicode):
    """Helper representing a filesystem path that can be "bound" to a base
    path. You can then ask it to render as a relative path to that base.
    """

    def __new__(self, *parts, **kwargs):
        base = kwargs.pop('base', None)
        if kwargs:
            raise TypeError()
        self.base = base
        abs = path.normpath(path.abspath(path.join(*parts)))
        return unicode.__new__(self, abs)

    @property
    def rel(self):
        base =  self.base or os.getcwd()
        if not hasattr(path, 'relpath'):
            # Python < 2.6 doesn't have relpath, and I don't want
            # to bother with a wbole bunch of code for this. See
            # if we can simply remove the prefix, and if not, 2.5
            # users will have to live with the absolute path.
            if self.path.startswith(base):
                return self.path[len(base)+1:]
            return self.abs
        return path.relpath(self, start=base)

    @property
    def abs(self):
        return self

    def exists(self):
        return path.exists(self)

    @property
    def dir(self):
        return Path(path.dirname(self), base=self.base)


class Writer():
    """Helps printing messages to the output, in a very particular form.

    Supported are two concepts, "actions" and "messages". A message is
    always the child of an action. There is a limited set of action
    types (we call them events). Each event and each message may have a
    "severity". The severity can determine how a message or event is
    rendered (if the terminals supports colors), and will also affect
    whether a action or message is rendered at all, depending on verbosity
    settings.

    If a message exceeds it's action in severity causing the message to
    be visible but the action not, the action will forcably be rendered as
    well. For this reason, the class keeps track of the last message that
    should have been printed.

    There is also a mechanism which allows to delay printing an action.
    That is, you may begin constructing an action and collecting it's
    messages, and only later print it out. You would want to do this if
    the event type can only be determined after the action is completed,
    since it often indicates the outcome.
    """

    DELAY = object()

    EVENTS = {
        'info': (), 'mkdir': (), 'updated': (), 'unchanged': (), 'skipped': (),
         'created': (), 'exists': (), 'error': (),}
    LEVELS = {
        'default': (), 'warning': (), 'error': (), 'info': (),}

    # +2 for [ and ]
    # +1 for additional left padding
    max_event_len = max([len(k) for k in EVENTS.keys()]) + 2 + 1

    class Action(dict):
        def __init__(self, writer, *more, **data):
            self.writer = writer
            self.messages = []
            self.is_done = False
            dict.__init__(self, {'severity': 'default'})
            self.update(*more, **data)

        def done(self, event, *more, **data):
            assert event in Writer.EVENTS
            self['event'] = event
            self.update(*more, **data)
            self.writer._print_action(self)
            self.is_done = True

        def update(self, text=None, severity=None, **more_data):
            if text:
                self['text'] = text
            if severity:
                self['severity'] = severity
            dict.update(self, **more_data)

        def message(self, message, severity='info'):
            if not self.is_done:
                self.messages.append(message)
            else:
                self.writer._print_message(message)

        @property
        def event(self):
            return self['event']

    def __init__(self):
        self._current_action = None

    def action(self, event, *a, **kw):
        action = Writer.Action(self, *a, **kw)
        action.done(event)
        return action

    def begin(self, *a, **kw):
        return Writer.Action(self, *a, **kw)

    def message(self, *a, **kw):
        self._current_action.message(*a, **kw)

    def _print_action(self, action):
        """Print the action and all it's attached messages.
        """
        self._print_action_header(action)
        for m in action.messages:
            self._print_message(m)
        self._current_action = action

    def _print_action_header(self, action):
        text = action['text']
        if isinstance(text, Path):
            # Handle Path instances manually. This doesn't happen
            # automatically because we haven't figur out how to make
            # that class represent itself through the relative path
            # by default, while still returning the full path if it
            # is used, say, during an open() operation.
            text = text.rel
        print ("%"+str(self.max_event_len)+"s %s") % (
            "[%s]" % action['event'], text)

    def _print_message(self, message):
        print " "*(self.max_event_len+1) + u"- %s" % message

