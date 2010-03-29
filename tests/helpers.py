import os, sys
from os.path import join
import tempfile
import shutil

from android2po import program as a2po


__all__ = ('ProgramTest', 'TempProject',)


def mkfile(path, content=''):
    f = open(path, 'w')
    if content == '<xml>':
        f.write('<resources></resources>')
    else:
        f.write(content)
    f.flush()
    f.close()


class TempProject(object):
    """Represents a dummy-Android project in a temporary directory that
    we can run our command line tool on.
    """

    def __init__(self, manifest=True, resource_dir='res', locale_dir='locale',
                 config=None):
        self.dir = dir = tempfile.mkdtemp()
        self.locale_dir = self.p(locale_dir)

        if manifest:
            mkfile(self.p('AndroidManifest.xml'))
        if config:
            self.write_config(config)

        os.mkdir(self.p(resource_dir))
        os.mkdir(self.p(resource_dir, 'values'))
        mkfile(self.p(resource_dir, 'values', 'strings.xml'), '<xml>')

    def __del__(self):
        self.delete()

    def delete(self):
        """Delete all the files of this temporary project.
        """
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)

    def p(self, *w):
        """Join a path relative to the project directory.
        """
        return join(self.dir, *w)

    def write_config(self, config):
        """Write a configuration file.
        """
        if isinstance(config, (list, tuple)):
            config = "\n".join(config)
        mkfile(self.p('.android2po'), config)

    def program(self, command=None, kwargs={}):
        """Run android2po in this project's working directory.
        """
        args = ['a2po-test']
        if command:
            args.append(command)
        for k, v in kwargs.iteritems():
            if v is True:
                args.append(k)
            else:
                args.append("%s=%s" % (k, v))

        old_cwd = os.getcwd()
        old_stderr = sys.stderr
        os.chdir(self.dir)
        sys.stderr = sys.stdout
        try:
            try:
                ret = a2po.main(args)
            except SystemExit, e:
                raise RuntimeError('SystemExit raised by program: %s', e)
            else:
                if ret:
                    raise RuntimeError('Program returned non-zero: %d', ret)
        finally:
            os.chdir(old_cwd)
            sys.stderr = old_stderr

    def get_po(self, l):
        f = open(join(self.locale_dir, '%s' % l), 'r')
        try:
            return f.readlines()
        finally:
            f.close()


class ProgramTest(object):
    """Base-class for tests that helps with setting up dummy projects
    and having android2po run on them.
    """

    def setup_project(self, *args, **kwargs):
        """Setup a fake Android project in a temporary directory
        that we can work with.
        """
        p = TempProject(*args, **kwargs)
        self.projects.append(p)
        return p

    def setup(self):
        # Start with a fresh list of projects for the test.
        self.projects = []

    def teardown(self):
        # Clear all projects that might have been created by the test.
        for p in self.projects:
            p.delete()