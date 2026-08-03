/*
  pfun_cma_engine.h: Header definitions for the PFun CMA Model Engine
*/

#ifndef PFUN_CMA_ENGINE_H
#define PFUN_CMA_ENGINE_H

#ifdef __cplusplus
extern "C" {
#endif

// Low-level numerical methods
double exp_clipped(double x);
double expit(double x);
double calc_vdep_current(double v, double v1, double v2, double A, double B);
double E_pfun(double x);
double Light_pfun(double x);
double K_pfun(double x);
double meal_distr_pfun(double Cm, double t, double toff);

// Signal calculations (vectorized)
void calc_L(const double* t, int N, double d, double taup, double eps, double* out);
void calc_M(const double* t, int N, const double* L, double d, double eps, int* seed, double* out);
void calc_c(const double* t, int N, const double* L, const double* m, double d, double taup, double* out);
void calc_a(const double* t, int N, const double* c, const double* m, const double* L, double d, double taup, double eps, double* out);
void calc_I_S(int N, const double* c, const double* m, double* out);
void calc_I_E(int N, const double* a, const double* I_S, double* out);

/**
 * Normalize raw activity signal via sigmoid.
 *
 * @param t Time vector (size N, unused but kept for API symmetry)
 * @param N Number of time points
 * @param A_raw Raw activity input (size N, pre-normalized to [0,1]); if NULL, out_A is zeroed
 * @param k_A Sigmoid gain (steepness of transition)
 * @param A_thresh Activation threshold (half-maximal point)
 * @param out_A Output normalized activity signal (size N)
 */
void calc_A(const double* t, int N, const double* A_raw,
            double k_A, double A_thresh, double* out_A);

/**
 * Activity-modulated cortisol: c_mod[i] = c[i] * (1 + beta_A * A[i]).
 *
 * @param N Number of time points
 * @param c Cortisol vector (size N)
 * @param A Normalized activity signal (size N)
 * @param beta_A Cortisol amplification factor
 * @param out_c_mod Output modified cortisol (size N)
 */
void calc_c_mod(int N, const double* c, const double* A,
                double beta_A, double* out_c_mod);

/**
 * Post-activity insulin sensitization via recursive exponential filter.
 *
 * s_A[0] = 0
 * s_A[i] = s_A[i-1] * exp(-dt/tau_A) + eta_A * A[i-1] * (1 - exp(-dt/tau_A))
 * out_I_E_eff[i] = I_E[i] * (1 + s_A[i])
 *
 * Guard: if tau_A <= 0, s_A is zeroed and I_E is passed through unchanged.
 *
 * @param N Number of time points
 * @param I_E Extracellular insulin vector (size N)
 * @param A Normalized activity signal (size N)
 * @param t Time vector (size N, used to compute dt between steps)
 * @param eta_A Post-activity sensitization magnitude
 * @param tau_A Sensitization decay time (hours); must be > 0
 * @param out_I_E_eff Output sensitized insulin (size N)
 * @param out_s_A Output sensitization state (size N)
 */
void calc_I_E_eff(int N, const double* I_E, const double* A,
                  const double* t, double eta_A, double tau_A,
                  double* out_I_E_eff, double* out_s_A);

/**
 * Calculate post-prandial glucose dynamics with optional activity uptake.
 *
 * @param t Time vector (size N)
 * @param N Number of time points
 * @param I_E_eff Effective insulin vector (size N); pass I_E if no activity
 * @param A Normalized activity signal (size N); if NULL, activity uptake is skipped
 * @param tM Meal times vector (size n_meals)
 * @param n_meals Number of meals
 * @param taug Meal durations vector (size n_meals)
 * @param B Bias constant
 * @param Cm Cortisol temporal sensitivity coefficient
 * @param toff Meal-relative time offset
 * @param gamma_A Direct glucose uptake coefficient (ignored if A is NULL)
 * @param kappa_A Glucose uptake saturation constant (ignored if A is NULL)
 * @param include_bias_in_components Include bias in per-meal components
 * @param out_G_instant Output for instantaneous glucose (size N, optional, can be NULL)
 * @param out_g_components Output for per-meal components (size n_meals * N, row-major: meal x time, optional, can be NULL)
 */
void calc_G(const double* t, int N, const double* I_E_eff,
            const double* A,
            const double* tM, int n_meals,
            const double* taug, double B, double Cm, double toff,
            double gamma_A, double kappa_A,
            int include_bias_in_components,
            double* out_G_instant, double* out_g_components);

/**
 * Run the full CMA model with optional physical activity modeling.
 * All output buffers should be pre-allocated.
 *
 * When A_raw is NULL, all activity parameters are ignored and the model
 * produces output identical to the original (backward compatible).
 */
void run_cma_model(
    const double* t, int N,
    double d, double taup, double taug_val, // taug_val used if taug_vec is NULL
    const double* taug_vec,
    double B, double Cm, double toff,
    const double* tM, int n_meals,
    int* seed, double eps,
    const double* A_raw,              // raw activity input (NULL to disable activity)
    double k_A, double A_thresh,      // activity sigmoid params
    double gamma_A, double kappa_A,   // glucose uptake params
    double beta_A,                    // cortisol amplification
    double eta_A, double tau_A,       // post-activity sensitization
    double* out_L, double* out_m, double* out_c, double* out_c_mod,
    double* out_A,
    double* out_a, double* out_I_S, double* out_I_E,
    double* out_I_E_eff,
    double* out_s_A,
    double* out_G, double* out_g
);

#ifdef __cplusplus
}
#endif

#endif // PFUN_CMA_ENGINE_H
