/* test_cgm.c: CGM ingestion + GSL curve fit test. Run via `make test-cgm`. */
#include <math.h>
#include <stdio.h>

#include <gsl/gsl_errno.h>

#include "pfun_cma_engine/pfun_cma_cgm.h"

#define CHECK(c) do { if (!(c)) { printf("FAIL: %s (line %d)\n", #c, __LINE__); return 1; } } while (0)

int main(void) {
  gsl_set_error_handler_off();
  double e, tod;
  CHECK(pfun_parse_iso8601("2024-03-05T08:30:00-05:00", &e, &tod) == 0);
  CHECK(fabs(tod - 8.5) < 1e-9);
  double e2;
  CHECK(pfun_parse_iso8601("2024-03-05T13:30:00Z", &e2, &tod) == 0);
  CHECK(fabs(e - e2) < 1e-6);
  double v[3] = {100, 150, 90}, m[3] = {5.0, 9.0, 5.5};
  CHECK(pfun_guess_glucose_units(v, 3) == 0);
  CHECK(pfun_guess_glucose_units(m, 3) == 1);

  pfun_cgm_data d;
  CHECK(pfun_cgm_read_csv("tests/data/sample_cgm.csv", 256, &d) == 0);
  CHECK(d.N == 256);
  for (int i = 0; i < d.N; i++) {
    CHECK(!isnan(d.t[i]) && !isnan(d.G[i]));
    CHECK(d.G[i] >= 0.0 && d.G[i] <= 2.0);
  }
  double tM[3];
  int nm = pfun_estimate_mealtimes(d.t, d.G, d.N, 3, tM);
  CHECK(nm == 3);
  pfun_fit_result r;
  CHECK(pfun_cma_fit(d.t, d.G, d.N, tM, nm, &r) == 0);
  printf("rmse=%.4f iters=%d status=%d\n", r.rmse, r.iterations, r.status);
  CHECK(isfinite(r.rmse) && r.rmse < 0.5);
  pfun_cgm_data_free(&d);
  printf("test_cgm OK\n");
  return 0;
}
