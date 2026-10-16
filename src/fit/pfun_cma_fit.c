/*
  pfun_cma_fit.c: CMA model curve fitting using GSL nonlinear least squares
  (gsl_multifit_nlinear, Levenberg-Marquardt). Bounded parameters
  (d, taup, taug, B, Cm, toff) are mapped from unconstrained values with a
  sine transform so the bounds from pfun-cma-model are always respected.
*/

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include <gsl/gsl_errno.h>
#include <gsl/gsl_multifit_nlinear.h>
#include <gsl/gsl_blas.h>
#include <gsl/gsl_vector.h>

#include "pfun_cma_engine/pfun_cma_cgm.h"
#include "pfun_cma_engine/pfun_cma_engine.h"

#define NP 6
static const double LB[NP] = {-12.0, 0.5, 0.1, 0.0, 0.0, -3.0};
static const double MID[NP] = {0.0, 1.0, 1.0, 0.05, 0.0, 0.0};
static const double UB[NP] = {14.0, 3.0, 3.0, 1.0, 2.0, 3.0};

typedef struct {
  const double *t, *y, *tM;
  int N, n_meals;
  double *buf; /* model scratch: 11 * N + n_meals * N */
} fit_ctx;

static double to_param(int k, double u) {
  return LB[k] + (UB[k] - LB[k]) * 0.5 * (sin(u) + 1.0);
}

static double to_unbounded(int k, double p) {
  double s = 2.0 * (p - LB[k]) / (UB[k] - LB[k]) - 1.0;
  if (s < -0.98) s = -0.98; /* avoid zero-gradient at the bounds */
  if (s > 0.98) s = 0.98;
  return asin(s);
}

static void eval_model(const fit_ctx *c, const double *p, double *G_out) {
  int N = c->N;
  double *b = c->buf;
  double *L = b, *m = b + N, *cc = b + 2 * N, *cm = b + 3 * N, *A = b + 4 * N,
         *a = b + 5 * N, *IS = b + 6 * N, *IE = b + 7 * N, *IEe = b + 8 * N,
         *sA = b + 9 * N, *g = b + 10 * N;
  run_cma_model(c->t, N, p[0], p[1], p[2], NULL, p[3], p[4], p[5], c->tM,
                c->n_meals, NULL, 0.0, NULL, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                L, m, cc, cm, A, a, IS, IE, IEe, sA, G_out, g);
}

static int resid(const gsl_vector *x, void *data, gsl_vector *f) {
  fit_ctx *c = data;
  double p[NP];
  for (int k = 0; k < NP; k++)
    p[k] = to_param(k, gsl_vector_get(x, k));
  double *G = malloc(c->N * sizeof(double));
  if (!G)
    return GSL_ENOMEM;
  eval_model(c, p, G);
  for (int i = 0; i < c->N; i++)
    gsl_vector_set(f, i, G[i] - c->y[i]);
  free(G);
  return GSL_SUCCESS;
}

int pfun_estimate_mealtimes(const double *t, const double *G, int N,
                            int n_meals, double *out_tM) {
  if (N < 3 || n_meals < 1)
    return 0;
  char *used = calloc(N, 1);
  if (!used)
    return 0;
  int found = 0;
  while (found < n_meals) {
    int best = -1;
    for (int i = 1; i < N - 1; i++) {
      if (used[i] || G[i] < G[i - 1] || G[i] < G[i + 1])
        continue;
      if (best < 0 || G[i] > G[best])
        best = i;
    }
    if (best < 0)
      break;
    out_tM[found++] = t[best];
    for (int i = 0; i < N; i++) /* suppress peaks within 2h (circular) */
      if (12.0 - fabs(fabs(t[i] - t[best]) - 12.0) < 2.0)
        used[i] = 1;
  }
  free(used);
  /* sort ascending */
  for (int i = 1; i < found; i++)
    for (int j = i; j > 0 && out_tM[j - 1] > out_tM[j]; j--) {
      double tmp = out_tM[j]; out_tM[j] = out_tM[j - 1]; out_tM[j - 1] = tmp;
    }
  return found;
}

int pfun_cma_fit(const double *t, const double *G, int N, const double *tM,
                 int n_meals, pfun_fit_result *out) {
  if (!t || !G || !tM || !out || N < NP + 1 || n_meals < 1)
    return -1;
  memset(out, 0, sizeof(*out));
  fit_ctx ctx = {t, G, tM, N, n_meals, NULL};
  ctx.buf = malloc(((size_t)11 + n_meals) * N * sizeof(double));
  if (!ctx.buf)
    return -1;

  gsl_multifit_nlinear_fdf fdf;
  fdf.f = resid;
  fdf.df = NULL; /* finite-difference Jacobian */
  fdf.fvv = NULL;
  fdf.n = N;
  fdf.p = NP;
  fdf.params = &ctx;

  gsl_multifit_nlinear_parameters fp = gsl_multifit_nlinear_default_parameters();
  gsl_multifit_nlinear_workspace *w =
      gsl_multifit_nlinear_alloc(gsl_multifit_nlinear_trust, &fp, N, NP);
  gsl_vector *x0 = gsl_vector_alloc(NP);
  if (!w || !x0) {
    free(ctx.buf);
    if (w) gsl_multifit_nlinear_free(w);
    if (x0) gsl_vector_free(x0);
    return -1;
  }
  for (int k = 0; k < NP; k++)
    gsl_vector_set(x0, k, to_unbounded(k, MID[k]));

  gsl_error_handler_t *old = gsl_set_error_handler_off();
  int info = 0;
  int status = gsl_multifit_nlinear_init(x0, &fdf, w);
  if (status == GSL_SUCCESS)
    status = gsl_multifit_nlinear_driver(200, 1e-8, 1e-8, 1e-8, NULL, NULL,
                                         &info, w);
  gsl_set_error_handler(old);

  gsl_vector *x = gsl_multifit_nlinear_position(w);
  for (int k = 0; k < NP; k++)
    out->params[k] = to_param(k, gsl_vector_get(x, k));
  double chisq;
  gsl_blas_ddot(gsl_multifit_nlinear_residual(w), gsl_multifit_nlinear_residual(w), &chisq);
  out->rss = chisq;
  out->rmse = sqrt(chisq / N);
  out->iterations = (int)gsl_multifit_nlinear_niter(w);
  out->status = status;

  gsl_multifit_nlinear_free(w);
  gsl_vector_free(x0);
  free(ctx.buf);
  return 0;
}
