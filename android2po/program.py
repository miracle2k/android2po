"""Implements the command line interface.
"""

from __future__ import absolute_import

import sys
from os import path
import argparse

from .commands import *
from .env import IncompleteEnvironment, EnvironmentError, Environment, Language


__all__ = ('main', 'run',)


COMMANDS = {
    'init': InitCommand,
    'export': ExportCommand,
    'import': ImportCommand,
}


class Config:
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
         'kwargs': {'metavar': 'DIR',}
        },
        {'name': 'gettext',
         'help': 'directory containing the .po files ($PROJECT/locale by default)',
         'dest': 'gettext_dir',
         'kwargs': {'metavar': 'DIR',}
        },
    )

    @classmethod
    def setup_arguments(cls, parser):
        """Setup our configuration values as arguments in the ``argparse``
        object in ``parser``.
        """
        for optdef in cls.OPTIONS:
            names = ('--%s' % optdef.get('name'),)
            kwargs = {
                'help': optdef.get('help', None),
                'dest': optdef.get('dest', None),
                # We handle defaults ourselves. This
                # is actually important, or defaults
                # from one config source may override
                # valid values from another.
                'default': argparse.SUPPRESS,
            }
            kwargs.update(optdef.get('kwargs', {}))
            parser.add_argument(*names, **kwargs)

    @classmethod
    def rebase_paths(cls, config, base_path):
        """Make those config values that are paths relative to
        ``base_path``, because by default, paths are relative to
        the current working directory.
        """
        for name in ('gettext_dir', 'resource_dir'):
            value = getattr(config, name, None)
            if value is not None:
                setattr(config, name, path.join(base_path, value))


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


def read_config(filename):
    """Read the config file in ``filename``.

    The config file currently is simply a file with command line options,
    each option on a separate line.
    """

    # Open the config file and read the arguments.
    f = open(filename, 'rb')
    try:
        lines = f.readlines()
    finally:
        f.close()
    args = map(str.strip, " ".join(lines).split(" "))

    # Use a parser that specifically only supports those options that
    # we want to support within a config file (as opposed to all the
    # options available through the command line interface).
    parser = argparse.ArgumentParser(add_help=False)
    Config.setup_arguments(parser)
    config, unprocessed = parser.parse_known_args(args)
    if unprocessed:
        raise CommandError("unsupported config values: %s" % ' '.join(unprocessed))

    # Post process the config: Paths in the config file should be relative
    # to the config location, not the current working directory.
    Config.rebase_paths(config, path.dirname(filename))

    return config


def make_env(argv):
    """Given the command line arguments in ``argv``, construct an
    environment.

    This entails everything from parsing the command line, parsing
    a config file, if there is one, merging the two etc.

    Returns a ``Environment`` instance.
    """

    env = Environment()

    # Parse the command line arguments first. This is helpful in
    # that any potential syntax errors there will cause us to
    # fail before doing anything else.
    options = parse_args(argv)

    # Try to load a config file, either if given at the command line,
    # or the one that was automatically found. Note that even if a
    # config file is used, using the default paths is still supported.
    # That is, you can provide some extra configuration values
    # through a file, potentially shared across multiple projects, and
    # still rely on simply calling the script inside a default
    # project's directory hierarchy.
    config_file = None
    if options.config:
        config_file = options.config
        env.config_file = config_file
    elif env.config_file:
        config_file = env.config_file
        if options.verbose:
            print "Using auto-detected config file: %s"  % config_file
    if config_file:
        env.pop_from_config(read_config(config_file))

    # Now that we have applied the config file, also apply the command
    # line options. Those will thus override the config values.
    env.pop_from_options(options)

    # Some paths, if we still don't have values for them, can be deducted
    # from the project directory.
    env.auto_paths()
    if env.options.verbose and env.auto_directories:
        # Let the user know we are deducting information from the
        # project that we found.
        print "Assuming default directory structure in '%s'" % project_dir

    # Initialize the environment. This mainly loads the list of
    # languages, but also does some basic validation.
    try:
        env.init()
    except IncompleteEnvironment:
        if not env.project_dir:
            if not env.config_file:
                raise CommandError('You need to run this from inside an '
                    'Android project directory, or specify the source and '
                    'target directories manually, either as command line '
                    'options, or through a configuration file')
            else:
                raise CommandError('Your configuration file does not specify '
                    'the source and target directory, and you are not running '
                    'the script from inside an Android project directory.')
    except EnvironmentError, e:
        raise CommandError(e)

    # We're done. Just print some info out for the user.
    if env.options.verbose:
        print "Using as Android resource dir: '%s'" % env.resource_dir
        print "Using as gettext dir: '%s'" % env.gettext_dir
    if not env.options.quiet:
        print "Found %d language(s): %s" % (len(env.languages),
                                            ", ".join(map(unicode, env.languages)))

    return env


def main(argv):
    """The program.

    Returns an error code or None.
    """
    try:
        # Build an environment from the list of arguments.
        env = make_env(argv)
        cmd = COMMANDS[env.options.command](env)
        return cmd.execute()
    except CommandError, e:
        print 'Error:', e
        return 1


def run():
    """Simplified interface to main().
    """
    sys.exit(main(sys.argv) or 0)