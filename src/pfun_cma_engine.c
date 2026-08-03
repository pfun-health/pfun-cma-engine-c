/*
  pfun_cma_engine.c: Implementation of the PFun CMA Model Engine
*/

#include "pfun_cma_engine.h"
#include <float.h>
#include <math.h>
#include <stdlib.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Simple LCG for random noise
static double pfun_rand(int *seed) {
  if (seed == NULL)
    return 0.0;
  *seed = (*seed * 1103515245 + 12345) & 0x7fffffff;
  return (double)(*seed) / (double)0x7fffffff;
}

static double pfun_uniform(int *seed, double low, double high) {
  return low + (high - low) * pfun_rand(seed);
}

double exp_clipped(double x) {
  if (x < -709.0)
    x = -709.0;
  if (x > 709.0)
    x = 709.0;
  return exp(x);
}

double expit(double x) { return 1.0 / (1.0 + exp_clipped(-2.0 * x)); }

double calc_vdep_current(double v, double v1, double v2, double A, double B) {
  return A * expit(B * (v - v1) / v2);
}

double E_pfun(double x) { return 1.0 / (1.0 + exp_clipped(-2.0 * x)); }

double Light_pfun(double x) {
  return 2.0 / (1.0 + exp_clipped(2.0 * pow(x, 2.0)));
}

double K_pfun(double x) {
  if (x > 0.0) {
    return exp_clipped(-pow(log(2.0 * x), 2.0));
  } else {
    return 0.0;
  }
}

double meal_distr_pfun(double Cm, double t, double toff) {
  return pow(cos(2.0 * M_PI * Cm * (t + toff) / 24.0), 2.0);
}

void calc_L(const double *t, int N, double d, double taup, double eps,
            double *out) {
  for (int i = 0; i < N; i++) {
    out[i] = Light_pfun(0.025 * pow((t[i] - 12.0 - d), 2.0) / (eps + taup));
  }
}

void calc_M(const double *t, int N, const double *L, double d, double eps,
            int *seed, double *out) {
  for (int i = 0; i < N; i++) {
    double m_val =
      pow((1.0 - L[i]), 3.0) * pow(cos(-(t[i] - 3.0 - d) * M_PI / 24.0), 2.0);
    if (seed != NULL && *seed != 0) {
      m_val += pfun_uniform(seed, -eps, eps);
    }
    out[i] = m_val;
  }
}

void calc_c(const double *t, int N, const double *L, const double *m, double d,
            double taup, double *out) {
  for (int i = 0; i < N; i++) {
    out[i] = (4.9 / (1.0 + taup)) * M_PI * E_pfun(pow((L[i] - 0.88), 3.0)) *
      E_pfun(0.05 * (8.0 - t[i] + d)) * E_pfun(2.0 * pow(-m[i], 3.0));
  }
}

void calc_a(const double *t, int N, const double *c, const double *m,
            const double *L, double d, double taup, double eps, double *out) {
  for (int i = 0; i < N; i++) {
    double t_alt = 0.7 * (27.0 - t[i] + d);
    double L_alt =
      Light_pfun(0.025 * pow((t_alt - 12.0 - d), 2.0) / (eps + taup));
    out[i] = (E_pfun(pow((-c[i] * m[i]), 3.0)) +
              exp_clipped(-0.025 * pow((t[i] - 13.0 - d), 2.0)) * L_alt) /
      2.0;
  }
}

void calc_I_S(int N, const double *c, const double *m, double *out) {
  for (int i = 0; i < N; i++) {
    out[i] = 1.0 - 0.23 * c[i] - 0.97 * m[i];
  }
}

void calc_I_E(int N, const double *a, const double *I_S, double *out) {
  for (int i = 0; i < N; i++) {
    out[i] = a[i] * I_S[i];
  }
}

void calc_A(const double *t, int N, const double *A_raw, double k_A,
            double A_thresh, double *out_A) {
  (void)t; /* t parameter reserved for future use (e.g., time-varying threshold) */
  if (A_raw == NULL) {
    for (int i = 0; i < N; i++)
      out_A[i] = 0.0;
  } else {
    for (int i = 0; i < N; i++) {
      out_A[i] = 1.0 / (1.0 + exp_clipped(-2.0 * k_A * (A_raw[i] - A_thresh)));
    }
  }
}

void calc_c_mod(int N, const double *c, const double *A, double beta_A,
                double *out_c_mod) {
  for (int i = 0; i < N; i++) {
    out_c_mod[i] = c[i] * (1.0 + beta_A * A[i]);
  }
}

void calc_I_E_eff(int N, const double *I_E, const double *A, const double *t,
                  double eta_A, double tau_A, double *out_I_E_eff,
                  double *out_s_A) {
  /* Guard: tau_A <= 0 disables sensitization (passthrough) */
  if (tau_A <= 0.0) {
    for (int i = 0; i < N; i++) {
      out_s_A[i] = 0.0;
      out_I_E_eff[i] = I_E[i];
    }
    return;
  }

  out_s_A[0] = 0.0;
  out_I_E_eff[0] = I_E[0] * (1.0 + out_s_A[0]);

  for (int i = 1; i < N; i++) {
    double dt = t[i] - t[i - 1];
    double decay = exp_clipped(-dt / tau_A);
    out_s_A[i] = out_s_A[i - 1] * decay + eta_A * A[i - 1] * (1.0 - decay);
    out_I_E_eff[i] = I_E[i] * (1.0 + out_s_A[i]);
  }
}

void calc_G(const double *t, int N, const double *I_E_eff, const double *A,
            const double *tM, int n_meals, const double *taug, double B,
            double Cm, double toff, double gamma_A, double kappa_A,
            int include_bias_in_components, double *out_G_instant,
            double *out_g_components) {
  if (out_G_instant) {
    for (int i = 0; i < N; i++) {
      double bias = B * (1.0 + meal_distr_pfun(Cm, t[i], toff));
      /* Subtract contraction-mediated glucose uptake (Michaelis-Menten) */
      double delta_G_A = 0.0;
      if (A != NULL) {
        delta_G_A = gamma_A * A[i] / (1.0 + kappa_A * A[i]);
      }
      out_G_instant[i] = bias - delta_G_A;
    }
  }

  for (int j = 0; j < n_meals; j++) {
    double tm_j = tM[j];
    double taug_j = taug[j];
    double taug_j_sq = pow(taug_j, 2.0);

    for (int i = 0; i < N; i++) {
      double k_G = K_pfun((t[i] - tm_j) / taug_j_sq);
      double g_val = 1.3 * k_G / (1.0 + I_E_eff[i]);

      if (out_g_components) {
        out_g_components[j * N + i] = g_val;
        if (include_bias_in_components) {
          double bias = B * (1.0 + meal_distr_pfun(Cm, t[i], toff));
          double delta_G_A = 0.0;
          if (A != NULL) {
            delta_G_A = gamma_A * A[i] / (1.0 + kappa_A * A[i]);
          }
          out_g_components[j * N + i] += bias - delta_G_A;
        }
      }
      if (out_G_instant) {
        out_G_instant[i] += g_val;
      }
    }
  }
}

void run_cma_model(const double *t, int N, double d, double taup,
                   double taug_val, const double *taug_vec, double B, double Cm,
                   double toff, const double *tM, int n_meals, int *seed,
                   double eps, const double *A_raw, double k_A,
                   double A_thresh, double gamma_A, double kappa_A,
                   double beta_A, double eta_A, double tau_A, double *out_L,
                   double *out_m, double *out_c, double *out_c_mod,
                   double *out_A, double *out_a, double *out_I_S,
                   double *out_I_E, double *out_I_E_eff, double *out_s_A,
                   double *out_G, double *out_g) {
  /* Light */
  calc_L(t, N, d, taup, eps, out_L);

  /* Melatonin */
  calc_M(t, N, out_L, d, eps, seed, out_m);

  /* Cortisol */
  calc_c(t, N, out_L, out_m, d, taup, out_c);

  /* Activity signal (normalized) */
  calc_A(t, N, A_raw, k_A, A_thresh, out_A);

  /* Activity-modulated cortisol */
  calc_c_mod(N, out_c, out_A, beta_A, out_c_mod);

  /* Adiponectin (uses activity-modified cortisol) */
  calc_a(t, N, out_c_mod, out_m, out_L, d, taup, eps, out_a);

  /* Insulin secretion (uses activity-modified cortisol) */
  calc_I_S(N, out_c_mod, out_m, out_I_S);

  /* Extracellular insulin */
  calc_I_E(N, out_a, out_I_S, out_I_E);

  /* Post-activity insulin sensitization */
  calc_I_E_eff(N, out_I_E, out_A, t, eta_A, tau_A, out_I_E_eff, out_s_A);

  /* Meal duration vector */
  const double *actual_taug = taug_vec;
  double *temp_taug = NULL;
  if (actual_taug == NULL) {
    temp_taug = (double *)malloc(n_meals * sizeof(double));
    if (temp_taug == NULL)
      return; /* Allocation failed */
    for (int j = 0; j < n_meals; j++)
      temp_taug[j] = taug_val;
    actual_taug = temp_taug;
  }

  /* Glucose — uses I_E_eff and activity uptake; pass NULL for A when inactive */
  const double *act = (A_raw != NULL) ? out_A : NULL;
  calc_G(t, N, out_I_E_eff, act, tM, n_meals, actual_taug, B, Cm, toff,
         gamma_A, kappa_A, 0, out_G, out_g);

  if (temp_taug)
    free(temp_taug);
}
