#ifndef MGRS_BATCH_H
#define MGRS_BATCH_H

#include <stddef.h>
#include "mgrs.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The caller owns all buffers and serializes access to GeoTrans state.
 * Forward input/output: count * 2 doubles / count * 15 bytes.
 * Inverse input/output: count * width bytes / count * 2 doubles.
 * Returns the first error (stopping immediately), or accumulated warnings.
 * index identifies the failed row or first warning row. The adapter reuses
 * its buffers; GEOTRANS allocates intermediate coordinate objects per row.
 */
long USE_DLL Convert_Geodetic_To_MGRS_Array(
    const double *points, size_t count, int degrees, long precision,
    char *output, size_t *index);
long USE_DLL Convert_MGRS_To_Geodetic_Array(
    const char *codes, size_t count, size_t width, int degrees,
    double *output, size_t *index);

#ifdef __cplusplus
}
#endif
#endif
