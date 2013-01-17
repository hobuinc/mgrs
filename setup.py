
from glob import glob
from setuptools import setup

import os

if os.name == 'nt':
    from setuptools import Library as Extension
else:
    from setuptools import Extension

sources = ['libmgrs/mgrs.c',
           'libmgrs/utm.c',
           'libmgrs/ups.c',
           'libmgrs/tranmerc.c',
           'libmgrs/polarst.c']


mgrs = Extension('libmgrs',
                 sources = sources,
                 define_macros = None,
                 include_dirs = ['./libmgrs'],
                 libraries = None,
                 library_dirs = None
                 )

# Get text from README.txt
readme_text = file('./README.rst', 'rb').read()


import os

    
setup(name          = 'mgrs',
      version       = '1.1.0',
      description   = 'MGRS coordinate conversion for Python',
      license       = 'MIT',
      keywords      = 'gis coordinate conversion',
      author        = 'Howard Butler',
      author_email  = 'hobu.inc@gmail.com',
      maintainer        = 'Howard Butler',
      maintainer_email  = 'hobu@hobu.net',
      url   = 'https://github.com/hobu/mgrs',
      long_description = readme_text,
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

