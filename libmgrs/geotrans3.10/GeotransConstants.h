//Classification: UNCLASSIFIED

/******************************************************************************
 *
 * Filename: GeotransConstants.h
 * 
 * Copyright BAE Systems Inc. 2019 ALL RIGHTS RESERVED
 * 
 * DATE       NAME     DR#         DESCRIPTION
 * 07/25/2019 Krinsky  MSP-887     Initial Submital
 ******************************************************************************/

#ifndef GTS_CONSTANTS_H
#define GTS_CONSTANTS_H

namespace
{
   const double PI        = 3.14159265358979323e0;
   const double PI_OVER_2 = ( PI / 2.0 );
   const double PI_OVER_3 = ( PI / 3.0 );
   const double PI_OVER_4 = ( PI / 4.0 );
   const double TWO_PI    = (2.0 * PI);

   const double ONE_THIRD = (1.0 / 3.0);

   const double DEG_PER_RAD     = 180.0 / PI;
   const double RAD_PER_DEG     = PI / 180.0;

   const double TWO_PLUS_PI_OVER_2 = (2.0 + PI_OVER_2);
   const double ONE_PLUS_PI_OVER_2 = (1.0 + PI_OVER_2);

   const double ONE_DEG        = ( 1.0 * PI / 180);  /* 1  degree in radians */
   const double THIRTY_ONE_DEG = (31.0 * PI / 180);  /* 31 degrees in radians */
}

#endif
