from __future__ import absolute_import

import os
import re
from os import path


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

    def xml_file(self, filename):
        # Android uses a special language code format for the region part
        parts = tuple(self.code.split('_', 2))
        if len(parts) == 2:
            android_code = "%s-r%s" % parts
        else:
            android_code = "%s" % parts
        return path.join(self.env.resource_dir,
                         'values-%s/%s' % (android_code, filename))

    def po_file(self, filename):
        return path.join(self.env.gettext_dir, filename % self.code)

    def has_xml(self, filename):
        return path.exists(self.xml_file(filename))

    def has_po(self, filename):
        return path.exists(self.po_file(filename))

    def __unicode__(self):
        return unicode(self.code)


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
    languages = []
    files = []
    for name in os.listdir(resource_dir):
        match = LANG_DIR.match(name)
        if not match:
            continue
        filepath = path.join(resource_dir, name)
        country, region = match.groups()
        if country == None:
            for filename in ('strings.xml', 'arrays.xml'):
                file = path.join(filepath, filename)
                if path.isfile(file):
                    files.append((file,
                                  filename,
                                  filename.split('.')[0]+"-%s.po",
                                  filename.split('.')[0]+".pot"),
                    )
        else:
            code = "%s" % country
            if region:
                code += "_%s" % region
            languages.append(code)

    # check how many files was found
    # if there is only strings.xml, the new filename only
    # consists of the language code because of the behavior
    # of the first versions of android2po
    if (len(files) == 1) and (files[0][1] == 'strings.xml'):
        files = [(files[0][0], files[0][1], "%s.po", "template.pot")]

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
        self.auto_gettext_dir = None
        self.auto_resource_dir = None
        self.resource_dir = None
        self.gettext_dir = None
        self.no_template = False

        # Try to determine if we are inside a project; if so, we a) might
        # find a configuration file, and b) can potentially assume some
        # default directory names.
        self.project_dir, self.config_file = find_project_dir_and_config()

    def _pop_from(self, namespace, store_as):
        for name in dir(namespace):
            if name.startswith('_'):
                continue
            if name in self.__dict__:
                # Attributes that already exist on our instance we would
                # like to store here directly, i.e. make available as
                # env.foo.
                # All others will be at, for example, env.options.foo.
                setattr(self, name, getattr(namespace, name))
                delattr(namespace, name)
        setattr(self, store_as, namespace)

    def pop_from_options(self, options):
        """Load the values we support into our attributes, remove them
        from the ``options`` namespace, and store whatever is left in
        ``self.options``.
        """
        self._pop_from(options, 'options')

    def pop_from_config(self, config):
        """Load the values we support into our attributes, remove them
        from the ``config`` namespace, and store whatever is left in
        ``self.config``.
        """
        self._pop_from(config, 'config')

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
        xmlfiles, languages = collect_languages(self.resource_dir)
        if not xmlfiles:
            raise EnvironmentError('default language was not found.')

        self.xmlfiles = xmlfiles
        for code in languages:
            self.languages.append(Language(code, self))
