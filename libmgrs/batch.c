#include <string.h>
#include "batch.h"

#define PI 3.14159265358979323e0
#define MGRS_WIDTH 15

long Convert_Geodetic_To_MGRS_Array(
    const double *points, size_t count, int degrees, long precision,
    char *output, size_t *index)
{
    size_t i;
    long warnings = 0;
    *index = 0;
    if (precision < 0 || precision > 5)
        return MGRS_PRECISION_ERROR;
    for (i = 0; i < count; ++i) {
        double lat = points[2 * i];
        double lon = points[2 * i + 1];
        char text[80] = {0};
        long status = 0;
        if (degrees) {
            /* Preserve the scalar Python API's floating-point order. */
            lat = lat * PI / 180.0;
            lon = lon * PI / 180.0;
        }
        /* Negated comparisons also reject NaN before GeoTrans can cast it. */
        if (!(lat >= -PI / 2 && lat <= PI / 2))
            status |= MGRS_LAT_ERROR;
        if (!(lon >= -PI && lon <= 2 * PI))
            status |= MGRS_LON_ERROR;
        if (!status)
            status = Convert_Geodetic_To_MGRS(lat, lon, precision, text);
        if (status & ~MGRS_LAT_WARNING) {
            *index = i;
            return status;
        }
        if (status && !warnings)
            *index = i;
        warnings |= status;
        memcpy(output + i * MGRS_WIDTH, text, MGRS_WIDTH);
    }
    return warnings;
}

long Convert_MGRS_To_Geodetic_Array(
    const char *codes, size_t count, size_t width, int degrees,
    double *output, size_t *index)
{
    size_t i, j;
    long warnings = 0;
    *index = 0;
    if (width < 1 || width > MGRS_WIDTH)
        return MGRS_STRING_ERROR;
    for (i = 0; i < count; ++i) {
        /* Fixed-width strings need not have a trailing NUL. */
        char text[MGRS_WIDTH + 1] = {0};
        double lat = 0, lon = 0;
        long status = 0;
        int terminated = 0;
        memcpy(text, codes + i * width, width);
        for (j = 0; j < width; ++j) {
            if (!text[j]) {
                terminated = 1;
            } else if (terminated || (unsigned char)text[j] > 127) {
                /* Only NUL padding may follow the first terminator. */
                status = MGRS_STRING_ERROR;
                break;
            }
        }
        if (!status)
            status = Convert_MGRS_To_Geodetic(text, &lat, &lon);
        if (status & ~MGRS_LAT_WARNING) {
            *index = i;
            return status;
        }
        if (status && !warnings)
            *index = i;
        warnings |= status;
        output[2 * i] = degrees ? lat * 180.0 / PI : lat;
        output[2 * i + 1] = degrees ? lon * 180.0 / PI : lon;
    }
    return warnings;
}
