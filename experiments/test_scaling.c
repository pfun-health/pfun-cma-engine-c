/*
 * test_scaling.c: Standalone test to report numerical ranges of the CMA model signals.
 * Compile:
 *   gcc -o test_scaling test_scaling.c src/pfun_cma_engine.c -lm
 * Run:
 *   ./test_scaling
 */

#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "src/pfun_cma_engine.h"

#define N_PTS 1441    /* 24h * 60min + 1 */
#define N_MEALS 3

static double t_vals[N_PTS];

static void build_time_vector(void) {
    for (int i = 0; i < N_PTS; i++) {
        t_vals[i] = (24.0 * i) / (double)(N_PTS - 1);  /* 0..24 */
    }
}

static void min_mean_max(const double *x, int N, double *pmin, double *pmean, double *pmax) {
    double mn = x[0], mx = x[0];
    double sum = 0.0;
    for (int i = 0; i < N; i++) {
        double v = x[i];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
        sum += v;
    }
    *pmin  = mn;
    *pmean = sum / (double)N;
    *pmax  = mx;
}

static double interp_value(const double *t, const double *x, int N, double t_target) {
    /* linear interpolation */
    if (t_target <= t[0])  return x[0];
    if (t_target >= t[N-1]) return x[N-1];
    int i = 0;
    while (i < N-1 && t[i+1] < t_target) i++;
    double f = (t_target - t[i]) / (t[i+1] - t[i]);
    return x[i] + f * (x[i+1] - x[i]);
}

static void run_and_report(const char *label, double taup) {
    double *L  = (double *)malloc(N_PTS * sizeof(double));
    double *m  = (double *)malloc(N_PTS * sizeof(double));
    double *c  = (double *)malloc(N_PTS * sizeof(double));
    double *a  = (double *)malloc(N_PTS * sizeof(double));
    double *IS = (double *)malloc(N_PTS * sizeof(double));
    double *IE = (double *)malloc(N_PTS * sizeof(double));
    double *G  = (double *)malloc(N_PTS * sizeof(double));
    double *g  = (double *)malloc(N_PTS * N_MEALS * sizeof(double));

    if (!L || !m || !c || !a || !IS || !IE || !G || !g) {
        fprintf(stderr, "Allocation failed\n");
        exit(1);
    }

    double d         = 0.0;
    double taug_val  = 4.0;
    double B         = 0.05;
    double Cm        = 0.0;
    double toff      = 0.0;
    double tM[]      = {7.0, 11.0, 17.5};
    double eps       = 1e-18;

    run_cma_model(t_vals, N_PTS,
                  d, taup, taug_val, NULL,
                  B, Cm, toff,
                  tM, N_MEALS,
                  NULL, eps,
                  L, m, c, a, IS, IE, G, g);

    printf("\n=== %s (taup = %.1f) ===\n\n", label, taup);

    const char *names[] = {"L", "m", "c", "a", "I_S", "I_E", "G"};
    double *bufs[]      = {L, m, c, a, IS, IE, G};

    for (int s = 0; s < 7; s++) {
        double mn, mean, mx;
        min_mean_max(bufs[s], N_PTS, &mn, &mean, &mx);
        printf("  %-4s  min=% .6e  mean=% .6e  max=% .6e\n", names[s], mn, mean, mx);
    }

    printf("\n  G and I_E at meal times:\n");
    for (int j = 0; j < N_MEALS; j++) {
        double tm   = tM[j];
        double g_at = interp_value(t_vals, G,  N_PTS, tm);
        double ie_at= interp_value(t_vals, IE, N_PTS, tm);
        printf("    t=%.1f:  G=% .6e  I_E=% .6e\n", tm, g_at, ie_at);
    }

    free(L); free(m); free(c); free(a);
    free(IS); free(IE); free(G); free(g);
}

int main(void) {
    build_time_vector();

    run_and_report("Run 1", 0.5);
    run_and_report("Run 2", 0.0);

    return 0;
}
