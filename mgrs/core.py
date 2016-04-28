import atexit, os, re, sys
import ctypes
from ctypes.util import find_library
import sysconfig
import math

class RTreeError(Exception):
    "RTree exception, indicates a RTree-related error."
    pass

if os.name == 'nt':
    try:
        local_dlls = sys.path
        original_path = os.environ['PATH']
        os.environ['PATH'] = "%s;%s" % (';'.join(local_dlls), original_path)
        try:
            # Python 2
            rt = ctypes.PyDLL('libmgrs.pyd')
        except OSError:
            # Python 3
            rt = ctypes.PyDLL('libmgrs.cp35-win32.pyd')
        def free(m):
            try:
                free = ctypes.cdll.msvcrt.free(m)
            except WindowsError:
                pass
    except (ImportError, WindowsError):
        raise
elif os.name == 'posix':
    platform = os.uname()[0]
    soabi = sysconfig.get_config_var('SOABI')
    if soabi:
        lib_name = 'libmgrs.{}.so'.format(soabi)
    else:
        lib_name = 'libmgrs.so'
    local_library_path = os.path.abspath(os.path.dirname(__file__) + "/..")
    free = ctypes.CDLL(find_library('c')).free
    rt = ctypes.CDLL(os.path.join(local_library_path, lib_name))
else:
    raise RTreeError('Unsupported OS "%s"' % os.name)

errors = {  0x0001: "Latitude Error",
            0x0002: "Longitude Error",
            0x0004: "String Error",
            0x0008: "Precision Error",
            0x0010: "Axis Error",
            0x0020: "Inverse Flattening Error",
            0x0040: "Easting Error",
            0x0080: "Northing Error",
            0x0100: "Zone Error",
            0x0200: "Hemisphere Error"
         }

def get_errors(value):
    output = 'MGRS Errors: '
    for key in errors.keys():
        if key & value:
            output += errors[key] + " & "
    return output[:-2]

def TO_RADIANS(degrees):
    return (float(degrees) * math.pi/180.0)

def TO_DEGREES(radians):
    return (float(radians) * 180.0/math.pi)


def check_error(result, func, cargs):
    "Error checking proper value returns"
    if result != 0:
        msg = 'Error in "%s": %s' % (func.__name__, get_errors(result) )
        raise RTreeError(msg)
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

rt.Convert_Geodetic_To_MGRS.argtypes = [ctypes.c_double, ctypes.c_double, ctypes.c_long, ctypes.c_char_p]
rt.Convert_Geodetic_To_MGRS.restype = ctypes.c_long
rt.Convert_Geodetic_To_MGRS.errcheck = check_error

#
# /*
#  * This function converts an MGRS coordinate string to Geodetic (latitude
#  * and longitude in radians) coordinates.  If any errors occur, the error
#  * code(s) are returned by the  function, otherwise MGRS_NO_ERROR is returned.
#  *
#  *    MGRS       : MGRS coordinate string           (input)
#  *    Latitude   : Latitude in radians              (output)
#  *    Longitude  : Longitude in radians             (output)
#  *
#  */
#

rt.Convert_MGRS_To_Geodetic.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
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

rt.Convert_UTM_To_MGRS.argtype = [ctypes.c_long, ctypes.c_char, ctypes.c_double, ctypes.c_double, ctypes.c_long, ctypes.c_char_p]
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

rt.Convert_MGRS_To_UTM.argtype = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_long), ctypes.POINTER(ctypes.c_char), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double)]
rt.Convert_MGRS_To_UTM.restype = ctypes.c_long
rt.Convert_MGRS_To_UTM.errcheck = check_error
