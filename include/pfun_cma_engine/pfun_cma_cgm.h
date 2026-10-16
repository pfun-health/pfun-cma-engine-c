/*
  pfun_cma_cgm.h: CGM data ingestion and CMA model curve fitting.

  Ingestion mirrors pfun-cma-model's `format_data` (engine/data_utils.py).
  Fitting (pfun_cma_fit) requires GSL (nonlinear least squares).
*/

#ifndef PFUN_CMA_CGM_H
#define PFUN_CMA_CGM_H

#ifdef __cplusplus
extern "C" {
#endif

#define PFUN_CGM_DEFAULT_N 1024

typedef struct {
  int N;        /* number of samples */
  double *t;    /* time of day, decimal hours (local) */
  double *G;    /* normalized glucose in [0, 2] */
  double *value;/* raw glucose (mg/dL or mmol/L) */
  double *time; /* UTC epoch seconds (bin mean) */
  int mmoll;    /* 1 if units were guessed to be mmol/L, else mg/dL */
} pfun_cgm_data;

/* Guess units: returns 1 for mmol/L, 0 for mg/dL (nearest to reference ranges) */
int pfun_guess_glucose_units(const double *v, int n);
/* Normalize glucose to [0, 2] (units: 0=mg/dL, 1=mmol/L) */
double pfun_normalize_glucose(double g, int mmoll);
/* Parse ISO8601 ("YYYY-MM-DD[T ]HH:MM:SS[.f][Z|+HH:MM]"). Rejects nonfinite
 * seconds. Returns 0 on success. out_epoch: UTC seconds; out_tod: local
 * time-of-day in hours. */
int pfun_parse_iso8601(const char *s, double *out_epoch, double *out_tod);

/* Ingest raw samples (epoch, tod, raw value) -> N evenly binned, interpolated
 * samples. Local time is unwrapped during interpolation and wrapped to [0,24)
 * in the result. Returns 0 on success; free with pfun_cgm_data_free. */
int pfun_cgm_format(const double *epoch, const double *tod, const double *value,
                    int n, int N, pfun_cgm_data *out);
/* Ingest a CSV with a header containing a time column ("time", "ts_utc" or
 * "ts_local", "systemTime" or "displayTime") and a value column ("value" or
 * "sg"). If both UTC and local timestamp columns are present, UTC determines
 * epoch ordering and the local column determines time of day. Returns 0 on
 * success. */
int pfun_cgm_read_csv(const char *path, int N, pfun_cgm_data *out);
void pfun_cgm_data_free(pfun_cgm_data *d);

/* Fit result for bounded params (d, taup, taug, B, Cm, toff) */
typedef struct {
  double params[6];
  double rss;     /* residual sum of squares */
  double rmse;
  int iterations;
  int status;     /* GSL status of convergence (0 = success) */
} pfun_fit_result;

/* Estimate meal onset one hour before G peaks (>= 2h apart), clamped at
 * midnight. Returns count. */
int pfun_estimate_mealtimes(const double *t, const double *G, int N,
                            int n_meals, double *out_tM);
/* Fit the CMA model to (t, G) with fixed meal times via GSL nonlinear least
 * squares (Levenberg-Marquardt, params bounded by a sine transform).
 * The application must call gsl_set_error_handler_off() once during startup,
 * before calling this function; fitting does not modify GSL's process-global
 * error handler. Returns 0 on success. */
int pfun_cma_fit(const double *t, const double *G, int N, const double *tM,
                 int n_meals, pfun_fit_result *out);

#ifdef __cplusplus
}
#endif

#endif
