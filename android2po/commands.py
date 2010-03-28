from __future__ import absolute_import

import os
from os import path
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from lxml import etree
from babel.messages import pofile
from babel.core import UnknownLocaleError

from .convert import xml2po, po2xml, read_xml
from .env import Language


__all__ = ('CommandError', 'ExportCommand', 'ImportCommand', 'InitCommand',)


class CommandError(Exception):
    pass


def read_catalog(filename, **kwargs):
    """Helper to read a catalog from a .po file.
    """
    file = open(filename, 'rb')
    try:
        return pofile.read_po(file, **kwargs)
    finally:
        file.close()


def catalog2string(catalog, **kwargs):
    """Helper that returns a babel message catalog as a string.

    This is a simple shortcut around pofile.write_po().
    """
    sf = StringIO.StringIO()
    pofile.write_po(sf, catalog, **kwargs)
    return sf.getvalue()


def xml2string(xmldom):
    """Helper that returns the DOM of an XML as a string.

    TODO: It would be cool if this could try to recreate the formatting
    of the original xml file.
    """
    ENCODING = 'utf-8'
    return etree.tostring(xmldom, xml_declaration=True,
                          encoding=ENCODING, pretty_print=True)


def ensure_directories(cmd, dir):
    """Ensure that the given directory exists.
    """
    if not dir.exists():
        cmd.w.action('mkdir', dir)
        os.makedirs(dir)


def write_file(cmd, filename, content, update=True, action=None):
    """Helper that writes a file, while sending the proper actions
    to the command's writer for stdout display of what's going on.

    When ``update`` is not set, then if the file already exists we don't
    change or overwrite it.

    If a Writer.Action is given in ``action``, it will be used to print
    out messages. Otherwise, a new action will be started using the
    filename as the text.
    """
    if not action:
	action = cmd.w.begin(filename)

    if not update and filename.exists():
        cmd.w.action('exists', filename)
        return

    ensure_directories(cmd, filename.dir)

    f = open(filename, 'wb')
    try:
        f.write(content)
	f.flush()
    finally:
        f.close()

    action.done('updated')


class Command(object):
    """Abstract base command class.
    """

    def __init__(self, env, writer):
        self.env = env
        self.w = writer

    @classmethod
    def setup_arg_parser(cls, argparser):
        """A command should register it's sub-arguments here with the
        given argparser instance.
        """

    def execute(self):
        raise NotImplementedError()


class InitCommand(Command):
    """The init command; to initialize new languages.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        parser.add_argument('language', nargs='*',
            help='Language code to initialize. If none given, all '+
                 'languages lacking a .po file will be initialized.')

    def generate_templates(self, update=True):
	"""Generate the .pot templates. Returns the catalog objects as a
	kind -> catalog dict.

	TODO: Test that this happens during the "init" command as well.
	"""
	env = self.env
	default_catalogs = {}
        for kind in self.env.xmlfiles:
            template_pot = self.env.default.po(kind)
            if not env.config.no_template:
                action = self.w.begin(template_pot)
            default_catalog = xml2po(self.env.default.xml(kind))
	    default_catalogs[kind] = default_catalog
            if not env.config.no_template:
		if template_pot.exists() and not update:
		    action.done('skipped')
		else:
		    cstring = catalog2string(default_catalog)
		    write_file(self, template_pot, cstring, action=action)
	return default_catalogs

    def generate_po(self, target_po_file, default_data, language_data=None,
                    language_data_files=None, update=True):
        """Helper to generate a .po file.

	``default_data`` is the coleltive data from the language neutral XML
	files, and this is what the .po we generate will be based on.

	``language_data`` is colletive data from the corresponding
	language-specific XML files, in case such data is available.

	``language_data_files`` is the list of files that ``language_data``
	is based upon. This is because in some cases multiple XML files
	might need to be combined into one gettext catalog.

        If ``update`` is not set than we will bail out early
        if the file doesn't exist.
	"""
        action = self.w.begin(target_po_file)

        if not update and target_po_file.exists():
            action.done('exists')
            return

        if language_data is not None:
            action.message('Using existing translations from %s' % ", ".join(
	        [l.rel for l in language_data_files]))
            lang_catalog, unmatched = xml2po(default_data, language_data)
            if unmatched:
                action.message("Existing translation XML files for this "
		               "language contains strings not found in the "
		               "default XML files: %s" % (", ".join(unmatched)))
        else:
            action.message('No corresponding XML exists, generating catalog '+
	                   'without translations')
            lang_catalog = xml2po(default_data)

	cstring = catalog2string(lang_catalog)
        action.message("%d strings processed, %d translated." % (
            # Make sure we don't count the header.
            len(lang_catalog),
            len([m for m in lang_catalog if m.string and m.id])))
	write_file(self, target_po_file, cstring, action=action)

    def _iterate(self, language, require_translation=True):
	"""Yield 4-tuples in the form of: (
	    target .po file,
	    source xml data,
	    translated xml data,
	    list of files translated xml data was read from
	)

	This is implemeted as a separate iterator so that later on we can
	also support a mechanism in which multiple xml files are stored in
	one .po file, i.e. on export, multiple xml files needs to be able
	to yield into a single .po target.
	"""
        for kind in self.env.xmlfiles:
	    language_po = language.po(kind)
	    language_xml = language.xml(kind)

	    language_data = None
	    if not language_xml.exists():
		if require_translation:
		    # It's easily possible that say a arrays.xml only
		    # exists in values/, but not in values-xx/.
		    self.w.action('skipped', language_po)
		    self.w.message('%s doesn\'t exist' % language_p.rel)
		    continue
	    else:
		language_data = read_xml(language_xml)

	    template_data = read_xml(self.env.default.xml(kind))
	    yield language_po, template_data, language_data, [language_xml]

    def execute(self):
        env = self.env

        if env.options.language:
            languages = []
            for code in env.options.language:
                languages.append(Language(code, env))
        else:
            languages = env.languages

	# First, make sure the templates exist. This makes the "init"
	# command everything needed to boostrap.
	self.generate_templates(update=False)

        for language in languages:
	    # For each language, generate a .po file. In case a language
	    # already exists (that is, it's xml files exist, use the
	    # existing translations for the new gettext catalog).
            for (target_po,
	         template_data,
	         lang_data,
	         lang_files) in self._iterate(language, require_translation=False):
                self.generate_po(target_po, template_data, lang_data, lang_files,
		                 update=False)

	    # Also for each language, generate the empty .xml resource files.
	    # This will make us pick up the language on subsequent runs.
	    for kind in self.env.xmlfiles:
                write_file(self, language.xml(kind),
                           """<?xml version='1.0' encoding='utf-8'?>\n<resources>\n</resources>""",
		           update=False)


class ExportCommand(InitCommand):
    """The export command.

    Through the --initial flag it shares some functionality with
    the init command, so we inherit from it to be able to use
    some shared methods.
    """

    @classmethod
    def setup_arg_parser(cls, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--initial', action='store_true',
            help='create .po files for new languages based their XML '+
                  'files')
        group.add_argument('--overwrite', action='store_true',
            help='recreate .po files for all languages from their XML '+
                 'counterparts')

    def execute(self):
        env = self.env
        w = self.w

	# First, always update the template files. Note that even if
	# template generation is disabled, we still need to have the
	# catalogs at least in memory for the updating process later on.
	#
        # TODO: Should this really be generated in every case, or do we
        # want to enable the user to set fixed meta data, and simply
        # merge subsequent updates in? Note this may affect the --initial
        # mode below, since it uses the template.
	default_catalogs = self.generate_templates()

        if env.options.initial or env.options.overwrite:
	    # In overwrite or initial mode, we (re)generate .po files
	    # based on any existing localized xml resources.
	    for language in env.languages:
		for (target_po,
	             template_data,
	             lang_data,
	             lang_files) in self._iterate(language):
		    if target_po.exists() and not env.options.overwrite:
			# We are in --initial mode, and the file exists;
			# We have nothing to do.
			w.action('exists', target_po)
		    else:
			# The file either doesnt yet exist, or we are in
			# overwrite mode. Generate it in any case.
			self.generate_po(target_po, template_data,
			                 lang_data, lang_files)

        else:
            for language in env.languages:
                for kind in self.env.xmlfiles:
		    target_po = language.po(kind)
                    if not target_po.exists():
			w.action('skipped', target_po)
			w.message('File does not exist yet. Use --initial')
                        continue

                    action = w.begin(target_po)
                    # If we do not provide a locale, babel will consider this
                    # catalog a template and always write out the default
                    # header. It seemingly does not consider the "Language"
                    # header inside the file at all, and indeed deletes it.
                    # TODO: It deletes all headers it doesn't know, and
                    # overrides others. That sucks.
		    try:
			lang_catalog = read_catalog(target_po, locale=language.code)
		    except UnknownLocaleError:
			action.message('%s is not a valid locale code' % language.code)
			action.done('error')
		    else:
			lang_catalog.update(default_catalogs[kind])
			# TODO: Should we include previous?
			write_file(self, target_po,
			           catalog2string(lang_catalog, include_previous=False),
			           action=action)


class ImportCommand(Command):
    """The import command.
    """

    def _iterate(self, language):
	"""Yield 2-tuples of the target xml files and the source po catalogs.

	This is implemeted as a separate iterator so that later on we can
	also support a mechanism in which multiple xml files are stored in
	one .po file, i.e. on import, a single .po file needs to be able to
	yield into multiple .xml targets.
	"""
        for kind in self.env.xmlfiles:
	    language_po = language.po(kind)
	    language_xml = language.xml(kind)

	    if not language_po.exists():
		self.w.action('skipped', language_xml)
		self.w.message('%s doesn\'t exist' % language_po.rel)
		continue
	    yield language_xml, read_catalog(language_po)

    def execute(self):
        for language in self.env.languages:
	    for target_xml, podata in self._iterate(language):
		self.w.begin(target_xml)
		write_file(self, target_xml, xml2string(po2xml(podata)))