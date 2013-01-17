.. _home:

mgrs: Converting to and from MGRS and Decimal Degrees
------------------------------------------------------------------------------

GeoTrans_ provides C code for converting to and from MGRS, but well, it's 
C code :).  This is a simple ctypes_ wrapper around two of the MGRS-related 
functions in GeoTrans_.

This library has an internal copy of some of the files from GeoTrans_ 2.4.2.

.. _`GeoTrans`: http://earth-info.nga.mil/GandG/geotrans/
.. _`ctypes`: http://docs.python.org/library/ctypes.html



Usage
------------------------------------------------------------------------------

In a nutshell::

    >>> import mgrs
    
    >>> latitude = 42.0
    >>> longitude = -93.0
    
    >>> m = mgrs.MGRS()
    >>> c = m.toMGRS(latitude, longitude)
    >>> c
    '15TWG0000049776'
    
    >>> d = m.toLatLon(c)
    >>> d
    (41.999997975127997, -93.000000000000014)
    
    >>> y = '321942.29N'
    >>> yd = m.dmstodd(y)
    32.328414
    
    >>> d, m, s = m.ddtodms(32.328414)
    >>> d, m, s
    (32.0, 19.0, 42.290400)

You can also control the precision of the MGRS grid with the MGRSPrecision 
arguments in .toMGRS().  Other than that, there isn't too much to it.


