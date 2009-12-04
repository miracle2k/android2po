# encoding: utf8
"""Adapted from virtualenv's setup.py
"""

import sys, os
try:
    from setuptools import setup
    kw = {'entry_points':
          """[console_scripts]\na2po = android2po:run\n""",
          'zip_safe': False}
except ImportError:
    from distutils.core import setup
    kw = {'scripts': ['scripts/a2po']}
import re

here = os.path.dirname(os.path.abspath(__file__))

# Figure out the version
version_re = re.compile(
    r'__version__ = (\(.*?\))')
fp = open(os.path.join(here, 'android2po.py'))
version = None
for line in fp:
    match = version_re.search(line)
    if match:
        exec "version = %s" % match.group(1)
        version = ".".join(map(str, version))
        break
else:
    raise Exception("Cannot find version in android2po.py")
fp.close()

setup(name='android2po',
      version=version,
      description="Convert between Android string resources and gettext .po files.",
      classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
      ],
      author='Michael Elsdoerfer',
      author_email='michael@elsdoerfer.com',
      url='http://github.com/miracle2k/android2po',
      license='BSD',
      py_modules=['android2po'],
      install_requires = ['lxml',],
      **kw
      )