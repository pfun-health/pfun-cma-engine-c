/*
  cgm_fit.c: ingest a CGM CSV and fit the CMA model (GSL nonlinear least squares).
  Usage: cgm_fit <cgm.csv> [N=1024] [n_meals=3]
         cgm_fit --ingest-only <cgm.csv> [N]   (prints t,G,value CSV)
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "pfun_cma_engine/pfun_cma_cgm.h"

int main(int argc, char **argv) {
  int ingest_only = argc > 1 && !strcmp(argv[1], "--ingest-only");
  int a = ingest_only ? 2 : 1;
  if (argc <= a) {
    fprintf(stderr, "usage: %s [--ingest-only] <cgm.csv> [N] [n_meals]\n", argv[0]);
    return 2;
  }
  int N = argc > a + 1 ? atoi(argv[a + 1]) : PFUN_CGM_DEFAULT_N;
  int n_meals = (!ingest_only && argc > a + 2) ? atoi(argv[a + 2]) : 3;
  pfun_cgm_data d;
  if (N < 8 || n_meals < 1 || n_meals > 16 || pfun_cgm_read_csv(argv[a], N, &d) != 0) {
    fprintf(stderr, "error: failed to ingest %s\n", argv[a]);
    return 1;
  }
  if (ingest_only) {
    printf("t,G,value\n");
    for (int i = 0; i < d.N; i++)
      printf("%.6f,%.6f,%.6f\n", d.t[i], d.G[i], d.value[i]);
    pfun_cgm_data_free(&d);
    return 0;
  }
  double tM[16];
  int nm = pfun_estimate_mealtimes(d.t, d.G, d.N, n_meals, tM);
  pfun_fit_result r;
  if (nm < 1 || pfun_cma_fit(d.t, d.G, d.N, tM, nm, &r) != 0) {
    fprintf(stderr, "error: fit failed\n");
    pfun_cgm_data_free(&d);
    return 1;
  }
  static const char *names[6] = {"d", "taup", "taug", "B", "Cm", "toff"};
  printf("units: %s\nmeal times:", d.mmoll ? "mmol/L" : "mg/dL");
  for (int i = 0; i < nm; i++) printf(" %.3f", tM[i]);
  printf("\n");
  for (int k = 0; k < 6; k++) printf("%s = %.6f\n", names[k], r.params[k]);
  printf("rmse = %.6f\niterations = %d\nstatus = %d\n", r.rmse, r.iterations, r.status);
  pfun_cgm_data_free(&d);
  return 0;
}
