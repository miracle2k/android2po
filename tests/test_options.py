"""Tests for each of the various configuration options.
"""

import os, sys
from os.path import join
import tempfile
import shutil

from nose.tools import assert_raises
from android2po import program as a2po


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

    def __init__(self, manifest=True, resource_dir='res', locale_dir='locale'):
        self.dir = dir = tempfile.mkdtemp()
        self.locale_dir = self.p(locale_dir)

        if manifest:
            mkfile(self.p('AndroidManifest.xml'))

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


class TestOptions:

    def setup_project(self):
        """Setup a fake Android project in a temporary directory
        that we can work with.
        """
        p = TempProject()
        self.projects.append(p)
        return p

    def setup(self):
        # Start with a fresh list of projects for the test.
        self.projects = []

    def teardown(self):
        # Clear all projects that might have been created by the test.
        for p in self.projects:
            p.delete()

    def test_no_template(self):
        """Template pot file can be disabled.
        """
        # By default, a template file is created.
        p1 = self.setup_project()
        p1.program('export')
        p1.get_po('template.pot')

        # With the right option, we don't see one.
        p2 = self.setup_project()
        p2.program('export', {'--no-template': True})
        assert_raises(IOError, p2.get_po, 'template.pot')

    def test_template_name(self):
        """The name of the template file can be configured.
        """
        p = self.setup_project()
        p.program('export', {'--template': 'foobar1234.pot'})
        p.get_po('foobar1234.pot')

    def test_template_name_with_var(self):
        """The name of the template file can contain a %s placeholder.
        If it does, it will be replaced by the name of the corresponding
        xml file, even if only a single kind of xml file is used.
        """
        p = self.setup_project()
        p.program('export', {'--template': 'foobar-%s-1234.pot'})
        p.get_po('foobar-strings-1234.pot')