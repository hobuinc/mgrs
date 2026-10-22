"""Exception and compatibility helpers for the native bindings."""

import math
from warnings import filterwarnings, warn

from . import _native

MGRSError = _native.MGRSError


class DeprecatedClassMeta(type):
    """
    Meta class that warns that a given class, or any of its sublasses have been
    deprecated and will call a new class decalred with
    _DeprecatedClassMeta__alias instead

    Credit: https://stackoverflow.com/a/52087847/9469244
    """

    def __new__(cls, name, bases, classdict, *args, **kwargs):

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


class RTreeError(Exception, metaclass=DeprecatedClassMeta):
    """RTree exception, indicates a RTree-related error."""

    _DeprecatedClassMeta__alias = MGRSError
    pass


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

warnings = {
    0x0400: "Latitude Warning",
}


def get_errors(value):
    output = []
    for key in errors.keys():
        if key & value:
            output.append(errors[key])
    return " & ".join(output)


def get_warnings(value):
    output = []
    for key in warnings.keys():
        if key & value:
            output.append(warnings[key])
    return " & ".join(output)


def TO_RADIANS(degrees):
    return float(degrees) * math.pi / 180.0


def TO_DEGREES(radians):
    return float(radians) * 180.0 / math.pi


# Report all runtime warnings from this module, not only the first (default)
filterwarnings("always", category=RuntimeWarning, module="mgrs")


def check_error(result, func, cargs):
    "Error checking proper value returns"
    if result == 0:
        return
    _errors = get_errors(result)
    if _errors:
        raise MGRSError(f'Error in "{func.__name__}": {_errors}')
    _warnings = get_warnings(result)
    if _warnings:
        warn(
            f'Warning in "{func.__name__}": {_warnings} using args: {cargs}',
            category=RuntimeWarning,
            stacklevel=2,
        )
    return
