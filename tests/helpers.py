import os, sys
from os.path import join, dirname, exists
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
import tempfile
import shutil
from lxml import etree

from babel.messages import pofile
from android2po import program as a2po
from android2po.convert import read_xml, write_xml


__all__ = ('ProgramTest', 'TempProject', 'TestWarnFunc',
           'SystemExitCaught', 'NonZeroReturned',)



class SystemExitCaught(Exception):
    pass


class NonZeroReturned(Exception):
    pass


def mkfile(path, content=''):
    f = open(path, 'w')
    f.write(content)
    f.flush()
    f.close()


class TestWarnFunc(object):
    """Object that can be passed to the ``warnfunc`` paramter of
    for example xml2po(), and collects the warnings so we
    can test whether they are in fact generated.
    """
    def __init__(self):
        self.logs = []
    def __call__(self, msg, severity):
        self.logs.append(msg)


class Tee(object):
    """Return a stdout-compatible object that will pipe data written
    into it to all of the file-objects in ``args``."""

    def __init__(self, *args):
        self.args = args

    def write(self, data):
        for f in self.args:
            f.write(data)


class TempProject(object):
    """Represents a dummy-Android project in a temporary directory that
    we can run our command line tool on.
    """

    def __init__(self, manifest=True, resource_dir='res', locale_dir='locale',
                 config=None, default_xml={}, xml_langs=[]):
        self.dir = dir = tempfile.mkdtemp()
        self.locale_dir = self.p(locale_dir)
        self.resource_dir = self.p(resource_dir)

        if manifest:
            mkfile(self.p('AndroidManifest.xml'))
        if config is not None:
            self.write_config(config)

        os.mkdir(self.locale_dir)
        os.mkdir(self.resource_dir)
        if default_xml not in (False, None):
            self.write_xml(default_xml)
        # Language-XML files that should be created by default
        for code in xml_langs:
            self.write_xml(lang=code)

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

    def write_xml(self, data={}, lang=None, kind='strings'):
        if isinstance(data, basestring):
            content = data
        else:
            content = etree.tostring(write_xml(data))

        folder = 'values'
        if lang:
            folder = "%s-%s" % (folder, lang)
        filename = self.p(self.resource_dir, folder, '%s.xml' % kind)
        if not exists(dirname(filename)):
            os.makedirs(dirname(filename))
        mkfile(filename, content)

    def write_po(self, catalog, filename=None):
        if not filename:
            filename = '%s.po' % catalog.locale
        file = open(join(self.locale_dir, '%s' % filename), 'wb')
        try:
            return pofile.write_po(file, catalog)
        finally:
            file.close()

    def program(self, command=None, kwargs={}, expect=None):
        """Run android2po in this project's working directory.

        Return the program output.
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
                    if isinstance(w, (list, tuple)):
                        # This is starting to get messy, but this allows the
                        # caller to generate "--arg val1 val2" by passing as
                        # the dict: {'arg': [['val1', 'val2']]}
                        args.append('%s' % k)
                        args.extend(w)
                    else:
                        # Otherwise, we set a single value, and we use "=",
                        # so that arguments that are defined as nargs='+'
                        # will not capture more than the value "w".
                        args.append("%s=%s" % (k, w))

        old_cwd = os.getcwd()
        os.chdir(self.dir)
        # Sometimes we might want to check a certain message was printed
        # out, so in addition to having nose capture the output, we
        # want to as well.
        old_stdout = sys.stdout
        stdout_capture = StringIO.StringIO()
        sys.stdout = Tee(sys.stdout, stdout_capture)
        # argparse likes to write to stderr, let it be handled like
        # normal stdout (i.e. captured by nose as well as us).
        old_stderr = sys.stderr
        sys.stderr = sys.stdout
        try:
            try:
                print "Running: %s" % " ".join(args)
                ret = a2po.main(args)
            except SystemExit, e:
                # argparse likes to raise this if arguments are invalid.
                raise SystemExitCaught('SystemExit raised by program: %s', e)
            else:
                if expect is not None:
                    if ret != expect:
                        raise ValueError(
                            'Program returned code %d, expected %d' % (
                                ret, expect))
                elif ret:
                    raise NonZeroReturned('Program returned non-zero: %d', ret)
                return stdout_capture.getvalue()
        finally:
            os.chdir(old_cwd)
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def get_po(self, filename):
        file = open(join(self.locale_dir, '%s' % filename), 'rb')
        try:
            return pofile.read_po(file)
        finally:
            file.close()

    def get_xml(self, lang=None, kind='strings', raw=False):
        dirname = 'values'
        if lang:
            dirname = "%s-%s" % (dirname, lang)
        filename = self.p(self.resource_dir, dirname, '%s.xml' % kind)
        if raw:
            return open(filename).read()
        else:
            return read_xml(filename)


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
