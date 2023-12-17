import ctypes
import math
import os
import sysconfig
from ctypes.util import find_library

import packaging.tags


class DeprecatedClassMeta(type):
    """
    Meta class that warns that a given class, or any of its sublasses have been
    deprecated and will call a new class decalred with
    _DeprecatedClassMeta__alias instead

    Credit: https://stackoverflow.com/a/52087847/9469244
    """

    def __new__(cls, name, bases, classdict, *args, **kwargs):
        from warnings import warn

        alias = classdict.get("_DeprecatedClassMeta__alias")

        if alias is not None:

            def new(cls, *args, **kwargs):
                alias = getattr(cls, "_DeprecatedClassMeta__alias")

                if alias is not None:
                    warn(
                        "{} has is deprecated. Please use {} instead".format(
                            cls.__name__, alias.__name__
                        ),
                        DeprecationWarning,
                        stacklevel=2,
                    )

                return alias(*args, **kwargs)

            classdict["__new__"] = new
            classdict["_DeprecatedClassMeta__alias"] = alias

        fixed_bases = []

        for b in bases:
            alias = getattr(b, "_DeprecatedClassMeta__alias", None)

            if alias is not None:
                warn(
                    "{} has is deprecated. Please use {} instead".format(
                        b.__name__, alias.__name__
                    ),
                    DeprecationWarning,
                    stacklevel=2,
                )

            # Avoid duplicate base classes.
            b = alias or b
            if b not in fixed_bases:
                fixed_bases.append(b)

        fixed_bases = tuple(fixed_bases)

        s = super()
        return s.__new__(cls, name, fixed_bases, classdict, *args, **kwargs)


class MGRSError(Exception):
    """MGRS exception, indicates a MGRS-related error."""

    pass


class RTreeError(Exception, metaclass=DeprecatedClassMeta):
    """RTree exception, indicates a RTree-related error."""

    _DeprecatedClassMeta__alias = MGRSError
    pass


def get_windows_platform_name():
    """Constructs libmgrs pyd filename based on Windows platform"""

    libname = "libmgrs"
    tags = list(packaging.tags.cpython_tags())
    t = tags[0]
    name = f"{t.interpreter}-" f"{t.platform}"
    return libname + "." + name + ".pyd"


if os.name == "nt":

    def _load_library(dllname, loadfunction, dllpaths=("",)):
        """Load a DLL via ctypes load function. Return None on failure.
        Try loading the DLL from the current package directory first,
        then from the Windows DLL search path.
        """
        try:
            dllpaths = (os.path.abspath(os.path.dirname(__file__)),) + dllpaths
        except NameError:
            pass  # no __file__ attribute on PyPy and some frozen distributions
        for path in dllpaths:
            if path:
                # temporarily add the path to the PATH environment variable
                # so Windows can find additional DLL dependencies.
                try:
                    oldenv = os.environ["PATH"]
                    os.environ["PATH"] = path + ";" + oldenv
                except KeyError:
                    oldenv = None
            try:
                return loadfunction(os.path.join(path, dllname))
            except (WindowsError, OSError):
                pass
            finally:
                if path and oldenv is not None:
                    os.environ["PATH"] = oldenv
        return None

    try:
        lib_name = get_windows_platform_name()
        rt = None
        # try wheel location
        if not rt:
            p = os.path.join(os.path.dirname(__file__), "..")
            lib_path = os.path.abspath(p)
            rt = _load_library(lib_name, ctypes.cdll.LoadLibrary, (lib_path,))
        # try conda location
        if not rt:
            conda_env = os.environ.get("CONDA_PREFIX", None)
            if conda_env:
                p = os.path.join(conda_env, "Library", "bin")
                rt = _load_library(lib_name, ctypes.cdll.LoadLibrary, (p,))

        if not rt:
            rt = _load_library(lib_name, ctypes.cdll.LoadLibrary)

        if not rt:
            raise MGRSError(f"Unable to load {lib_name}")

        free = None

        def free(m):  # noqa: F811
            global free
            try:
                free = ctypes.cdll.msvcrt.free(m)
            except WindowsError:
                pass

    except (ImportError, WindowsError):
        raise

elif os.name == "posix":
    soabi = sysconfig.get_config_var("SOABI")
    lib_name = "libmgrs.so"
    if soabi:
        lib_name = "libmgrs.{}.so".format(soabi)

    local_library_path = os.path.abspath(os.path.dirname(__file__) + "/..")
    rt = ctypes.CDLL(os.path.join(local_library_path, lib_name))

    if not rt:
        local_library_path = os.path.abspath(os.path.dirname(__file__))
        rt = ctypes.CDLL(os.path.join(local_library_path, lib_name))

        if not rt:
            raise OSError("Could not load mgrs library")

    free = ctypes.CDLL(find_library("c")).free

else:
    raise MGRSError('Unsupported OS "%s"' % os.name)

errors = {
    0x0001: "Latitude Error",
    0x0002: "Longitude Error",
    0x0004: "String Error",
    0x0008: "Precision Error",
    0x0010: "Axis Error",
    0x0020: "Inverse Flattening Error",
    0x0040: "Easting Error",
    0x0080: "Northing Error",
    0x0100: "Zone Error",
    0x0200: "Hemisphere Error",
}


def get_errors(value):
    output = "MGRS Errors: "
    for key in errors.keys():
        if key & value:
            output += errors[key] + " & "
    return output[:-2]


def TO_RADIANS(degrees):
    return float(degrees) * math.pi / 180.0


def TO_DEGREES(radians):
    return float(radians) * 180.0 / math.pi


def check_error(result, func, cargs):
    "Error checking proper value returns"
    if result != 0:
        msg = 'Error in "%s": %s' % (func.__name__, get_errors(result))
        raise MGRSError(msg)
    return


#   long Convert_Geodetic_To_MGRS (double Latitude,
#                                  double Longitude,
#                                  long   Precision,
#                                  char *MGRS);
# /*
#  * The function Convert_Geodetic_To_MGRS converts geodetic (latitude and
#  * longitude) coordinates to an MGRS coordinate string, according to the
#  * current ellipsoid parameters.  If any errors occur, the error code(s)
#  * are returned by the  function, otherwise MGRS_NO_ERROR is returned.
#  *
#  *    Latitude   : Latitude in radians              (input)
#  *    Longitude  : Longitude in radians             (input)
#  *    Precision  : Precision level of MGRS string   (input)
#  *    MGRS       : MGRS coordinate string           (output)
#  *
#  */

rt.Convert_Geodetic_To_MGRS.argtypes = [
    ctypes.c_double,
    ctypes.c_double,
    ctypes.c_long,
    ctypes.c_char_p,
]
rt.Convert_Geodetic_To_MGRS.restype = ctypes.c_long
rt.Convert_Geodetic_To_MGRS.errcheck = check_error

#
# /*
#  * This function converts an MGRS coordinate string to Geodetic (latitude
#  * and longitude in radians) coordinates.  If any errors occur, the error
#  * code(s) are returned by the  function, otherwise MGRS_NO_ERROR is returned
#  *
#  *    MGRS       : MGRS coordinate string           (input)
#  *    Latitude   : Latitude in radians              (output)
#  *    Longitude  : Longitude in radians             (output)
#  *
#  */
#

rt.Convert_MGRS_To_Geodetic.argtypes = [
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
rt.Convert_MGRS_To_Geodetic.restype = ctypes.c_long
rt.Convert_MGRS_To_Geodetic.errcheck = check_error


# /*
#  * The function Convert_UTM_To_MGRS converts UTM (zone, easting, and
#  * northing) coordinates to an MGRS coordinate string, according to the
#  * current ellipsoid parameters.  If any errors occur, the error code(s)
#  * are returned by the  function, otherwise MGRS_NO_ERROR is returned.
#  *
#  *    Zone       : UTM zone                         (input)
#  *    Hemisphere : North or South hemisphere        (input)
#  *    Easting    : Easting (X) in meters            (input)
#  *    Northing   : Northing (Y) in meters           (input)
#  *    Precision  : Precision level of MGRS string   (input)
#  *    MGRS       : MGRS coordinate string           (output)
#  */

rt.Convert_UTM_To_MGRS.argtype = [
    ctypes.c_long,
    ctypes.c_char,
    ctypes.c_double,
    ctypes.c_double,
    ctypes.c_long,
    ctypes.c_char_p,
]
rt.Convert_UTM_To_MGRS.restype = ctypes.c_long
rt.Convert_UTM_To_MGRS.errcheck = check_error

# /*
#  * The function Convert_MGRS_To_UTM converts an MGRS coordinate string
#  * to UTM projection (zone, hemisphere, easting and northing) coordinates
#  * according to the current ellipsoid parameters.  If any errors occur,
#  * the error code(s) are returned by the function, otherwise UTM_NO_ERROR
#  * is returned.
#  *
#  *    MGRS       : MGRS coordinate string           (input)
#  *    Zone       : UTM zone                         (output)
#  *    Hemisphere : North or South hemisphere        (output)
#  *    Easting    : Easting (X) in meters            (output)
#  *    Northing   : Northing (Y) in meters           (output)
#  */

rt.Convert_MGRS_To_UTM.argtype = [
    ctypes.c_char_p,
    ctypes.POINTER(ctypes.c_long),
    ctypes.POINTER(ctypes.c_char),
    ctypes.POINTER(ctypes.c_double),
    ctypes.POINTER(ctypes.c_double),
]
rt.Convert_MGRS_To_UTM.restype = ctypes.c_long
rt.Convert_MGRS_To_UTM.errcheck = check_error
