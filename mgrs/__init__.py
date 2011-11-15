from core import rt

import ctypes

class MGRS:
    def __init__(self):
        pass
    
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