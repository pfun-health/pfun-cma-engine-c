#include "pfun_cma_engine/pfun_cma_engine.h"

#include <math.h>
#include <string.h>

#define MAXPTS 512
#define NMEALS 3
#define EPS 1e-18

static int g_npts = 0;
static double g_t[MAXPTS];
static double g_L[MAXPTS];
static double g_m[MAXPTS];
static double g_c[MAXPTS];
static double g_c_mod[MAXPTS];
static double g_A[MAXPTS];
static double g_a[MAXPTS];
static double g_I_S[MAXPTS];
static double g_I_E[MAXPTS];
static double g_I_E_eff[MAXPTS];
static double g_s_A[MAXPTS];
static double g_G[MAXPTS];
static double g_g[NMEALS * MAXPTS];

int wasm_run_model(double d, double taup, double taug_val, double B, double Cm,
                   double toff, double tM0, double tM1, double tM2, int npts,
                   int activity_on, double A_amp, int noise_on) {
  if (npts < 2)
    npts = 2;
  if (npts > MAXPTS)
    npts = MAXPTS;

  double tM[NMEALS] = {tM0, tM1, tM2};
  for (int i = 0; i < npts; i++) {
    g_t[i] = 24.0 * (double)i / (double)(npts - 1);
  }

  double A_raw[MAXPTS];
  memset(A_raw, 0, sizeof(A_raw));
  if (activity_on) {
    for (int i = 0; i < npts; i++) {
      const double x = g_t[i];
      A_raw[i] = A_amp * (exp(-pow((x - 8.0) / 1.5, 2.0)) +
                          exp(-pow((x - 17.0) / 2.0, 2.0)));
    }
  }

  int seed = 12345;
  int *seed_ptr = noise_on ? &seed : NULL;
  const double *A_ptr = activity_on ? A_raw : NULL;

  run_cma_model(g_t, npts, d, taup, taug_val, NULL, B, Cm, toff, tM, NMEALS,
                seed_ptr, EPS, A_ptr,
                5.0, 0.3, 0.15, 0.5, 0.20, 0.40, 2.0, g_L, g_m, g_c, g_c_mod,
                g_A, g_a, g_I_S, g_I_E, g_I_E_eff, g_s_A, g_G, g_g);

  g_npts = npts;
  return g_npts;
}

int wasm_get_npts(void) { return g_npts; }

double wasm_get_t(int idx) {
  if (idx < 0 || idx >= g_npts)
    return NAN;
  return g_t[idx];
}

double wasm_get_series_value(int series, int idx) {
  if (idx < 0 || idx >= g_npts)
    return NAN;
  switch (series) {
  case 0:
    return g_G[idx];
  case 1:
    return g_I_E[idx];
  case 2:
    return g_c[idx];
  case 3:
    return g_A[idx];
  default:
    return NAN;
  }
}
