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
  CHECK(pfun_parse_iso8601("2024-03-05T08:30:00+0530", &e2, &tod) == 0);
  double e3;
  CHECK(pfun_parse_iso8601("2024-03-05T03:00:00Z", &e3, &tod) == 0);
  CHECK(fabs(e2 - e3) < 1e-6);
  CHECK(pfun_parse_iso8601("2024-03-05T12:00:nan", &e2, &tod) != 0);
  CHECK(pfun_parse_iso8601("2024-03-05T12:00:inf", &e2, &tod) != 0);
  double v[3] = {100, 150, 90}, m[3] = {5.0, 9.0, 5.5};
  CHECK(pfun_guess_glucose_units(v, 3) == 0);
  CHECK(pfun_guess_glucose_units(m, 3) == 1);
  pfun_cgm_data d;

  double peak_t[3] = {4.0, 5.0, 6.0}, peak_G[3] = {0.5, 1.0, 0.5};
  double meal_t;
  CHECK(pfun_estimate_mealtimes(peak_t, peak_G, 3, 1, &meal_t) == 1);
  CHECK(fabs(meal_t - 4.0) < 1e-9);
  peak_t[1] = 0.5;
  CHECK(pfun_estimate_mealtimes(peak_t, peak_G, 3, 1, &meal_t) == 1);
  CHECK(fabs(meal_t) < 1e-9);

  double overnight_epoch[2] = {0.0, 1200.0};
  double overnight_tod[2] = {23.8333333333, 0.1666666667};
  double overnight_value[2] = {100.0, 110.0};
  CHECK(pfun_cgm_format(overnight_epoch, overnight_tod, overnight_value, 2,
                        5, &d) == 0);
  CHECK(fabs(d.t[1] - 23.9166666667) < 1e-6);
  CHECK(fabs(d.t[2]) < 1e-6);
  CHECK(fabs(d.t[3] - 0.0833333333) < 1e-6);
  pfun_cgm_data_free(&d);
  double unsorted_epoch[2] = {1200.0, 0.0};
  double unsorted_tod[2] = {0.1666666667, 23.8333333333};
  CHECK(pfun_cgm_format(unsorted_epoch, unsorted_tod, overnight_value, 2, 5,
                        &d) == 0);
  CHECK(fabs(d.t[1] - 23.9166666667) < 1e-6);
  CHECK(fabs(d.t[2]) < 1e-6);
  CHECK(fabs(d.t[3] - 0.0833333333) < 1e-6);
  pfun_cgm_data_free(&d);
  overnight_epoch[1] += 86400.0;
  CHECK(pfun_cgm_format(overnight_epoch, overnight_tod, overnight_value, 2,
                        5, &d) == 0);
  CHECK(fabs(d.t[1] - 5.9166666667) < 1e-6);
  CHECK(fabs(d.t[3] - 18.0833333333) < 1e-6);
  pfun_cgm_data_free(&d);

  CHECK(pfun_cgm_read_csv("tests/data/sample_cgm_local.csv", 3, &d) == 0);
  CHECK(fabs(d.t[0] - 8.0) < 1e-6);
  CHECK(fabs(d.t[2] - 8.1666666667) < 1e-6);
  pfun_cgm_data_free(&d);

  CHECK(pfun_cgm_read_csv("tests/data/sample_cgm_display_time.csv", 3, &d) == 0);
  CHECK(fabs(d.t[0] - 8.0) < 1e-6);
  CHECK(fabs(d.t[2] - 8.1666666667) < 1e-6);
  pfun_cgm_data_free(&d);

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
