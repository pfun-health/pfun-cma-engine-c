/*
  pfun_cma_cgm.c: CGM data ingestion (C port of pfun-cma-model format_data).
*/

#include <ctype.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "pfun_cma_engine/pfun_cma_cgm.h"

/* reference ranges: g0, g1, g_s */
static const double R_MGDL[3] = {70.0, 180.0, 90.0};
static const double R_MMOLL[3] = {3.7, 11.0, 4.77};

/**
 * Infer whether glucose readings are in mg/dL or mmol/L by comparing their
 * minimum, maximum, and mean with reference values for each unit.
 *
 * @param v Glucose readings to classify
 * @param n Number of readings
 * @return 1 for mmol/L, 0 for mg/dL, or 0 if no readings are usable
 */
int pfun_guess_glucose_units(const double *v, int n) {
  double mn = INFINITY, mx = -INFINITY, sum = 0.0;
  int cnt = 0;
  for (int i = 0; i < n; i++) {
    if (isnan(v[i]))
      continue;
    if (v[i] < mn) mn = v[i];
    if (v[i] > mx) mx = v[i];
    sum += v[i];
    cnt++;
  }
  if (cnt == 0)
    return 0;
  double gx[3] = {mn, mx, sum / cnt};
  double d0 = 0.0, d1 = 0.0;
  for (int k = 0; k < 3; k++) {
    d0 += (gx[k] - R_MGDL[k]) * (gx[k] - R_MGDL[k]);
    d1 += (gx[k] - R_MMOLL[k]) * (gx[k] - R_MMOLL[k]);
  }
  return d0 < d1 ? 0 : 1;
}

/**
 * Map a raw glucose reading to the model's normalized [0, 2] scale.
 *
 * @param G Raw glucose value
 * @param mmoll Nonzero if G is in mmol/L; otherwise G is in mg/dL
 * @return Normalized glucose value
 */
double pfun_normalize_glucose(double G, int mmoll) {
  const double *r = mmoll ? R_MMOLL : R_MGDL;
  double g0 = r[0], g1 = r[1], gs = r[2];
  double numer = 8.95 * pow(G - gs, 3.0) + pow(G - g0, 2.0) - pow(G - g1, 2.0);
  double x = 1e-4 * numer / (g1 - g0);
  return 2.0 / (1.0 + exp(-2.0 * x));
}

/**
 * Convert a Gregorian calendar date to days relative to 1970-01-01.
 *
 * @param y Year
 * @param m Month in [1, 12]
 * @param d Day of month
 * @return Signed number of days from the Unix epoch date
 */
static long days_from_civil(long y, unsigned m, unsigned d) {
  y -= m <= 2;
  long era = (y >= 0 ? y : y - 399) / 400;
  unsigned yoe = (unsigned)(y - era * 400);
  unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
  unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
  return era * 146097 + (long)doe - 719468;
}

/**
 * Parse an ISO 8601 local timestamp and its optional UTC offset.
 *
 * @param s Timestamp string
 * @param out_epoch Receives UTC seconds since 1970-01-01
 * @param out_tod Receives the timestamp's local time of day in decimal hours
 * @return 0 on success, or -1 if the timestamp is invalid
 */
int pfun_parse_iso8601(const char *s, double *out_epoch, double *out_tod) {
  int Y, M, D, h, m;
  double sec = 0.0;
  int n = 0;
  while (isspace((unsigned char)*s) || *s == '"')
    s++;
  if (sscanf(s, "%d-%d-%d%n", &Y, &M, &D, &n) != 3)
    return -1;
  s += n;
  if (*s != 'T' && *s != ' ')
    return -1;
  s++;
  if (sscanf(s, "%d:%d%n", &h, &m, &n) != 2)
    return -1;
  s += n;
  if (*s == ':') {
    char *end;
    sec = strtod(s + 1, &end);
    if (end == s + 1 || !isfinite(sec))
      return -1;
    s = end;
  }
  if (M < 1 || M > 12 || D < 1 || D > 31 || h < 0 || h > 23 || m < 0 || m > 59)
    return -1;
  double off = 0.0; /* offset of local from UTC, seconds */
  if (*s == '+' || *s == '-') {
    int oh = 0, om = 0, sign = (*s == '-') ? -1 : 1;
    s++;
    if (sscanf(s, "%2d:%2d", &oh, &om) < 1 &&
        sscanf(s, "%2d%2d", &oh, &om) < 1)
      return -1;
    off = sign * (oh * 3600.0 + om * 60.0);
  }
  double local = days_from_civil(Y, (unsigned)M, (unsigned)D) * 86400.0 +
                 h * 3600.0 + m * 60.0 + sec;
  *out_epoch = local - off;
  *out_tod = h + m / 60.0 + sec / 3600.0;
  return 0;
}

static const double *cmp_epoch;
/**
 * Compare sample indices by their corresponding epoch timestamps.
 *
 * @param a Pointer to the first sample index
 * @param b Pointer to the second sample index
 * @return Negative, zero, or positive according to timestamp ordering
 */
static int cmp_idx(const void *a, const void *b) {
  double x = cmp_epoch[*(const int *)a], y = cmp_epoch[*(const int *)b];
  return (x > y) - (x < y);
}

/**
 * Release all arrays owned by a CGM data result and reset its fields.
 *
 * @param d Result to release; NULL is ignored
 */
void pfun_cgm_data_free(pfun_cgm_data *d) {
  if (!d)
    return;
  free(d->t);
  free(d->G);
  free(d->value);
  free(d->time);
  memset(d, 0, sizeof(*d));
}

/**
 * Sort, normalize, bin, and interpolate raw CGM samples into a result.
 *
 * @param epoch UTC epoch seconds for each sample
 * @param tod Local time of day in decimal hours for each sample
 * @param value Raw glucose values
 * @param n Number of input samples
 * @param N Number of output bins
 * @param out Receives the allocated formatted data on success
 * @return 0 on success, or -1 on invalid input or allocation/format failure
 */
int pfun_cgm_format(const double *epoch, const double *tod, const double *value,
                    int n, int N, pfun_cgm_data *out) {
  if (!epoch || !tod || !value || !out || n < 2 || N < 2)
    return -1;
  memset(out, 0, sizeof(*out));
  int *ix = malloc(n * sizeof(int));
  double *Graw = malloc(n * sizeof(double));
  double *local_tod = malloc(n * sizeof(double));
  double *sums[4], *cnt = calloc(N, sizeof(double));
  for (int k = 0; k < 4; k++)
    sums[k] = calloc(N, sizeof(double));
  out->t = malloc(N * sizeof(double));
  out->G = malloc(N * sizeof(double));
  out->value = malloc(N * sizeof(double));
  out->time = malloc(N * sizeof(double));
  int ok = ix && Graw && local_tod && cnt && sums[0] && sums[1] && sums[2] &&
           sums[3] && out->t && out->G && out->value && out->time;
  if (!ok)
    goto fail;

  out->mmoll = pfun_guess_glucose_units(value, n);
  for (int i = 0; i < n; i++) {
    ix[i] = i;
    Graw[i] = isnan(value[i]) ? NAN : pfun_normalize_glucose(value[i], out->mmoll);
  }
  cmp_epoch = epoch;
  qsort(ix, n, sizeof(int), cmp_idx);
  int first_sample = ix[0];
  local_tod[first_sample] = tod[first_sample];
  for (int k = 1; k < n; k++) {
    int previous = ix[k - 1], i = ix[k];
    double elapsed = (epoch[i] - epoch[previous]) / 3600.0;
    double days = round((local_tod[previous] + elapsed - tod[i]) / 24.0);
    local_tod[i] = tod[i] + days * 24.0;
  }

  /* downsample: N bins of equal width spanning [tmin, tmax], bin means */
  double t0 = epoch[ix[0]], t1 = epoch[ix[n - 1]];
  double width = (t1 - t0) / (N - 1);
  if (!(width > 0.0))
    goto fail;
  for (int k = 0; k < n; k++) {
    int i = ix[k];
    if (isnan(Graw[i]))
      continue;
    int b = (int)floor((epoch[i] - t0) / width);
    if (b >= N) b = N - 1;
    if (b < 0) b = 0;
    cnt[b] += 1.0;
    sums[0][b] += local_tod[i];
    sums[1][b] += Graw[i];
    sums[2][b] += value[i];
    sums[3][b] += epoch[i];
  }
  /* bin means; empty bins -> NaN */
  int first = -1;
  for (int b = 0; b < N; b++) {
    if (cnt[b] > 0.0) {
      out->t[b] = sums[0][b] / cnt[b];
      out->G[b] = sums[1][b] / cnt[b];
      out->value[b] = sums[2][b] / cnt[b];
      out->time[b] = sums[3][b] / cnt[b];
      if (first < 0) first = b;
    } else {
      out->t[b] = out->G[b] = out->value[b] = NAN;
      out->time[b] = t0 + b * width;
    }
  }
  if (first < 0)
    goto fail;
  /* linear interpolation of missing bins (constant extrapolation at edges,
   * like numpy.interp), over bin-center time (epoch) */
  double *cols[3] = {out->t, out->G, out->value};
  for (int c = 0; c < 3; c++) {
    double *v = cols[c];
    int prev = -1;
    for (int b = 0; b < N; b++) {
      if (!isnan(v[b])) {
        if (prev < 0) {
          for (int j = 0; j < b; j++) v[j] = v[b];
        } else if (b - prev > 1) {
          for (int j = prev + 1; j < b; j++) {
            double f = (double)(j - prev) / (double)(b - prev);
            v[j] = v[prev] + f * (v[b] - v[prev]);
          }
        }
        prev = b;
      }
    }
    for (int j = prev + 1; j < N; j++) v[j] = v[prev];
  }
  for (int b = 0; b < N; b++) {
    out->t[b] = fmod(out->t[b], 24.0);
    if (out->t[b] < 0.0)
      out->t[b] += 24.0;
  }
  free(ix); free(Graw); free(local_tod); free(cnt);
  for (int k = 0; k < 4; k++) free(sums[k]);
  out->N = N;
  return 0;
fail:
  free(ix); free(Graw); free(local_tod); free(cnt);
  for (int k = 0; k < 4; k++) free(sums[k]);
  pfun_cgm_data_free(out);
  return -1;
}

/**
 * Split a CSV line in place into fields, supporting simple quoted fields.
 *
 * @param line Input line, modified by inserting null terminators
 * @param f Receives pointers to the fields
 * @param max Maximum number of field pointers to write
 * @return Number of fields written
 */
static int split_csv(char *line, char **f, int max) {
  int n = 0;
  char *p = line;
  while (n < max) {
    if (*p == '"') {
      f[n++] = ++p;
      while (*p && *p != '"') p++;
      if (*p == '"') *p++ = 0;
      while (*p && *p != ',') p++;
    } else {
      f[n++] = p;
      while (*p && *p != ',' && *p != '\n' && *p != '\r') p++;
    }
    if (*p == ',') { *p++ = 0; continue; }
    *p = 0;
    break;
  }
  return n;
}

/**
 * Read timestamp and glucose columns from a CSV and format the samples.
 *
 * @param path CSV file path
 * @param N Number of output bins
 * @param out Receives the allocated formatted data on success
 * @return 0 on success, or -1 if the file, columns, data, or formatting fail
 */
int pfun_cgm_read_csv(const char *path, int N, pfun_cgm_data *out) {
  FILE *fp = fopen(path, "r");
  if (!fp)
    return -1;
  char line[4096];
  char *f[64];
  int tcol = -1, localcol = -1, vcol = -1, ncols;
  static const char *tnames[] = {"systemTime", "ts_utc", "time", "ts_local",
                                 "displayTime"};
  static const char *local_names[] = {"ts_local", "displayTime"};
  static const char *vnames[] = {"value", "sg"};
  if (!fgets(line, sizeof line, fp)) { fclose(fp); return -1; }
  ncols = split_csv(line, f, 64);
  for (int k = 0; k < 5 && tcol < 0; k++)
    for (int c = 0; c < ncols; c++)
      if (!strcmp(f[c], tnames[k])) { tcol = c; break; }
  for (int k = 0; k < 2 && localcol < 0; k++)
    for (int c = 0; c < ncols; c++)
      if (!strcmp(f[c], local_names[k])) { localcol = c; break; }
  for (int k = 0; k < 2 && vcol < 0; k++)
    for (int c = 0; c < ncols; c++)
      if (!strcmp(f[c], vnames[k])) { vcol = c; break; }
  if (tcol < 0 || vcol < 0) { fclose(fp); return -1; }

  int cap = 1024, n = 0;
  double *ep = malloc(cap * sizeof(double)), *td = malloc(cap * sizeof(double)),
         *vl = malloc(cap * sizeof(double));
  while (ep && td && vl && fgets(line, sizeof line, fp)) {
    int nf = split_csv(line, f, 64);
    if (nf <= tcol || nf <= vcol)
      continue;
    double e, t, v;
    char *end;
    if (pfun_parse_iso8601(f[tcol], &e, &t) != 0)
      continue;
    if (localcol >= 0 && localcol != tcol) {
      double local_epoch;
      if (nf <= localcol ||
          pfun_parse_iso8601(f[localcol], &local_epoch, &t) != 0)
        continue;
    }
    v = strtod(f[vcol], &end);
    if (end == f[vcol])
      v = NAN;
    if (n == cap) {
      cap *= 2;
      double *a = realloc(ep, cap * sizeof(double));
      double *b = realloc(td, cap * sizeof(double));
      double *c = realloc(vl, cap * sizeof(double));
      if (!a || !b || !c) { free(a ? a : ep); free(b ? b : td); free(c ? c : vl); fclose(fp); return -1; }
      ep = a; td = b; vl = c;
    }
    ep[n] = e; td[n] = t; vl[n] = v; n++;
  }
  fclose(fp);
  int rc = (ep && td && vl) ? pfun_cgm_format(ep, td, vl, n, N, out) : -1;
  free(ep); free(td); free(vl);
  return rc;
}
