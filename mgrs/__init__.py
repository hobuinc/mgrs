from . core import rt

import ctypes
import re

__version__='1.3.2'

class MGRS:
    def __init__(self):
        pass


    def ddtodms(self, dd):
        """Take in dd string and convert to dms"""
        negative = dd < 0
        dd = abs(dd)
        minutes,seconds = divmod(dd*3600,60)
        degrees,minutes = divmod(minutes,60)
        if negative:
            if degrees > 0:
                degrees = -degrees
            elif minutes > 0:
                minutes = -minutes
            else:
                seconds = -seconds
        return (degrees,minutes,seconds)

    def dmstodd(self, dms):
        """ convert dms to dd"""
        size = len(dms)
        letters = 'WENS'
        is_annotated = False

        try:
            float(dms)
        except ValueError:
            for letter in letters:
                if letter in dms.upper():
                    is_annotated = True
                    break
            if not is_annotated:
                raise core.RTreeError("unable to parse '%s' to decimal degrees" % dms)
        is_negative = False
        if is_annotated:
            dms_upper = dms.upper()
            if 'W' in dms_upper or 'S' in dms_upper:
                is_negative = True
        else:
            if dms < 0:
                is_negative = True

        if is_annotated:
            bletters = letters.encode(encoding='utf-8')
            bdms = dms.encode(encoding = 'utf-8')
            dms = bdms.translate(None, bletters).decode('ascii')

            # bletters = bytes(letters, encoding='utf-8')
            # bdms = bytes(dms, encoding='utf-8')
            # dms = bdms.translate(None, bletters).decode('ascii')

            # dms = dms.translate(None, letters) # Python 2.x version

        pieces = dms.split(".")
        D = 0.0
        M = 0.0
        S = 0.0
        divisor = 3600.0
        if len(pieces) == 1:
            S = dms[-2:]
            M = dms[-4:-2]
            D = dms[:-4]
        else:
            S = '{0:s}.{1:s}'.format (pieces[0][-2:], pieces[1])
            M = pieces[0][-4:-2]
            D = pieces[0][:-4]

        DD = float(D) + float(M)/60.0 + float(S)/divisor
        if is_negative:
            DD = DD * -1.0
        return DD

    def toMGRS(self, latitude, longitude, inDegrees=True, MGRSPrecision=5):
        if inDegrees:
            lat = core.TO_RADIANS(latitude)
            lon = core.TO_RADIANS(longitude)
        else:
            lat = latitude
            lon = longitude

        p = ctypes.create_string_buffer(80)
        core.rt.Convert_Geodetic_To_MGRS( lat, lon, MGRSPrecision, p)
        return ctypes.string_at(p)

    def toLatLon(self, MGRS, inDegrees=True):
        plat = ctypes.pointer(ctypes.c_double())
        plon = ctypes.pointer(ctypes.c_double())
        c = ctypes.string_at(MGRS)
        core.rt.Convert_MGRS_To_Geodetic( c, plat, plon)
        if inDegrees:
            lat = core.TO_DEGREES(plat.contents.value)
            lon = core.TO_DEGREES(plon.contents.value)
        else:
            lat = plat.contents.value
            lon = plon.contents.value
        return (lat, lon)

    def MGRSToUTM (self, MGRS) :
        mgrs       = ctypes.string_at(MGRS)
        zone       = ctypes.pointer(ctypes.c_long())
        hemisphere = ctypes.pointer(ctypes.c_char())
        easting    = ctypes.pointer(ctypes.c_double())
        northing   = ctypes.pointer(ctypes.c_double())

        core.rt.Convert_MGRS_To_UTM(mgrs, zone, hemisphere, easting, northing)

        return zone.contents.value, hemisphere.contents.value, easting.contents.value, northing.contents.value

    def UTMToMGRS (self, zone, hemisphere, easting, northing, MGRSPrecision=5) :
        mgrs = ctypes.create_string_buffer(80)

        core.rt.Convert_UTM_To_MGRS(zone, ctypes.c_char(hemisphere), ctypes.c_double(easting), ctypes.c_double(northing), MGRSPrecision, mgrs)

        return mgrs.value
