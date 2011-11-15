import atexit, os, re, sys
import ctypes
from ctypes.util import find_library

import ctypes


class RTreeError(Exception):
    "RTree exception, indicates a RTree-related error."
    pass
    
if os.name == 'nt':
    lib_name = 'libmgrs.dll'
    try:
        local_dlls = os.path.abspath(os.__file__ + "../../../DLLs")
        original_path = os.environ['PATH']
        os.environ['PATH'] = "%s;%s" % (local_dlls, original_path)
        rt = ctypes.PyDLL(lib_name)
        def free(m):
            try:
                free = ctypes.cdll.msvcrt.free(m)
            except WindowsError:
                pass
    except (ImportError, WindowsError):
        raise
elif os.name == 'posix':
    platform = os.uname()[0]
    lib_name = 'libmgrs.so'
    local_library_path = os.path.abspath(os.path.dirname(__file__) + "/..")
    if platform == 'Darwin':
        free = ctypes.CDLL(find_library('libc')).free
    else:
        free = ctypes.CDLL(find_library('libc.so.6')).free
    rt = ctypes.CDLL(os.path.join(local_library_path, lib_name))
else:
    raise RTreeError('Unsupported OS "%s"' % os.name)