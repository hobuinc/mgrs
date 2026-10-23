// C API adapter for NGA GEOTRANS 3.10; local changes are documented in
// geotrans3.10/README.rst.
// Callers serialize access, including Set/Get_MGRS_Parameters. The Python
// extension holds its projection mutex for all scalar and batch calls.
#include "mgrs.h"
#include "geotrans3.10/CoordinateSystems/mgrs/MGRS.h"
#include "CoordinateConversionException.h"
#include "ErrorMessages.h"
#include "GeodeticCoordinates.h"
#include "MGRSorUSNGCoordinates.h"
#include "UPSCoordinates.h"
#include "UTMCoordinates.h"

#include <cmath>
#include <cstring>
#include <memory>
#include <utility>

namespace {
namespace cc = MSP::CCS;
constexpr double pi = 3.14159265358979323e0;

struct ProjectionState {
    double a = 6378137.0;
    double f = 1.0 / 298.257223563;
    char code[3] = "WE";
    std::unique_ptr<cc::MGRS> projection;

    cc::MGRS &get() {
        if (!projection) {
            projection = std::make_unique<cc::MGRS>(a, f, code);
        }
        return *projection;
    }
};

ProjectionState &state() {
    static ProjectionState value;
    return value;
}

long error_status(cc::CoordinateConversionException &error) {
    const char *message = error.getMessage();
    struct ErrorMapping { const char *message; long status; };
    const ErrorMapping errors[] = {
        {cc::ErrorMessages::latitude, MGRS_LAT_ERROR},
        {cc::ErrorMessages::longitude, MGRS_LON_ERROR},
        {cc::ErrorMessages::precision, MGRS_PRECISION_ERROR},
        {cc::ErrorMessages::semiMajorAxis, MGRS_A_ERROR},
        {cc::ErrorMessages::ellipsoidFlattening, MGRS_INV_F_ERROR},
        {cc::ErrorMessages::easting, MGRS_EASTING_ERROR},
        {cc::ErrorMessages::northing, MGRS_NORTHING_ERROR},
        {cc::ErrorMessages::zone, MGRS_ZONE_ERROR},
        {cc::ErrorMessages::zoneOverride, MGRS_ZONE_ERROR},
        {cc::ErrorMessages::hemisphere, MGRS_HEMISPHERE_ERROR},
        {cc::ErrorMessages::radius, MGRS_EASTING_ERROR | MGRS_NORTHING_ERROR},
    };
    for (const auto &entry : errors) {
        if (std::strcmp(message, entry.message) == 0) {
            return entry.status;
        }
    }
    // Invalid grid strings, areas and ellipsoid codes have no more specific
    // representation in the historical MGRS status API.
    return MGRS_STRING_ERROR;
}

template <typename Function>
long convert(Function &&function) {
    try {
        return function();
    } catch (cc::CoordinateConversionException &error) {
        return error_status(error);
    }
}

long warning_status(const cc::CoordinateTuple &result) {
    // The MGRS conversion paths attach latitude-band warnings to tuples.
    return result.warningMessage()[0] ? MGRS_LAT_WARNING : MGRS_NO_ERROR;
}

long precision_status(long precision) {
    return precision < 0 || precision > 5 ? MGRS_PRECISION_ERROR : MGRS_NO_ERROR;
}

bool normalize_string(const char *text, char (&normalized)[16]) {
    if (!text) {
        return false;
    }
    const auto digit = [](char ch) { return ch >= '0' && ch <= '9'; };
    const auto letter = [](char ch) {
        return (ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z');
    };
    size_t length = 0;
    for (; *text; ++text) {
        const char ch = *text;
        // Normalize before applying the length limit or creating an upstream
        // coordinate tuple, which would otherwise truncate long spaced input.
        if (ch == ' ' || ch == '\t' || ch == '\n' || ch == '\r' ||
            ch == '\v' || ch == '\f') {
            continue;
        }
        if ((!digit(ch) && !letter(ch)) || length == sizeof(normalized) - 1) {
            return false;
        }
        normalized[length++] = ch;
    }
    normalized[length] = '\0';

    // Require the whole string to match [zone] + 3 letters + paired digits.
    // GEOTRANS checks geographic validity, but can ignore letters after digits.
    size_t i = 0;
    while (digit(normalized[i])) {
        ++i;
    }
    if (i > 2) {
        return false;
    }
    const size_t letters = i;
    while (letter(normalized[i])) {
        ++i;
    }
    if (i - letters != 3) {
        return false;
    }
    const size_t digits = i;
    while (digit(normalized[i])) {
        ++i;
    }
    return i == length && i - digits <= 10 && (i - digits) % 2 == 0;
}

long grid_status(char hemisphere, double easting, double northing, bool utm) {
    long status = MGRS_NO_ERROR;
    if (hemisphere != 'N' && hemisphere != 'S') {
        status |= MGRS_HEMISPHERE_ERROR;
    }
    if (!(easting >= (utm ? 100000.0 : 0.0) &&
          easting <= (utm ? 900000.0 : 4000000.0))) {
        status |= MGRS_EASTING_ERROR;
    }
    if (!(northing >= 0.0 && northing <= (utm ? 10000000.0 : 4000000.0))) {
        status |= MGRS_NORTHING_ERROR;
    }
    return status;
}
} // namespace

long Set_MGRS_Parameters(double a, double f, char *ellipsoid_code) {
    long status = MGRS_NO_ERROR;
    if (!(a > 0.0) || !std::isfinite(a)) {
        status |= MGRS_A_ERROR;
    }
    if (!(f >= 1.0 / 350.0 && f <= 1.0 / 250.0)) {
        status |= MGRS_INV_F_ERROR;
    }
    if (!ellipsoid_code || std::strlen(ellipsoid_code) != 2) {
        status |= MGRS_STRING_ERROR;
    }
    if (status) {
        return status;
    }
    return convert([&] {
        auto replacement = std::make_unique<cc::MGRS>(a, f, ellipsoid_code);
        auto &parameters = state();
        parameters.a = a;
        parameters.f = f;
        std::memcpy(parameters.code, ellipsoid_code, 3);
        parameters.projection = std::move(replacement);
        return MGRS_NO_ERROR;
    });
}

void Get_MGRS_Parameters(double *a, double *f, char *ellipsoid_code) {
    const auto &parameters = state();
    *a = parameters.a;
    *f = parameters.f;
    std::memcpy(ellipsoid_code, parameters.code, 3);
}

long Convert_Geodetic_To_MGRS(double latitude, double longitude,
                             long precision, char *mgrs) {
    long status = precision_status(precision);
    if (!(latitude >= -pi / 2 && latitude <= pi / 2)) {
        status |= MGRS_LAT_ERROR;
    }
    if (!(longitude >= -pi && longitude <= 2 * pi)) {
        status |= MGRS_LON_ERROR;
    }
    if (status) {
        return status;
    }
    return convert([&] {
        cc::GeodeticCoordinates input(cc::CoordinateType::geodetic, longitude, latitude);
        std::unique_ptr<cc::MGRSorUSNGCoordinates> result(
            state().get().convertFromGeodetic(&input, precision));
        std::strcpy(mgrs, result->MGRSString());
        return warning_status(*result);
    });
}

long Convert_MGRS_To_Geodetic(char *mgrs, double *latitude, double *longitude) {
    char normalized[16] = {};
    if (!normalize_string(mgrs, normalized)) {
        return MGRS_STRING_ERROR;
    }
    return convert([&] {
        cc::MGRSorUSNGCoordinates input(cc::CoordinateType::militaryGridReferenceSystem, normalized);
        std::unique_ptr<cc::GeodeticCoordinates> result(state().get().convertToGeodetic(&input));
        *latitude = result->latitude();
        *longitude = result->longitude();
        return warning_status(*result);
    });
}

long Convert_UTM_To_MGRS(long zone, char hemisphere, double easting,
                        double northing, long precision, char *mgrs) {
    long status = grid_status(hemisphere, easting, northing, true) | precision_status(precision);
    if (zone < 1 || zone > 60) {
        status |= MGRS_ZONE_ERROR;
    }
    if (status) {
        return status;
    }
    return convert([&] {
        cc::UTMCoordinates input(cc::CoordinateType::universalTransverseMercator,
                                 zone, hemisphere, easting, northing);
        std::unique_ptr<cc::MGRSorUSNGCoordinates> result(state().get().convertFromUTM(&input, precision));
        std::strcpy(mgrs, result->MGRSString());
        return warning_status(*result);
    });
}

long Convert_MGRS_To_UTM(char *mgrs, long *zone, char *hemisphere,
                        double *easting, double *northing) {
    char normalized[16] = {};
    if (!normalize_string(mgrs, normalized)) {
        return MGRS_STRING_ERROR;
    }
    return convert([&] {
        cc::MGRSorUSNGCoordinates input(cc::CoordinateType::militaryGridReferenceSystem, normalized);
        std::unique_ptr<cc::UTMCoordinates> result(state().get().convertToUTM(&input));
        *zone = result->zone();
        *hemisphere = result->hemisphere();
        *easting = result->easting();
        *northing = result->northing();
        return warning_status(*result);
    });
}

long Convert_UPS_To_MGRS(char hemisphere, double easting, double northing,
                        long precision, char *mgrs) {
    const long status = grid_status(hemisphere, easting, northing, false) | precision_status(precision);
    if (status) {
        return status;
    }
    return convert([&] {
        cc::UPSCoordinates input(cc::CoordinateType::universalPolarStereographic,
                                 hemisphere, easting, northing);
        std::unique_ptr<cc::MGRSorUSNGCoordinates> result(state().get().convertFromUPS(&input, precision));
        std::strcpy(mgrs, result->MGRSString());
        return warning_status(*result);
    });
}

long Convert_MGRS_To_UPS(char *mgrs, char *hemisphere, double *easting, double *northing) {
    char normalized[16] = {};
    if (!normalize_string(mgrs, normalized)) {
        return MGRS_STRING_ERROR;
    }
    return convert([&] {
        cc::MGRSorUSNGCoordinates input(cc::CoordinateType::militaryGridReferenceSystem, normalized);
        std::unique_ptr<cc::UPSCoordinates> result(state().get().convertToUPS(&input));
        *hemisphere = result->hemisphere();
        *easting = result->easting();
        *northing = result->northing();
        return warning_status(*result);
    });
}
