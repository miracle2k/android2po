from __future__ import absolute_import

import os
import re
from argparse import Namespace
from os import path
from .config import Config
from .utils import Path


__all__ = ('EnvironmentError', 'IncompleteEnvironment',
           'Environment', 'Language',)


class EnvironmentError(Exception):
    pass


class IncompleteEnvironment(EnvironmentError):
    pass


class Language(object):
    """Represents a single language.
    """

    def __init__(self, code, env):
        self.code = code
        self.env = env

    def xml(self, kind):
        # Android uses a special language code format for the region part
        parts = tuple(self.code.split('_', 2))
        if len(parts) == 2:
            android_code = "%s-r%s" % parts
        else:
            android_code = "%s" % parts
        return self.env.path(self.env.resource_dir,
                             'values-%s/%s.xml' % (android_code, kind))

    def po(self, kind):
        filename = self.env.config.layout % {
            'group': kind,
            'domain': self.env.config.domain or 'android',
            'locale': self.code}
        return self.env.path(self.env.gettext_dir, filename)

    def __unicode__(self):
        return unicode(self.code)


class DefaultLanguage(Language):
    """A special version of ``Language``, representing the default
    language.

    For the Android side, this means the XML files in the values/
    directory. For the gettext side, it means the .pot file(s).
    """

    def __init__(self, env):
        super(DefaultLanguage, self).__init__('<def>', env)

    def xml(self, kind):
        return self.env.path(self.env.resource_dir, 'values/%s.xml' % kind)

    def po(self, kind):
        template_name = self.env.config.template_name
        multiple_kinds = len(self.env.xmlfiles) > 1

        # If the template name configured by the user supports a variable,
        # then always insert the kind in it's place.
        if '%s' in template_name:
            filename = template_name % kind
        else:
            # Otherwise, if there are multiple kinds, use the current
            # kind as a prefix to differentiate (i.e. arrays-template.pot).
            if multiple_kinds:
                filename = "%s-%s" % (kind, template_name)
            else:
                # Otherwise, we're fine with just the template name alone.
                filename = template_name
        return self.env.path(self.env.gettext_dir, filename)


def find_project_dir_and_config():
    """Goes upwards through the directory hierarchy and tries to find
    either an Android project directory, a config file for ours, or both.

    The latter case (both) can only happen if the config file is in the
    root of the Android directory, because once we have either, we stop
    searching.

    Note that the two are distinct, in that if a config file is found,
    it's directory is not considered a "project directory" from which
    default paths can be derived.

    Returns a 2-tuple (project_dir, config_file).
    """
    cur = os.getcwdu()

    while True:
        project_dir = config_file = None

        manifest_path = path.join(cur, 'AndroidManifest.xml')
        if path.exists(manifest_path) and path.isfile(manifest_path):
            project_dir = cur

        config_path = path.join(cur, '.android2po')
        if path.exists(config_path) and path.isfile(config_path):
            config_file = config_path

        # Stop once we found either.
        if project_dir or config_file:
            return project_dir, config_file

        # Stop once we're at the root of the filesystem.
        old = cur
        cur = path.normpath(path.join(cur, path.pardir))
        if cur == old:
            # No further change, we are probably at root level.
            # TODO: Is there a better way? Is path.ismount suitable?
            # Or we could split the path into pieces by path.sep.
            break

    return None, None


LANG_DIR = re.compile(r'^values(?:-(\w\w)(?:-r(\w\w))?)?$')

def collect_languages(resource_dir):
    """Returns a 2-tuple with (files, languages).

    ``files`` is a list of the different xml files in the main values/
    directory (strings.xml, arrays.xml),  ``languages`` a list of language
    codes.
    """
    languages = []
    files = []
    for name in os.listdir(resource_dir):
        match = LANG_DIR.match(name)
        if not match:
            continue
        filepath = path.join(resource_dir, name)
        country, region = match.groups()
        if country == None:
            # Processing the default values/ directory
            for filename in ('strings.xml', 'arrays.xml'):
                file = path.join(filepath, filename)
                if path.isfile(file):
                    files.append(path.splitext(filename)[0])
        else:
            code = "%s" % country
            if region:
                code += "_%s" % region
            languages.append(code)

    return files, languages


class Environment(object):
    """Environment is the main object that holds all the data with
    which we run.

    Usage:

        env = Environment()
        env.pop_from_config(config)
        env.init()
    """

    def __init__(self):
        self.languages = []
        self.xmlfiles = []
        self.default = DefaultLanguage(self)
        self.config = Config()
        self.auto_gettext_dir = None
        self.auto_resource_dir = None
        self.resource_dir = None
        self.gettext_dir = None

        # Try to determine if we are inside a project; if so, we a) might
        # find a configuration file, and b) can potentially assume some
        # default directory names.
        self.project_dir, self.config_file = find_project_dir_and_config()

    def _pull_into(self, namespace, target):
        """If for a value ``namespace`` there exists a corresponding
        attribute on ``target``, then update that attribute with the
        values from ``namespace``, and then remove the value from
        ``namespace``.

        This is needed because certain options, if passed on the command
        line, need nevertheless to be stored in the ``self.config``
        object. We therefore **pull** those values in, and return the
        rest of the options.
        """
        for name in dir(namespace):
            if name.startswith('_'):
                continue
            if name in target.__dict__:
                setattr(target, name, getattr(namespace, name))
                delattr(namespace, name)
        return namespace

    def _pull_into_self(self, namespace):
        """This is essentially like ``self._pull_info``, but we pull
        values into the environment object itself, and in order to avoid
        conflicts between option values and attributes on the environment
        (for example ``config``), we explicitly specify the values we're
        interested in: It's the "big" ones which we would like to make
        available on the environment object directly.
        """
        for name in ('resource_dir', 'gettext_dir'):
            if hasattr(namespace, name):
                setattr(self, name, getattr(namespace, name))
                delattr(namespace, name)
        return namespace

    def pop_from_options(self, argparse_namespace):
        """Apply the set of options given on the command line.

        These means that we need those options that are "configuration"
        values to end up in ``self.config``. The normal options will
        be made available as ``self.options``.
        """
        rest = self._pull_into_self(argparse_namespace)
        rest = self._pull_into(rest, self.config)
        self.options = rest

    def pop_from_config(self, argparse_namespace):
        """Load the values we support into our attributes, remove them
        from the ``config`` namespace, and store whatever is left in
        ``self.config``.
        """
        rest = self._pull_into_self(argparse_namespace)
        rest = self._pull_into(rest, self.config)
        # At this point, there shouldn't be anything left, because
        # nothing should be included in the argparse result that we
        # don't consider a configuration option.
        ns = Namespace()
        assert rest == ns

    def auto_paths(self):
        """Try to auto-fill some path values that don't have values yet.
        """
        if self.project_dir:
            if not self.resource_dir:
                self.resource_dir = path.join(self.project_dir, 'res')
                self.auto_resource_dir = True
            if not self.gettext_dir:
                self.gettext_dir = path.join(self.project_dir, 'locale')
                self.auto_gettext_dir = True

    def path(self, *pargs):
        """Helper that constructs a Path object using the project dir
        as the base."""
        return Path(*pargs, base=self.project_dir)

    def init(self):
        """Initialize the environment.

        This entails loading the list of languages, and in the process
        doing some basic validation. An ``EnvironmentError`` is thrown
        if there is something wrong.
        """
        # If either of those is not specified, we can't continue. Raise a
        # special exception that let's the caller display the proper steps
        # on how to proceed.
        if not self.resource_dir or not self.gettext_dir:
            raise IncompleteEnvironment()

        # It's not enough for directories to be specified; they really
        # should exist as well. In particular, the locale/ directory is
        # not part of the standard Android tree and thus likely to not
        # exist yet, so we create it automatically, but ONLY if it wasn't
        # specified explicitely. If the user gave a specific location,
        # it seems right to let him deal with it fully.
        if not path.exists(self.gettext_dir) and self.auto_gettext_dir:
            os.makedirs(self.gettext_dir)
        elif not path.exists(self.gettext_dir):
            raise EnvironmentError('Gettext directory at "%s" doesn\'t exist.' %
                                   self.gettext_dir)
        elif not path.exists(self.resource_dir):
            raise EnvironmentError('Android resource direcory at "%s" doesn\'t exist.' %
                                   self.resource_dir)

        # Create an environment object based on all the data we have now.
        files, languages = collect_languages(self.resource_dir)
        if not files:
            raise EnvironmentError('default language was not found.')

        self.xmlfiles = files
        for code in languages:
            self.languages.append(Language(code, self))

        # If regular expressions are used as ignore filters, precompile
        # those to help speed things along. For simplicity, we also
        # convert all static ignores to regexes.
        compiled_list = []
        for ignore_list in self.config.ignores:
            for ignore in ignore_list:
                if ignore.startswith('/') and ignore.endswith('/'):
                    compiled_list.append(re.compile(ignore[1:-1]))
                else:
                    compiled_list.append(re.compile("^%s$" % re.escape(ignore)))
        self.config.ignores = compiled_list

        # Validate the layout option, and resolve magic constants ("gnu")
        # to an actual format string.
        layout = self.config.layout
        multiple_pos = len(self.xmlfiles) > 1
        if not layout or layout == 'default':
            if self.config.domain and multiple_pos:
                layout = '%(domain)s-%(group)s-%(locale)s.po'
            elif self.config.domain:
                layout = '%(domain)s-%(locale)s.po'
            elif multiple_pos:
                layout = '%(group)s-%(locale)s.po'
            else:
                layout = '%(locale)s.po'
        elif layout == 'gnu':
            if multiple_pos:
                layout = '%(locale)s/LC_MESSAGES/%(group)s-%(domain)s.po'
            else:
                layout = '%(locale)s/LC_MESSAGES/%(domain)s.po'
        else:
            if not '%(locale)s' in layout:
                raise EnvironmentError('locale missing')
            if self.config.domain and not '%(domain)s' in layout:
                raise EnvironmentError('domain missing')
            if multiple_pos and not '%(group)s' in layout:
                raise EnvironmentError('group missing')
        self.config.layout = layout
