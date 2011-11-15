
from glob import glob
from setuptools import setup, Extension

sources = ['libmgrs/mgrs.c']
mgrs = Extension('libmgrs',
                 sources = sources,
                 define_macros = None,
                 include_dirs = ['./libmgrs'],
                 libraries = None,
                 library_dirs = None
                 )

import os

    
setup(name          = 'mgrs',
      version       = 1.0,
      description   = 'MGRS coordinate conversion for Python',
      license       = 'MIT',
      keywords      = 'gis coordinate conversion',
      author        = 'Howard Butler',
      author_email  = 'hobu.inc@gmail.com',
      maintainer        = 'Howard Butler',
      maintainer_email  = 'hobu@hobu.net',
      url   = 'http://pypi.python.org/pypy/mgrs',
      # long_description = readme_text,
      ext_modules      = [mgrs],
      packages      = ['mgrs'],
      install_requires = ['setuptools'],
      test_suite = 'tests.test_suite',
      # data_files = data_files,
      zip_safe = False,
      classifiers   = [
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: C',
        'Programming Language :: C++',
        'Programming Language :: Python',
        'Topic :: Scientific/Engineering :: GIS',
        'Topic :: Database',
        ],
)

