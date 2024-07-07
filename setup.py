from setuptools import Extension, setup

sources = [
    "libmgrs/mgrs.c",
    "libmgrs/utm.c",
    "libmgrs/ups.c",
    "libmgrs/tranmerc.c",
    "libmgrs/polarst.c",
]


mgrs = Extension(
    "libmgrs",
    sources=sources,
    include_dirs=["./libmgrs"],
)

setup_args = dict(ext_modules=[mgrs])

setup(**setup_args)
