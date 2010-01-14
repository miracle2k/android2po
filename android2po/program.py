"""Implements the command line interface.
"""

from __future__ import absolute_import

import os, sys
from os import path
import re
import ConfigParser
import argparse

from .utils import AttrDict
from .commands import *


__all__ = ('main', 'run',)


COMMANDS = {
    'export': ExportCommand,
    'import': ImportCommand,
}


class Config(object):
    """Object that holds our program configuration.

    The configuration can be read from both command line options or
    a file; see the ``apply_*`` methods. Later calls will overwrite
    values from former calls. It's your responsibility to make the
    calls in the order in which you prefer.
    """

    # Defines all the values this config object supports, with the
    # necessary meta data to both read them from an ini file and
    # from command line arguments.
    #
    # Supported keys: name = name as both option and in config,
    # help = short help text, dest - local attribute to store the value,
    # default = default value, argparse_kwargs = additional arguments
    # for the command line option.
    OPTIONS = (
        {'name': 'android',
         'help': 'Android resource directory ($PROJECT/res by default)',
         'dest': 'resource_dir',
         'argparse_kwargs': {'metavar': 'DIR',}
        },
        {'name': 'gettext',
         'help': 'directory containing the .po files ($PROJECT/locale by default)',
         'dest': 'gettext_dir',
         'argparse_kwargs': {'metavar': 'DIR',}
        },
    )

    def __init__(self):
        self.reset()   # Initialize attributes

    def reset(self):
        for optdef in self.OPTIONS:
            name = optdef.get('dest', optdef.get('name'))
            setattr(self, name, optdef.get('default'))

    @classmethod
    def setup_arguments(cls, parser):
        """Setup the command line arguments with which one
        can override values in the config file.
        """
        for optdef in cls.OPTIONS:
            names = ('--%s' % optdef.get('name'),)
            kwargs = {
                'help': optdef.get('help', None),
                'default': argparse.SUPPRESS,  # We have set our defaults manually.
                'dest': optdef.get('dest', None),
            }
            kwargs.update(optdef.get('argparse_kwargs', {}))
            parser.add_argument(*names, **kwargs)

    def apply_file(self, filename):
        """Read the configuration from a file.
        """
        ini = ConfigParser.RawConfigParser()
        ini.read(filename)

        if not ini.has_section('core'):
            return
        ini_keys = ini.options('core')

        for optdef in self.OPTIONS:
            name = optdef.get('name')
            dest = optdef.get('dest', name)
            if name in ini_keys:
                setattr(self, dest, ini.get('core', name))

    def apply_options(self, options):
        """Apply from command line options.
        """
        # This is easy, we basically just have to copy the values.
        for optdef in self.OPTIONS:
            dest = optdef.get('dest', optdef.get('name'))
            if hasattr(options, dest):
                setattr(self, dest, getattr(options, dest))


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
    languages = {}
    default_file = None
    for name in os.listdir(resource_dir):
        filename = path.join(resource_dir, name, 'strings.xml')
        if not path.isfile(filename):
            continue
        match = LANG_DIR.match(name)
        if not match:
            continue
        country, region = match.groups()
        if country == None:
            default_file = filename
        else:
            code = "%s" % country
            if region:
                code += "_%s" % region
            languages[code] = filename

    return default_file, languages


def parse_args(argv):
    """Builds an argument parser based on all commands and configuration
    values that we support.
    """
    from . import get_version
    parser = argparse.ArgumentParser(add_help=True,
        description='Convert Android string resources to gettext .po '+
                    'files, an import them back.',
        epilog='Written by: Michael Elsdoerfer <michael@elsdoerfer.com>',
        version=get_version())

    # Create parser for arguments shared by all commands.
    base_parser = argparse.ArgumentParser(add_help=False)
    group = base_parser.add_mutually_exclusive_group()
    group.add_argument('--verbose', '-v', action='store_true',
                       help='be extra verbose')
    group.add_argument('--quiet', '-q', action='store_true',
                       help='be extra quiet')
    base_parser.add_argument('--config', '-c', metavar='FILE',
                        help='config file to use')
    # Add the arguments that set/override the configuration.
    group = base_parser.add_argument_group('configuration',
        'Those can also be specified in a configuration file. If given '
        'here, values from the configuration file will be overwritten.')
    Config.setup_arguments(group)

    # Add our commands with the base arguments + their own.
    subparsers = parser.add_subparsers(dest="command", title='commands',
                                       description='valid commands',
                                       help='additional help')
    for name, cmdclass in COMMANDS.items():
        cmd_parser = subparsers.add_parser(name, parents=[base_parser], add_help=True)
        group = cmd_parser.add_argument_group('command arguments')
        cmdclass.setup_arg_parser(group)

    return parser.parse_args(argv[1:])


def make_config(options):
    """Determine the runtime configuration based on the arguments passed
    in, the configuration file which was specified or auto-detected,
    and possibly certain default values based on the user's current
    working directory.
    """

    # Try to determine if we are inside a project; if so, we a) might
    # find a configuration file, and b) can potentially assume some
    # default directory names.
    project_dir, config_file = find_project_dir_and_config()

    # If an explicit configuration file was specified, that always
    # fully replaces any automatically found configuration file.
    # However, note that we are still be using the default paths
    # we can assume due to a project directory that we might have
    # found. That is, you can provide some extra configuration values
    # through a file, potentially shared across multiple projects, and
    # still rely on simply calling the script inside a default
    # project's directory hierarchy.
    if options.config:
        config_file = options.config
    elif config_file and options.verbose:
        print "Using auto-detected config file: %s"  % config_file

    # Start building the configuration based on both the file and
    # the values provided through the command line merged together.
    config = Config()
    if config_file:
        config.apply_file(config_file)
    config.apply_options(options)

    # Finally, if the input and output directories are not specified,
    # try to fall back to the project directory that we have found,
    # if we have found one.
    if not config.resource_dir or not config.gettext_dir:
        if not project_dir:
            if not config_file:
                raise CommandError('You need to run this from inside an '
                    'Android project directory, or specify the source and '
                    'target directories manually, either as command line '
                    'options, or through a configuration file')
            else:
                raise CommandError('Your configuration file does not specify '
                    'the source and target directory, and you are not running '
                    'the script from inside an Android project directory.')

        # Let the user know we are deducting information from the
        # project that we found.
        if options.verbose:
            print "Assuming default directory structure in '%s'" % project_dir

        if not config.resource_dir:
            config.resource_dir = path.join(project_dir, 'res')
        if not config.gettext_dir:
            config.gettext_dir = path.join(project_dir, 'locale')

    if options.verbose:
        print "Using as Android resource dir: '%s'" % config.resource_dir
        print "Using as gettext dir: '%s'" % config.gettext_dir

    return config


def prepare_env(config, options):
    """Build the 'environment', an object containing runtime data
    relevant to our general functioning, i.e. for most commands.
    """

    # Find all languages.
    default_file, languages = collect_languages(config.resource_dir)
    if not default_file:
            raise CommandError('default language was not found.')

    if not options.quiet:
        print "Found %d language(s): %s" % (len(languages), ", ".join(languages))

    # Setup an instance of the command class, then execute it.
    # TODO: Could be an object like Config(), meaning we don't need AttrDict.
    return AttrDict({
        'languages': languages,
        'default_file': default_file,
    })


def main(argv):
    """The program.

    Returns an error code or None
    """
    try:
        options = parse_args(argv)
        config = make_config(options)
        env = prepare_env(config, options)

        # Finally, run the command.
        cmd = COMMANDS[options.command](env, config, options)
        return cmd.execute()
    except CommandError, e:
        print 'Error:', e
        return 1


def run():
    """Simplified interface to main().
    """
    sys.exit(main(sys.argv) or 0)