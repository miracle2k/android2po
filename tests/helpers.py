import os, sys
from os.path import join
import tempfile
import shutil

from babel.messages import pofile
from android2po import program as a2po


__all__ = ('ProgramTest', 'TempProject',)


def mkfile(path, content=''):
    f = open(path, 'w')
    f.write(content)
    f.flush()
    f.close()


class TempProject(object):
    """Represents a dummy-Android project in a temporary directory that
    we can run our command line tool on.
    """

    def __init__(self, manifest=True, resource_dir='res', locale_dir='locale',
                 config=None, default_xml={}):
        self.dir = dir = tempfile.mkdtemp()
        self.locale_dir = self.p(locale_dir)
        self.resource_dir = self.p(resource_dir)

        if manifest:
            mkfile(self.p('AndroidManifest.xml'))
        if config is not None:
            self.write_config(config)

        os.mkdir(self.p(resource_dir))
        os.mkdir(self.p(resource_dir, 'values'))
        self.write_xml(default_xml)

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

    def write_xml(self, data, lang=None, kind='strings'):
        # Could use the more robust XML writing functions from
        # android2po.convert.
        content = '<resources>'
        for k, v in data.iteritems():
            content += '<string name="%s">%s</string>' % (k, v)
        content += '</resources>'

        dirname = 'values'
        if lang:
            dirname = "%s-%s" % (dirname, lang)
        mkfile(self.p(self.resource_dir, dirname, '%s.xml' % kind), content)

    def program(self, command=None, kwargs={}):
        """Run android2po in this project's working directory.
        """
        args = ['a2po-test']
        if command:
            args.append(command)
        for k, v in kwargs.iteritems():
            if v is True or not v:
                args.append(k)
            else:
                if not isinstance(v, (list, tuple)):
                    # A tuple may be used to pass the same argument multiple
                    # times with different values.
                    v = [v]
                for w in v:
                    args.append("%s=%s" % (k, w))

        # argparse likes to write to stderr, capture that output.
        old_cwd = os.getcwd()
        old_stderr = sys.stderr
        os.chdir(self.dir)
        sys.stderr = sys.stdout
        try:
            try:
                ret = a2po.main(args)
            except SystemExit, e:
                # argparse likes to raise this if arguments are invalid.
                raise RuntimeError('SystemExit raised by program: %s', e)
            else:
                if ret:
                    raise RuntimeError('Program returned non-zero: %d', ret)
        finally:
            os.chdir(old_cwd)
            sys.stderr = old_stderr

    def get_po(self, l):
        file = open(join(self.locale_dir, '%s' % l), 'rb')
        try:
            return pofile.read_po(file)
        finally:
            file.close()


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