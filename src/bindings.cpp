#include <pybind11/pybind11.h>

#include <cmath>
#include <cstdint>
#include <limits>
#include <cstring>
#include <vector>
#include <stdexcept>
#include <string>

#include "rust_backend.h"

namespace py = pybind11;

namespace {
constexpr double pi = 3.14159265358979323e0;
constexpr py::ssize_t mgrs_width = 15;

struct MGRSError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct ErrorName {
    long bit;
    const char *name;
};
constexpr ErrorName errors[] = {
    {MGRS_LAT_ERROR, "Latitude Error"},
    {MGRS_LON_ERROR, "Longitude Error"},
    {MGRS_STRING_ERROR, "String Error"},
    {MGRS_PRECISION_ERROR, "Precision Error"},
    {MGRS_A_ERROR, "Axis Error"},
    {MGRS_INV_F_ERROR, "Inverse Flattening Error"},
    {MGRS_EASTING_ERROR, "Easting Error"},
    {MGRS_NORTHING_ERROR, "Northing Error"},
    {MGRS_ZONE_ERROR, "Zone Error"},
    {MGRS_HEMISPHERE_ERROR, "Hemisphere Error"},
};

void check_result(long status, const char *function, bool batch = false,
                  size_t index = 0) {
    if (!status) {
        return;
    }
    if (status & (MGRS_PANIC | MGRS_LAYOUT_ERROR)) {
        throw std::runtime_error("Rust MGRS backend failed internally");
    }
    std::string message;
    for (auto error : errors) {
        if (status & error.bit) {
            if (!message.empty()) {
                message += " & ";
            }
            message += error.name;
        }
    }
    if (!message.empty()) {
        const auto prefix = batch
            ? "array conversion failed at row " + std::to_string(index) + ": "
            : std::string("Error in \"") + function + "\": ";
        throw MGRSError(prefix + message);
    }
    if (status & MGRS_LAT_WARNING) {
        message = batch
            ? "array conversion: Latitude Warning; first affected row "
                  + std::to_string(index)
            : std::string("Warning in \"") + function + "\": Latitude Warning";
        if (PyErr_WarnEx(PyExc_RuntimeWarning, message.c_str(), 1) < 0) {
            throw py::error_already_set();
        }
    }
}

// Rust projection state is immutable and shareable. Only owned native inputs
// and unpublished output storage may be accessed while the GIL is released.
template <typename Function>
long convert(Function &&function) {
    py::gil_scoped_release release;
    return function();
}

long bounded_index(py::handle value, long maximum, bool precision) {
    auto index = py::reinterpret_steal<py::object>(PyNumber_Index(value.ptr()));
    if (!index) {
        throw py::error_already_set();
    }
    int overflow = 0;
    long result = PyLong_AsLongAndOverflow(index.ptr(), &overflow);
    if (PyErr_Occurred()) {
        throw py::error_already_set();
    }
    if (overflow || result < (precision ? 0 : 1) || result > maximum) {
        if (precision) {
            throw MGRSError("Precision Error: expected 0 through 5");
        }
        throw py::value_error("width must be from 1 through 15 bytes");
    }
    return result;
}

std::string code_bytes(py::handle value, const char *encoding = "utf-8") {
    py::object encoded;
    if (PyUnicode_Check(value.ptr())) {
        encoded = py::reinterpret_steal<py::object>(
            PyUnicode_AsEncodedString(value.ptr(), encoding, "strict"));
        if (!encoded) {
            throw py::error_already_set();
        }
        value = encoded;
    }
    if (!PyBytes_Check(value.ptr())) {
        throw py::type_error("MGRS must be str or bytes");
    }
    std::string text(PyBytes_AS_STRING(value.ptr()), PyBytes_GET_SIZE(value.ptr()));
    // Scalar Python strings have explicit lengths: do not let an embedded NUL
    // hide trailing input from the C API. Fixed-width batch padding is separate.
    for (unsigned char ch : text) {
        if (!ch) {
            throw MGRSError("String Error: MGRS must not contain NUL bytes");
        }
        if (ch > 127) {
            throw MGRSError("String Error: MGRS must contain ASCII bytes");
        }
    }
    return text;
}

bool native_double(const py::buffer_info &info) {
    const std::uint16_t endian = 1;
    const char *native = *reinterpret_cast<const unsigned char *>(&endian)
        ? "<d" : ">d";
    return info.itemsize == sizeof(double) &&
        (info.format == "d" || info.format == "@d" ||
         info.format == "=d" || info.format == native);
}

struct MGRS {
    std::string to_mgrs(double latitude, double longitude, bool degrees,
                        py::handle requested_precision) const {
        const long precision = bounded_index(requested_precision, 5, true);
        double point[] = {latitude, longitude};
        char text[mgrs_width + 1] = {};
        size_t index = 0;
        const long status = convert([&] {
            return mgrs_rust_forward(
                point, 1, degrees, precision, reinterpret_cast<std::uint8_t *>(text), &index);
        });
        check_result(status, "Convert_Geodetic_To_MGRS");
        return text;
    }

    py::tuple to_latlon(py::handle code, bool degrees) const {
        auto text = code_bytes(code);
        double latitude = 0, longitude = 0;
        const long status = convert([&] {
            return mgrs_rust_inverse(reinterpret_cast<const std::uint8_t *>(text.data()),
                                     text.size(), &latitude, &longitude);
        });
        check_result(status, "Convert_MGRS_To_Geodetic");
        if (degrees) {
            latitude = latitude * 180.0 / pi;
            longitude = longitude * 180.0 / pi;
        }
        return py::make_tuple(latitude, longitude);
    }

    std::string geometry_text(py::handle code, bool geojson) const {
        auto text = code_bytes(code);
        std::string output(1024, '\0');
        std::size_t required = 0;
        const long status = convert([&] {
            auto call = [&] {
                auto function = geojson ? mgrs_rust_to_geojson : mgrs_rust_to_wkt;
                return function(
                    reinterpret_cast<const std::uint8_t *>(text.data()), text.size(),
                    reinterpret_cast<std::uint8_t *>(output.data()), output.size(), &required);
            };
            auto result = call();
            if (required > output.size()) {
                output.resize(required);
                result = call();
            }
            return result;
        });
        check_result(status, geojson ? "Convert_MGRS_To_GeoJSON" : "Convert_MGRS_To_WKT");
        output.resize(required);
        return output;
    }

    std::string to_wkt(py::handle code) const {
        return geometry_text(code, false);
    }

    py::dict to_geojson(py::handle code) const {
        // Standard-library JSON constructs only built-in dict/list/str/float
        // values, suitable as the value of an object's __geo_interface__.
        auto text = geometry_text(code, true);
        return py::module_::import("json").attr("loads")(text).cast<py::dict>();
    }

    py::tuple mgrs_to_utm(py::handle code, const std::string &encoding) const {
        auto text = code_bytes(code, encoding.c_str());
        std::int32_t zone = 0;
        char hemisphere = 0;
        double easting = 0, northing = 0;
        const long status = convert([&] {
            return mgrs_rust_to_utm(
                reinterpret_cast<const std::uint8_t *>(text.data()), text.size(),
                &zone, reinterpret_cast<std::uint8_t *>(&hemisphere), &easting, &northing);
        });
        check_result(status, "Convert_MGRS_To_UTM");
        return py::make_tuple(zone, std::string(1, hemisphere), easting, northing);
    }

    std::string utm_to_mgrs(long zone, py::handle hemisphere, double easting,
                            double northing, py::handle requested_precision) const {
        const long precision = bounded_index(requested_precision, 5, true);
        auto hemi = code_bytes(hemisphere);
        if (hemi.size() != 1) {
            throw py::type_error("hemisphere must be one character");
        }
        if (!std::isfinite(easting) || !std::isfinite(northing)) {
            check_result((!std::isfinite(easting) ? MGRS_EASTING_ERROR : 0) |
                         (!std::isfinite(northing) ? MGRS_NORTHING_ERROR : 0),
                         "Convert_UTM_To_MGRS");
        }
        char text[80] = {};
        const long status = convert([&] {
            return mgrs_rust_from_utm(
                zone, hemi[0], easting, northing, precision,
                reinterpret_cast<std::uint8_t *>(text));
        });
        check_result(status, "Convert_UTM_To_MGRS");
        return text;
    }

    py::bytearray to_mgrs_array(py::buffer points, bool degrees,
                                py::handle requested_precision) const {
        auto info = points.request();
        if (!native_double(info)) {
            throw py::type_error("points must contain native-endian doubles (array('d'))");
        }
        if (!PyBuffer_IsContiguous(info.view(), 'C')) {
            throw py::value_error("points must be C-contiguous");
        }
        if (!((info.ndim == 1 && info.size % 2 == 0) ||
              (info.ndim == 2 && info.shape[1] == 2))) {
            throw py::value_error("points must have shape (2*N,) or (N, 2) in lat,lon order");
        }
        const auto count = info.size / 2;
        if (count && reinterpret_cast<std::uintptr_t>(info.ptr) % alignof(double)) {
            throw py::value_error("points must be aligned for doubles");
        }
        const long precision = bounded_index(requested_precision, 5, true);
        if (count > PY_SSIZE_T_MAX / mgrs_width) {
            throw std::overflow_error("output byte buffer is too large");
        }
        auto output = py::reinterpret_steal<py::bytearray>(
            PyByteArray_FromStringAndSize(nullptr, count * mgrs_width));
        if (!output) {
            throw py::error_already_set();
        }
        // Snapshot mutable Python storage before releasing the GIL.
        std::vector<double> input(info.size);
        if (info.size) {
            std::memcpy(input.data(), info.ptr, info.size * sizeof(double));
        }
        char *target = PyByteArray_AS_STRING(output.ptr());
        size_t index = 0;
        const long status = convert([&] {
            return mgrs_rust_forward(
                input.data(), count, degrees, precision,
                reinterpret_cast<std::uint8_t *>(target), &index);
        });
        check_result(status, "Convert_Geodetic_To_MGRS_Array", true, index);
        return output;
    }

    py::object to_latlon_array(py::buffer codes, bool degrees,
                               py::handle requested_width) const {
        const long width = bounded_index(requested_width, mgrs_width, false);
        auto info = codes.request();
        auto format = info.format;
        if (format.size() == 2 && std::string("@=<>!").find(format[0]) != std::string::npos) {
            format.erase(0, 1);
        }
        if (info.itemsize != 1 || (format != "B" && format != "b" && format != "c")) {
            throw py::type_error("codes must be a byte buffer");
        }
        if (info.ndim != 1) {
            throw py::value_error("codes must be a one-dimensional byte buffer");
        }
        if (!PyBuffer_IsContiguous(info.view(), 'C')) {
            throw py::value_error("codes must be C-contiguous");
        }
        if (info.size % width) {
            throw py::value_error("codes length must be a multiple of width");
        }
        const auto count = info.size / width;
        if (count > PY_SSIZE_T_MAX / (2 * sizeof(double))) {
            throw std::overflow_error("output numeric buffer is too large");
        }
        auto seed = py::module_::import("array").attr("array")("d", py::make_tuple(0.0));
        auto output = py::reinterpret_steal<py::object>(PySequence_Repeat(seed.ptr(), count * 2));
        if (!output) {
            throw py::error_already_set();
        }
        auto target = py::reinterpret_borrow<py::buffer>(output).request(true);
        std::vector<std::uint8_t> input(info.size);
        if (info.size) {
            std::memcpy(input.data(), info.ptr, info.size);
        }
        auto *coordinates = static_cast<double *>(target.ptr);
        size_t index = 0;
        const long status = convert([&] {
            return mgrs_rust_inverse_array(
                input.data(), count, width, degrees, coordinates, &index);
        });
        check_result(status, "Convert_MGRS_To_Geodetic_Array", true, index);
        return output;
    }
};
} // namespace

PYBIND11_MODULE(_native, module) {
    module.doc() = "MGRS conversions with the statically linked Rust GEOTRANS 3.10 translation.";
    module.attr("backend") = "rust";
    py::register_exception<MGRSError>(module, "MGRSError", PyExc_Exception);
    py::class_<MGRS>(module, "MGRS")
        .def(py::init<>())
        .def("toMGRS", &MGRS::to_mgrs, py::arg("latitude"), py::arg("longitude"),
             py::arg("inDegrees") = true, py::arg("MGRSPrecision") = 5)
        .def("toLatLon", &MGRS::to_latlon, py::arg("MGRS"), py::arg("inDegrees") = true)
        .def("toWKT", &MGRS::to_wkt, py::arg("MGRS"),
             "Return the full cell as a WGS84 longitude/latitude WKT POLYGON. "
             "Curved edges are sampled; antimeridian longitudes may exceed +/-180.")
        .def("toGeoJSON", &MGRS::to_geojson, py::arg("MGRS"),
             "Return a __geo_interface__ geometry mapping using built-in types. "
             "Coordinates are WGS84 longitude/latitude. Antimeridian crossings "
             "produce a MultiPolygon; other cells produce a Polygon.")
        .def("MGRSToUTM", &MGRS::mgrs_to_utm, py::arg("MGRS"), py::arg("encoding") = "utf-8")
        .def("UTMToMGRS", &MGRS::utm_to_mgrs, py::arg("zone"), py::arg("hemisphere"),
             py::arg("easting"), py::arg("northing"), py::arg("MGRSPrecision") = 5)
        .def("toMGRSArray", &MGRS::to_mgrs_array, py::arg("points"),
             py::arg("inDegrees") = true, py::arg("MGRSPrecision") = 5,
             "Convert contiguous interleaved doubles to NUL-padded 15-byte records.")
        .def("toLatLonArray", &MGRS::to_latlon_array, py::arg("codes"),
             py::arg("inDegrees") = true, py::kw_only(), py::arg("width") = 15,
             "Convert fixed-width byte records to an interleaved array('d').");
}
