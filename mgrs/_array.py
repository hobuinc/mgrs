"""Batch conversion using standard-library arrays and the buffer protocol."""

import ctypes
import operator
import sys
import warnings
from array import array
from contextlib import contextmanager

from . import core

MGRS_WIDTH = 15


class _PyBuffer(ctypes.Structure):
    """CPython's public Py_buffer layout (also used by Python 3.9/3.10)."""

    _fields_ = [
        ("buf", ctypes.c_void_p),
        ("obj", ctypes.c_void_p),
        ("len", ctypes.c_ssize_t),
        ("itemsize", ctypes.c_ssize_t),
        ("readonly", ctypes.c_int),
        ("ndim", ctypes.c_int),
        ("format", ctypes.c_char_p),
        ("shape", ctypes.POINTER(ctypes.c_ssize_t)),
        ("strides", ctypes.POINTER(ctypes.c_ssize_t)),
        ("suboffsets", ctypes.POINTER(ctypes.c_ssize_t)),
        ("internal", ctypes.c_void_p),
    ]


_get_buffer = ctypes.pythonapi.PyObject_GetBuffer
_get_buffer.argtypes = [
    ctypes.py_object,
    ctypes.POINTER(_PyBuffer),
    ctypes.c_int,
]
_get_buffer.restype = ctypes.c_int
_release_buffer = ctypes.pythonapi.PyBuffer_Release
_release_buffer.argtypes = [ctypes.POINTER(_PyBuffer)]
_release_buffer.restype = None


@contextmanager
def _buffer_pointer(value):
    # PyBUF_SIMPLE requests contiguous bytes and permits read-only exporters.
    # Unlike from_buffer(), it also reads bytes and read-only memoryviews
    # without copying. The owned export pins storage until the C call ends.
    buffer = _PyBuffer()
    _get_buffer(value, ctypes.byref(buffer), 0)
    try:
        yield buffer.buf
    finally:
        _release_buffer(ctypes.byref(buffer))


def check_result(status, index):
    if not status:
        return
    errors = core.get_errors(status)
    if errors:
        message = f"array conversion failed at row {index}: {errors}"
        raise core.MGRSError(message)
    message = core.get_warnings(status)
    if message:
        warnings.warn(
            f"array conversion: {message}; first affected row {index}",
            RuntimeWarning,
            stacklevel=3,
        )


def to_mgrs(points, in_degrees, precision):
    with memoryview(points) as view:
        native = "<d" if sys.byteorder == "little" else ">d"
        if view.format not in ("d", "@d", "=d", native) or view.itemsize != 8:
            raise TypeError(
                "points must contain native-endian doubles (array('d'))",
            )
        if not view.c_contiguous:
            raise ValueError("points must be C-contiguous")
        if not (
            (view.ndim == 1 and len(view) % 2 == 0)
            or (view.ndim == 2 and view.shape[1] == 2)
        ):
            raise ValueError(
                "points must have shape (2*N,) or (N, 2) in lat,lon order",
            )
        count = view.nbytes // (2 * view.itemsize)
        precision = operator.index(precision)
        if not 0 <= precision <= 5:
            raise core.MGRSError("Precision Error: expected 0 through 5")
        with _buffer_pointer(view) as pointer:
            if count and pointer % ctypes.alignment(ctypes.c_double):
                raise ValueError("points must be aligned for doubles")
            output = bytearray(count * MGRS_WIDTH)
            index = ctypes.c_size_t()
            with _buffer_pointer(output) as target, core._conversion_lock:
                status = core.rt.Convert_Geodetic_To_MGRS_Array(
                    pointer,
                    count,
                    bool(in_degrees),
                    precision,
                    target,
                    ctypes.byref(index),
                )
    check_result(status, index.value)
    return output


def to_latlon(codes, in_degrees, width):
    width = operator.index(width)
    if not 1 <= width <= MGRS_WIDTH:
        raise ValueError("width must be from 1 through 15 bytes")
    with memoryview(codes) as view:
        if view.itemsize != 1 or view.format.lstrip("@=<>!") not in (
            "B",
            "b",
            "c",
        ):
            raise TypeError("codes must be a byte buffer")
        if view.ndim != 1:
            raise ValueError("codes must be a one-dimensional byte buffer")
        if not view.c_contiguous:
            raise ValueError("codes must be C-contiguous")
        if view.nbytes % width:
            raise ValueError("codes length must be a multiple of width")
        count = view.nbytes // width
        output = array("d", [0.0]) * (count * 2)
        index = ctypes.c_size_t()
        with _buffer_pointer(view) as pointer, core._conversion_lock:
            status = core.rt.Convert_MGRS_To_Geodetic_Array(
                pointer,
                count,
                width,
                bool(in_degrees),
                output.buffer_info()[0],
                ctypes.byref(index),
            )
    check_result(status, index.value)
    return output
