/**
 * @file demo.c
 * @brief Interactive TTY demonstration and ASCII export for PFun CMA engine.
 *
 * Demonstrates the Circadian-Meal-Activity (CMA) physiological model using
 * either an interactive terminal UI built with Nuklear and half-block graphics
 * (term.h/term.c), or headless ASCII chart export to standard output and
 * Markdown files (--ascii, --save). Provides real-time parameter tuning for
 * circadian phase shift, photoperiod, meal timing and sensitivity, activity
 * modulation, and stochastic noise.
 */

#define NK_INCLUDE_FIXED_TYPES
#define NK_INCLUDE_DEFAULT_ALLOCATOR
#define NK_INCLUDE_STANDARD_IO
#define NK_IMPLEMENTATION
#include "nuklear.h"

#include <math.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <poll.h>

#include "pfun_cma_engine.h"
#include "term.h"

/** Maximum number of simulation time points supported by results buffers. */
#define MAXPTS 512

/** Number of discrete meals modeled across the 24-hour cycle. */
#define NMEALS 3

/** Total number of observable model variables in the CMA engine. */
#define NVAR 12

/** Small positive epsilon constant used in numerical calculations. */
#define EPS 1e-18

/** String identifiers for all 12 model output variables. */
static const char *VAR_NAMES[NVAR] = {
    "G", "I_E", "I_E_eff", "L", "m", "c", "c_mod", "A", "s_A", "a", "I_S", "g"};

/**
 * @struct scenario
 * @brief Simulation scenario parameters for the CMA physiological model.
 */
typedef struct {
  double d;          /**< Circadian phase shift parameter (hours). */
  double taup;       /**< Circadian photoperiod parameter (hours). */
  double taug_val;   /**< Characteristic postprandial glucose clearance time constant (hours). */
  double B;          /**< Baseline bias constant in glucose dynamics. */
  double Cm;         /**< Cortisol temporal sensitivity coefficient on meal response. */
  double toff;       /**< Meal-relative time offset (hours). */
  double tM[NMEALS]; /**< Meal ingestion times across the 24-hour cycle (hours). */
  double N;          /**< Number of simulation time points. */
  double act_on;     /**< Non-zero to enable physical activity profile. */
  double A_amp;      /**< Amplitude scaling for physical activity peaks. */
  double k_A;        /**< Sigmoid gain (steepness) for activity normalization. */
  double A_thresh;   /**< Activation threshold (half-maximal point) for activity. */
  double gamma_A;    /**< Direct contraction-mediated glucose uptake coefficient. */
  double kappa_A;    /**< Direct glucose uptake saturation constant. */
  double beta_A;     /**< Cortisol amplification factor under physical exertion. */
  double eta_A;      /**< Magnitude of post-activity insulin sensitization. */
  double tau_A;      /**< Exponential decay time constant for post-activity sensitization (hours). */
  double noise;      /**< Non-zero to enable stochastic noise in simulation. */
} scenario;

/**
 * @struct cparam
 * @brief Interactive parameter descriptor binding a scenario variable to the TUI.
 */
typedef struct {
  const char *name; /**< Parameter display name in the TUI panel. */
  double *val;      /**< Pointer to the underlying variable in the active scenario. */
  double lo;        /**< Lower bound for adjustment. */
  double hi;        /**< Upper bound for adjustment. */
  double step;      /**< Increment/decrement step size. */
  int is_bool;      /**< 1 if parameter is a boolean toggle; 0 for continuous numeric. */
} cparam;

/**
 * @struct results
 * @brief Output trajectory buffers for all CMA model state variables.
 */
typedef struct {
  double L[MAXPTS];          /**< Light signal / photic drive trajectory. */
  double m[MAXPTS];          /**< Melatonin trajectory. */
  double c[MAXPTS];          /**< Baseline cortisol trajectory. */
  double c_mod[MAXPTS];      /**< Activity-modulated cortisol trajectory. */
  double A[MAXPTS];          /**< Normalized activity signal. */
  double a[MAXPTS];          /**< Circadian arousal / sleep-wake drive. */
  double I_S[MAXPTS];        /**< Stored / endogenous insulin drive. */
  double I_E[MAXPTS];        /**< Extracellular insulin trajectory. */
  double I_E_eff[MAXPTS];    /**< Effective sensitized insulin trajectory. */
  double s_A[MAXPTS];        /**< Post-activity insulin sensitization state. */
  double G[MAXPTS];          /**< Instantaneous blood glucose trajectory. */
  double g[NMEALS * MAXPTS]; /**< Per-meal postprandial glucose components (NMEALS x N). */
  double t[MAXPTS];          /**< Simulation time points vector (hours [0..24]). */
} results;

/**
 * @struct ui
 * @brief Interactive terminal user interface state.
 */
typedef struct {
  int sel;    /**< Index of selected model variable to plot [0..NVAR-1]. */
  int panel;  /**< Active panel index (0 = variable list, 1 = parameter editor). */
  int pfocus; /**< Index of focused parameter in parameter panel [0..NPARAM-1]. */
  int poff;   /**< Vertical scroll offset in parameter panel. */
  int help;   /**< 1 if help modal overlay is visible; 0 otherwise. */
  int quit;   /**< 1 to exit application event loop; 0 to continue. */
  int redraw; /**< 1 if screen needs re-rasterizing and flushing; 0 otherwise. */
  int lw;     /**< Left sidebar width in virtual pixels. */
  int hdr;    /**< Header bar height in virtual pixels. */
  int pl_x;   /**< Plot area left X coordinate. */
  int pl_y;   /**< Plot area top Y coordinate. */
  int pl_w;   /**< Plot area width in virtual pixels. */
  int pl_h;   /**< Plot area height in virtual pixels. */
  int pp_x;   /**< Parameter panel left X coordinate. */
  int pp_y;   /**< Parameter panel top Y coordinate. */
  int pp_w;   /**< Parameter panel width in virtual pixels. */
  int pp_h;   /**< Parameter panel height in virtual pixels. */
} ui;

/** User font configuration used by Nuklear for text rendering metrics. */
static struct nk_user_font ui_font;

/**
 * @brief Safe formatted string append with buffer capacity and write position tracking.
 *
 * Formats a string into out at offset *pos, ensuring no writes occur past cap.
 * Advances *pos by the number of characters written.
 *
 * @param out Destination character buffer.
 * @param cap Total capacity of out.
 * @param pos In/out pointer tracking current insertion offset in out.
 * @param fmt Printf-style format string.
 * @param ... Variadic arguments matching format specifiers.
 */
static void appendf(char *out, size_t cap, size_t *pos, const char *fmt, ...) {
  if (*pos >= cap)
    return;

  va_list ap;
  va_start(ap, fmt);
  int wrote = vsnprintf(out + *pos, cap - *pos, fmt, ap);
  va_end(ap);

  if (wrote < 0) {
    return;
  }

  size_t avail = cap - *pos;
  size_t wrote_sz = (size_t)wrote;
  if (wrote_sz >= avail) {
    *pos = cap;
    return;
  }
  *pos += wrote_sz;
}

/**
 * @brief Retrieve pointer to results array corresponding to variable index.
 *
 * Maps variable index [0..10] to the corresponding array in results.
 * Returns NULL for index 11 ('g', which is a multi-meal matrix).
 *
 * @param r Pointer to simulation results.
 * @param v Variable index [0..NVAR-1].
 * @return Pointer to variable time series array, or NULL if multi-series/invalid.
 */
static double *res_var(results *r, int v) {
  switch (v) {
  case 0:
    return r->G;
  case 1:
    return r->I_E;
  case 2:
    return r->I_E_eff;
  case 3:
    return r->L;
  case 4:
    return r->m;
  case 5:
    return r->c;
  case 6:
    return r->c_mod;
  case 7:
    return r->A;
  case 8:
    return r->s_A;
  case 9:
    return r->a;
  case 10:
    return r->I_S;
  default:
    return NULL;
  }
}

/**
 * @brief Nuklear font width callback for monospace terminal font.
 *
 * Treats each character as 1 pixel wide in virtual screen coordinates.
 *
 * @param h User font handle (unused).
 * @param height Font height (unused).
 * @param text Text string.
 * @param len String length in bytes.
 * @return Computed width in virtual pixels (equals len).
 */
static float font_width(nk_handle h, float height, const char *text, int len) {
  (void)h;
  (void)height;
  (void)text;
  return (float)len;
}

/**
 * @brief Initialize a scenario with default baseline physiological parameters.
 *
 * Configures default 24-hour cycle with 3 meals (breakfast at 7.0h, lunch at 11.0h,
 * dinner at 17.5h), baseline glucose dynamics, and default exercise response constants.
 *
 * @param sc Pointer to scenario struct to populate.
 * @param npts Number of simulation time points.
 */
static void scenario_default(scenario *sc, double npts) {
  sc->d = 1.0;
  sc->taup = 1.2;
  sc->taug_val = 1.0;
  sc->B = 0.05;
  sc->Cm = 0.0;
  sc->toff = 0.0;
  sc->tM[0] = 7.0;
  sc->tM[1] = 11.0;
  sc->tM[2] = 17.5;
  sc->N = npts;
  sc->act_on = 0;
  sc->A_amp = 0.4;
  sc->k_A = 5.0;
  sc->A_thresh = 0.3;
  sc->gamma_A = 0.15;
  sc->kappa_A = 0.5;
  sc->beta_A = 0.20;
  sc->eta_A = 0.40;
  sc->tau_A = 2.0;
  sc->noise = 0;
}

/** Number of interactive parameters available in the TUI parameter panel. */
#define NPARAM 20

/**
 * @brief Build parameter descriptors array bound to scenario fields.
 *
 * Configures names, pointers, bounds, step sizes, and boolean flags for all
 * 20 tunable parameters in the interactive interface.
 *
 * @param sc Pointer to active scenario struct.
 * @param p Output array of NPARAM cparam descriptors.
 */
static void scenario_params(scenario *sc, cparam *p) {
  p[0] = (cparam){"d", &sc->d, 0.0, 4.0, 0.1, 0};
  p[1] = (cparam){"taup", &sc->taup, 0.0, 4.0, 0.1, 0};
  p[2] = (cparam){"taug_val", &sc->taug_val, 0.5, 8.0, 0.25, 0};
  p[3] = (cparam){"B", &sc->B, 0.01, 0.5, 0.01, 0};
  p[4] = (cparam){"Cm", &sc->Cm, 0.0, 1.0, 0.05, 0};
  p[5] = (cparam){"toff", &sc->toff, 0.0, 2.0, 0.1, 0};
  p[6] = (cparam){"tM[0]", &sc->tM[0], 0.0, 24.0, 0.5, 0};
  p[7] = (cparam){"tM[1]", &sc->tM[1], 0.0, 24.0, 0.5, 0};
  p[8] = (cparam){"tM[2]", &sc->tM[2], 0.0, 24.0, 0.5, 0};
  p[9] = (cparam){"N pts", &sc->N, 97.0, (double)MAXPTS, 24.0, 0};
  p[10] = (cparam){"activity", &sc->act_on, 0.0, 1.0, 1.0, 0};
  p[11] = (cparam){"A_amp", &sc->A_amp, 0.0, 2.0, 0.05, 0};
  p[12] = (cparam){"k_A", &sc->k_A, 0.5, 20.0, 0.5, 0};
  p[13] = (cparam){"A_thresh", &sc->A_thresh, 0.0, 1.0, 0.05, 0};
  p[14] = (cparam){"gamma_A", &sc->gamma_A, 0.0, 1.0, 0.05, 0};
  p[15] = (cparam){"kappa_A", &sc->kappa_A, 0.0, 3.0, 0.1, 0};
  p[16] = (cparam){"beta_A", &sc->beta_A, 0.0, 2.0, 0.05, 0};
  p[17] = (cparam){"eta_A", &sc->eta_A, 0.0, 2.0, 0.05, 0};
  p[18] = (cparam){"tau_A", &sc->tau_A, 0.1, 6.0, 0.1, 0};
  p[19] = (cparam){"noise", &sc->noise, 0.0, 1.0, 1.0, 0};
}

/**
 * @brief Execute the CMA physiological model simulation for a given scenario.
 *
 * Populates time vector t linearly from 0 to 24 hours. If physical activity is
 * enabled (act_on), synthesizes a bimodal Gaussian exercise profile (morning run
 * around 8h, late afternoon run around 17h). Passes all parameters to the C
 * engine function run_cma_model to compute trajectories for all variables.
 *
 * @param sc Pointer to configured simulation scenario.
 * @param r Output results struct receiving computed state variable trajectories.
 */
static void scenario_run(const scenario *sc, results *r) {
  int N = (int)sc->N;
  if (N < 2)
    N = 2;
  for (int i = 0; i < N; i++)
    r->t[i] = 24.0 * (double)i / (double)(N - 1);

  double A_raw[MAXPTS];
  memset(A_raw, 0, sizeof(A_raw));
  if (sc->act_on) {
    for (int i = 0; i < N; i++) {
      double x = r->t[i];
      A_raw[i] = sc->A_amp * (exp(-pow((x - 8.0) / 1.5, 2.0)) +
                              exp(-pow((x - 17.0) / 2.0, 2.0)));
    }
  }
  const double *araw = sc->act_on ? A_raw : NULL;

  int seed = 12345;
  int *seedptr = sc->noise ? &seed : NULL;

  run_cma_model(r->t, N, sc->d, sc->taup, sc->taug_val, NULL, sc->B, sc->Cm,
                sc->toff, sc->tM, NMEALS, seedptr, EPS, araw, sc->k_A,
                sc->A_thresh, sc->gamma_A, sc->kappa_A, sc->beta_A, sc->eta_A,
                sc->tau_A, r->L, r->m, r->c, r->c_mod, r->A, r->a, r->I_S,
                r->I_E, r->I_E_eff, r->s_A, r->G, r->g);
}

/**
 * @brief Render a single trajectory as a monospace ASCII chart with axes.
 *
 * Generates an ASCII plot with labeled Y-axis values, coordinate frame borders,
 * interpolated points, and centered time values on the X-axis. Appends the
 * formatted chart to out.
 *
 * @param title Chart header title (variable name).
 * @param vals Array of data values (size N).
 * @param t Array of time coordinates (size N).
 * @param N Number of data points.
 * @param W Plot width in characters.
 * @param H Plot height in characters.
 * @param out Destination text buffer.
 * @param cap Maximum capacity of destination text buffer.
 */
static void ascii_chart(const char *title, const double *vals, const double *t,
                        int N, int W, int H, char *out, size_t cap) {
  double vmin = vals[0], vmax = vals[0], tmin = t[0], tmax = t[N - 1];
  for (int i = 1; i < N; i++) {
    if (vals[i] < vmin)
      vmin = vals[i];
    if (vals[i] > vmax)
      vmax = vals[i];
  }
  double span = (vmax - vmin) ? (vmax - vmin) : 1.0;
  double tspan = (tmax - tmin) ? (tmax - tmin) : 1.0;

  size_t pos = 0;
  appendf(out, cap, &pos, "%s  (t: %g .. %g, value: %g .. %g)\n", title, tmin,
          tmax, vmin, vmax);

  char cells[4096];
  if ((size_t)H * (size_t)W > sizeof(cells)) {
    W = 60;
    H = 12;
  }
  memset(cells, ' ', (size_t)H * W);
  for (int i = 0; i < N; i++) {
    int col = (int)((t[i] - tmin) / tspan * (W - 1) + 0.5);
    int row = (int)((1.0 - (vals[i] - vmin) / span) * (H - 1) + 0.5);
    if (col >= 0 && col < W)
      cells[row * W + col] = '*';
    if (i > 0 && col > -1 && col < W) {
      int pcol = (int)((t[i - 1] - tmin) / tspan * (W - 1) + 0.5);
      if (pcol >= 0 && pcol < W && pcol >= 0 && pcol != col && row >= 0)
        cells[row * W + pcol] = '.';
    }
  }
  for (int r = 0; r < H; r++) {
    double val = vmax - (double)r / (double)(H - 1) * span;
    appendf(out, cap, &pos, "%8.3g |%.*s|\n", val, W, cells + r * W);
  }
  char dash[512];
  memset(dash, '-', (size_t)(W > 0 && W < 511 ? W : 0));
  dash[W] = 0;
  appendf(out, cap, &pos, "        +%s+\n", dash);
  appendf(out, cap, &pos, "        ");
  for (int x = 0; x < 5; x++) {
    double frac = (double)x / 4.0;
    char lab[32];
    snprintf(lab, sizeof(lab), "%g", tmin + frac * tspan);
    int cw = W / 4;
    size_t l = strlen(lab);
    size_t bw = (size_t)cw > l ? (size_t)cw : l;
    size_t pad = (size_t)cw > l ? ((size_t)cw - l) / 2 : 0;
    char centered[64];
    memset(centered, ' ', sizeof(centered));
    centered[bw] = 0;
    memcpy(centered + pad, lab, l);
    appendf(out, cap, &pos, "%s", centered);
  }
  appendf(out, cap, &pos, "\n");
}

/**
 * @brief Render multiple overlaid trajectories as an ASCII chart with distinct markers.
 *
 * Overlays n series (e.g. per-meal postprandial glucose components) onto a shared
 * ASCII grid using distinct marker characters ('#', '*', '+', 'x', 'o', 'O', '@').
 *
 * @param title Chart header title.
 * @param n Number of series to plot (e.g. NMEALS).
 * @param series Array of pointers to data series arrays (each of size N).
 * @param t Array of time coordinates (size N).
 * @param N Number of data points per series.
 * @param W Plot width in characters.
 * @param H Plot height in characters.
 * @param out Destination text buffer.
 * @param cap Maximum capacity of destination text buffer.
 */
static void ascii_lines_chart(const char *title, const int n,
                              const double *const *series, const double *t,
                              int N, int W, int H, char *out, size_t cap) {
  const char markers[] = "#*+xoO@";
  double vmin = series[0][0], vmax = series[0][0];
  double tmin = t[0], tmax = t[N - 1];
  for (int k = 0; k < n; k++) {
    for (int i = 0; i < N; i++) {
      if (series[k][i] < vmin)
        vmin = series[k][i];
      if (series[k][i] > vmax)
        vmax = series[k][i];
    }
  }
  double span = (vmax - vmin) ? (vmax - vmin) : 1.0;
  double tspan = (tmax - tmin) ? (tmax - tmin) : 1.0;

  char cells[4096];
  if (H * W > (int)sizeof(cells)) {
    W = 60;
    H = 12;
  }
  memset(cells, ' ', (size_t)H * W);
  for (int k = 0; k < n && k < (int)sizeof(markers) - 1; k++) {
    for (int i = 0; i < N; i++) {
      int col = (int)((t[i] - tmin) / tspan * (W - 1) + 0.5);
      int row = (int)((1.0 - (series[k][i] - vmin) / span) * (H - 1) + 0.5);
      if (col >= 0 && col < W && row >= 0 && row < H)
        cells[row * W + col] = markers[k];
    }
  }

  size_t pos = 0;
  appendf(out, cap, &pos, "%s  (per-meal rows; t: %g .. %g, value: %g .. %g)\n",
          title, tmin, tmax, vmin, vmax);
  for (int r = 0; r < H; r++) {
    double val = vmax - (double)r / (double)(H - 1) * span;
    appendf(out, cap, &pos, "%8.3g |%.*s|\n", val, W, cells + r * W);
  }
  char dash[512];
  memset(dash, '-', W);
  dash[W] = 0;
  appendf(out, cap, &pos, "        +%s+\n", dash);
  appendf(out, cap, &pos, "        ");
  for (int x = 0; x < 5; x++) {
    double frac = (double)x / 4.0;
    char lab[32];
    snprintf(lab, sizeof(lab), "%g", tmin + frac * tspan);
    int cw = W / 4;
    size_t l = strlen(lab);
    size_t pad = (size_t)cw > l ? ((size_t)cw - l) / 2 : 0;
    char centered[64];
    memset(centered, ' ', sizeof(centered));
    centered[(size_t)cw > l ? (size_t)cw : l] = 0;
    memcpy(centered + pad, lab, l);
    appendf(out, cap, &pos, "%s", centered);
  }
  appendf(out, cap, &pos, "\n");
}

/**
 * @brief Draw a text string onto the Nuklear command buffer.
 *
 * @param cb Nuklear command buffer.
 * @param x Virtual pixel X coordinate.
 * @param y Virtual pixel Y coordinate.
 * @param s String to draw.
 * @param c Font color.
 */
static void txt(struct nk_command_buffer *cb, int x, int y, const char *s,
                struct nk_color c) {
  nk_draw_text(cb, nk_rect((float)x, (float)y, (float)strlen(s), 2.0f), s,
               (int)strlen(s), &ui_font, c, nk_rgb(0, 0, 0));
}

/**
 * @brief Pack a Nuklear RGB color structure into a 32-bit integer (0x00RRGGBB).
 *
 * @param c Nuklear color.
 * @return Packed 32-bit RGB color.
 */
static uint32_t pack(struct nk_color c) {
  return ((uint32_t)c.r << 16) | ((uint32_t)c.g << 8) | (uint32_t)c.b;
}

/**
 * @brief Translate Nuklear drawing commands into terminal canvas raster operations.
 *
 * Iterates through all commands in the Nuklear context (scissors, lines, rectangles,
 * filled rectangles, triangles, circles, polygons, and text glyphs) and dispatches
 * them to the underlying term rasterization functions.
 *
 * @param t Pointer to terminal canvas.
 * @param ctx Pointer to Nuklear GUI context.
 */
static void rasterize(term *t, struct nk_context *ctx) {
  term_clip_off(t);
  const struct nk_command *c;
  nk_foreach(c, ctx) {
    switch (c->type) {
    case NK_COMMAND_SCISSOR: {
      const struct nk_command_scissor *s = (const void *)c;
      term_set_clip(t, s->x, s->y, s->w, s->h);
      break;
    }
    case NK_COMMAND_LINE: {
      const struct nk_command_line *l = (const void *)c;
      term_line(t, l->begin.x, l->begin.y, l->end.x, l->end.y, pack(l->color));
      break;
    }
    case NK_COMMAND_RECT: {
      const struct nk_command_rect *r = (const void *)c;
      uint32_t col = pack(r->color);
      int x = r->x, y = r->y, w = r->w, h = r->h;
      term_line(t, x, y, x + w, y, col);
      term_line(t, x, y, x, y + h, col);
      term_line(t, x + w, y, x + w, y + h, col);
      term_line(t, x, y + h, x + w, y + h, col);
      break;
    }
    case NK_COMMAND_RECT_FILLED: {
      const struct nk_command_rect_filled *r = (const void *)c;
      term_fill(t, r->x, r->y, r->w, r->h, pack(r->color));
      break;
    }
    case NK_COMMAND_RECT_MULTI_COLOR: {
      const struct nk_command_rect_multi_color *r = (const void *)c;
      term_rect_multi(t, r->x, r->y, r->w, r->h, pack(r->left), pack(r->top),
                      pack(r->right), pack(r->bottom));
      break;
    }
    case NK_COMMAND_TRIANGLE: {
      const struct nk_command_triangle *tr = (const void *)c;
      term_triangle(t, tr->a.x, tr->a.y, tr->b.x, tr->b.y, tr->c.x, tr->c.y,
                    pack(tr->color), 0);
      break;
    }
    case NK_COMMAND_TRIANGLE_FILLED: {
      const struct nk_command_triangle_filled *tr = (const void *)c;
      term_triangle(t, tr->a.x, tr->a.y, tr->b.x, tr->b.y, tr->c.x, tr->c.y,
                    pack(tr->color), 1);
      break;
    }
    case NK_COMMAND_CIRCLE: {
      const struct nk_command_circle *ci = (const void *)c;
      term_ellipse(t, ci->x + ci->w / 2, ci->y + ci->h / 2, ci->w / 2,
                   ci->h / 2, pack(ci->color), 0);
      break;
    }
    case NK_COMMAND_CIRCLE_FILLED: {
      const struct nk_command_circle_filled *ci = (const void *)c;
      term_ellipse(t, ci->x + ci->w / 2, ci->y + ci->h / 2, ci->w / 2,
                   ci->h / 2, pack(ci->color), 1);
      break;
    }
    case NK_COMMAND_POLYGON: {
      const struct nk_command_polygon *pg = (const void *)c;
      term_polyline(t, (const int *)pg->points, pg->point_count,
                    pack(pg->color));
      int last = 2 * (pg->point_count - 1);
      term_line(t, pg->points[last].x, pg->points[last].y, pg->points[0].x,
                    pg->points[0].y, pack(pg->color));
      break;
    }
    case NK_COMMAND_POLYGON_FILLED: {
      const struct nk_command_polygon_filled *pg = (const void *)c;
      int n = pg->point_count;
      int *pts = malloc(sizeof(int) * 2 * (size_t)n);
      for (int i = 0; i < n; i++) {
        pts[2 * i] = pg->points[i].x;
        pts[2 * i + 1] = pg->points[i].y;
      }
      term_polygon(t, pts, n, pack(pg->color));
      free(pts);
      break;
    }
    case NK_COMMAND_POLYLINE: {
      const struct nk_command_polyline *pl = (const void *)c;
      term_polyline(t, (const int *)pl->points, pl->point_count,
                    pack(pl->color));
      break;
    }
    case NK_COMMAND_TEXT: {
      const struct nk_command_text *tx = (const void *)c;
      uint32_t col = pack(tx->foreground);
      for (int i = 0; i < tx->length; i++)
        term_glyph(t, tx->x + i, tx->y, (unsigned char)tx->string[i], col);
      break;
    }
    default:
      break;
    }
  }
  term_clip_off(t);
}

/**
 * @brief Render the simulation trajectory plot in the TUI window.
 *
 * Draws the bounding box, background grid lines, variable title, coordinate scale
 * labels, and plot lines. For per-meal components (sel == 11), draws multiple
 * color-coded curves with a meal legend; for other variables, draws a single curve.
 *
 * @param cb Nuklear command buffer.
 * @param px Left coordinate of plot area.
 * @param py Top coordinate of plot area.
 * @param pw Width of plot area.
 * @param ph Height of plot area.
 * @param sc Active simulation scenario.
 * @param res Simulation results containing variable trajectories.
 * @param sel Selected variable index [0..NVAR-1].
 */
static void draw_plot(struct nk_command_buffer *cb, int px, int py, int pw,
                      int ph, const scenario *sc, const results *res, int sel) {
  struct nk_color border = nk_rgb(150, 150, 150);
  struct nk_color dim = nk_rgb(75, 75, 75);
  struct nk_color textcol = nk_rgb(200, 200, 200);
  nk_stroke_rect(cb, nk_rect((float)px, (float)py, (float)pw, (float)ph), 0.0f,
                 1.0f, border);

  int ax = px + 2, ay = py + 2, aw = pw - 4, ah = ph - 4;
  int npts = (int)sc->N;

  double vmin, vmax;
  const double *vals = res_var((results *)res, sel);
  if (sel == 11) {
    vmin = res->g[0];
    vmax = res->g[0];
    for (int j = 0; j < NMEALS; j++)
      for (int i = 0; i < npts; i++) {
        double v = res->g[j * npts + i];
        if (v < vmin)
          vmin = v;
        if (v > vmax)
          vmax = v;
      }
  } else {
    vmin = vals[0];
    vmax = vals[0];
    for (int i = 1; i < npts; i++) {
      if (vals[i] < vmin)
        vmin = vals[i];
      if (vals[i] > vmax)
        vmax = vals[i];
    }
  }
  double pad = (vmax - vmin) * 0.06;
  if (pad == 0.0)
    pad = 0.5;
  vmin -= pad;
  vmax += pad;
  double t0 = res->t[0], t1 = res->t[npts - 1];

  for (int g = 1; g <= 3; g++) {
    int gy = ay + (int)((double)g * ah / 4.0);
    nk_stroke_line(cb, (float)ax, (float)gy, (float)(ax + aw), (float)gy, 1.0f,
                   dim);
  }
  nk_stroke_line(cb, (float)(ax + aw / 2), (float)ay, (float)(ax + aw / 2),
                 (float)(ay + ah), 1.0f, dim);

  char title[96];
  snprintf(title, sizeof(title), "%s vs t   (N=%d pts)", VAR_NAMES[sel], npts);
  int tl = (int)strlen(title);
  int txx = px + (pw - tl) / 2;
  if (txx < px + 1)
    txx = px + 1;
  int tyy = py - 2;
  if (tyy < 0)
    tyy = 0;
  txt(cb, txx, tyy, title, textcol);

  if (sel == 11) {
    struct nk_color mealcol[3] = {nk_rgb(80, 150, 255), nk_rgb(80, 255, 200),
                                  nk_rgb(255, 160, 80)};
    for (int j = 0; j < NMEALS; j++) {
      for (int i = 0; i < npts - 1; i++) {
        double xa = ax + (res->t[i] - t0) / (t1 - t0) * (aw - 1);
        double ya =
            ay + (1 - (res->g[j * npts + i] - vmin) / (vmax - vmin)) * (ah - 1);
        double xb = ax + (res->t[i + 1] - t0) / (t1 - t0) * (aw - 1);
        double yb =
            ay +
            (1 - (res->g[j * npts + i + 1] - vmin) / (vmax - vmin)) * (ah - 1);
        nk_stroke_line(cb, (float)xa, (float)ya, (float)xb, (float)yb, 1.0f,
                       mealcol[j]);
      }
    }
    txt(cb, ax + 2, ay, "meal1", mealcol[0]);
    txt(cb, ax + 30, ay, "meal2", mealcol[1]);
    txt(cb, ax + 58, ay, "meal3", mealcol[2]);
  } else {
    struct nk_color col = nk_rgb(200, 220, 255);
    for (int i = 0; i < npts - 1; i++) {
      double xa = ax + (res->t[i] - t0) / (t1 - t0) * (aw - 1);
      double ya = ay + (1 - (vals[i] - vmin) / (vmax - vmin)) * (ah - 1);
      double xb = ax + (res->t[i + 1] - t0) / (t1 - t0) * (aw - 1);
      double yb = ay + (1 - (vals[i + 1] - vmin) / (vmax - vmin)) * (ah - 1);
      nk_stroke_line(cb, (float)xa, (float)ya, (float)xb, (float)yb, 1.0f, col);
    }
  }

  char label[32];
  snprintf(label, sizeof(label), "%g", vmin + pad);
  txt(cb, ax + 2, ay + ah - 2, label, textcol);
  snprintf(label, sizeof(label), "%g", vmax - pad);
  txt(cb, ax + 2, ay + 6, label, textcol);
  snprintf(label, sizeof(label), "%g", t0);
  txt(cb, ax, ay + ah, label, textcol);
  snprintf(label, sizeof(label), "%g", t1);
  txt(cb, ax + aw - 12, ay + ah, label, textcol);
}

/**
 * @brief Build the complete Nuklear TUI layout for the current frame.
 *
 * Constructs the header bar, left-hand variable selection sidebar, central plot
 * canvas, bottom parameter adjustment panel, and optional help overlay modal.
 *
 * @param ctx Nuklear GUI context.
 * @param t Pointer to terminal canvas.
 * @param sc Active simulation scenario.
 * @param res Current simulation results.
 * @param u Pointer to TUI state struct.
 * @param params Array of tunable parameter descriptors.
 */
static void draw_ui(struct nk_context *ctx, term *t, const scenario *sc,
                    const results *res, ui *u, cparam *params) {
  int vw = t->vw, vh = t->vh;
  u->hdr = 2;
  u->lw = 10;
  int main_x = u->lw, main_y = u->hdr;
  int main_w = vw - u->lw, main_h = vh - u->hdr;
  int parmh = 16;

  nk_begin(ctx, "cma", nk_rect(0, 0, (float)vw, (float)vh),
           NK_WINDOW_NO_SCROLLBAR);
  struct nk_command_buffer *cb = nk_window_get_canvas(ctx);
  nk_push_scissor(cb, nk_rect(0.0f, 0.0f, (float)vw, (float)vh));

  if (main_w < 16 || main_h < 16) {
    txt(cb, 0, 0, "terminal too small (need >= 20x12)", nk_rgb(255, 100, 100));
    nk_end(ctx);
    return;
  }

  u->pl_x = main_x + 2;
  u->pl_y = main_y + 2;
  u->pl_w = main_w - 4;
  u->pl_h = main_h - parmh - 3;
  if (u->pl_h < 10)
    u->pl_h = 10;
  int px = u->pl_x, py = u->pl_y, pw = u->pl_w, ph = u->pl_h;

  u->pp_x = px;
  u->pp_y = py + ph + 2;
  u->pp_w = pw;
  u->pp_h = parmh - 3;

  txt(cb, 0, 0,
      "PFun CMA (nuklear tty)   j/k:sel  Tab:panel  +/-:adj  q:quit  h:help",
      nk_rgb(210, 210, 210));

  nk_fill_rect(cb,
               nk_rect(0, (float)u->hdr, (float)u->lw, (float)(vh - u->hdr)),
               0.0f, nk_rgb(18, 18, 18));

  int vis = (vh - u->hdr) / 2;
  for (int v = 0; v < NVAR && v < vis; v++) {
    int ry = u->hdr + v * 2;
    if (v == u->sel) {
      nk_fill_rect(cb, nk_rect(0, (float)ry, (float)u->lw, 2.0f), 0.0f,
                   u->panel == 0 ? nk_rgb(62, 74, 118) : nk_rgb(40, 48, 70));
    }
    char row[16];
    snprintf(row, sizeof(row), "%c%s", v == u->sel ? '>' : ' ', VAR_NAMES[v]);
    txt(cb, 1, ry, row, nk_rgb(230, 230, 230));
  }

  draw_plot(cb, px, py, pw, ph, sc, res, u->sel);

  int ppy = u->pp_y;
  nk_fill_rect(
      cb, nk_rect((float)u->pp_x, (float)ppy, (float)u->pp_w, (float)u->pp_h),
      0.0f, nk_rgb(14, 14, 14));
  nk_stroke_rect(
      cb, nk_rect((float)u->pp_x, (float)ppy, (float)u->pp_w, (float)u->pp_h),
      0.0f, 1.0f, nk_rgb(110, 110, 110));
  txt(cb, u->pp_x + 1, ppy,
      u->panel == 1 ? "parameters (editing)" : "parameters",
      nk_rgb(150, 200, 150));

  int vrows = (u->pp_h - 3) / 2;
  for (int r = 0; r < vrows; r++) {
    int idx = u->poff + r;
    if (idx >= NPARAM)
      break;
    int ry = ppy + 2 + r * 2;
    if (idx == u->pfocus && u->panel == 1) {
      nk_fill_rect(
          cb,
          nk_rect((float)(u->pp_x + 1), (float)ry, (float)(u->pp_w - 2), 2.0f),
          0.0f, nk_rgb(92, 70, 40));
    }
    char line[64];
    if (params[idx].is_bool) {
      snprintf(line, sizeof(line), "%-8s [%c]", params[idx].name,
               (int)*params[idx].val ? 'x' : ' ');
    } else if (params[idx].val == &sc->N) {
      snprintf(line, sizeof(line), "%-8s %d", params[idx].name,
               (int)*params[idx].val);
    } else {
      snprintf(line, sizeof(line), "%-8s %.4g", params[idx].name,
               *params[idx].val);
    }
    txt(cb, u->pp_x + 2, ry, line, nk_rgb(230, 230, 230));
  }

  if (u->help) {
    nk_fill_rect(cb, nk_rect(6, 10, (float)(vw - 12), 8.0f), 0.0f,
                 nk_rgb(30, 30, 30));
    nk_stroke_rect(cb, nk_rect(6, 10, (float)(vw - 12), 8.0f), 0.0f, 1.0f,
                   nk_rgb(120, 120, 120));
    txt(cb, 8, 11, "j/k: select variable     up/down: move within panel",
        nk_rgb(220, 220, 220));
    txt(cb, 8, 13, "Tab: switch panel (list/params)   left/right/+/-: adjust",
        nk_rgb(220, 220, 220));
    txt(cb, 8, 15, "enter: toggle checkbox   q: quit   h: this help",
        nk_rgb(220, 220, 220));
    nk_end(ctx);
    return;
  }

  if (u->panel == 0) {
    char sel[16];
    snprintf(sel, sizeof(sel), "%d/%d", u->sel + 1, NVAR);
    txt(cb, main_x, vh - 2, sel, nk_rgb(150, 150, 150));
  }
  nk_end(ctx);
}

/**
 * @brief Parse ANSI SGR 1006 extended mouse tracking escape sequences.
 *
 * Decodes sequences of the format "\033[<b;x;yM" or "\033[<b;x;ym" and feeds
 * corresponding motion, button press/release, or scroll events into the Nuklear context.
 *
 * @param t Pointer to terminal canvas (unused).
 * @param ctx Nuklear GUI context.
 * @param s Raw escape sequence byte buffer.
 * @param len Length of escape sequence in bytes.
 * @param u Pointer to TUI state struct (sets redraw flag on mouse event).
 */
static void csi_mouse(term *t, struct nk_context *ctx, const unsigned char *s,
                      int len, ui *u) {
  (void)t;
  int i = 0;
  if (i < len && s[i] == '\033')
    i++;
  if (i < len && s[i] == '[')
    i++;
  if (i < len && s[i] == '<')
    i++;
  int b = 0, x = 0, y = 0, cur = 0, digit = 0;
  for (; i < len; i++) {
    unsigned char c = s[i];
    if (c >= '0' && c <= '9') {
      if (!digit)
        digit = 1;
      if (cur == 0)
        b = b * 10 + (c - '0');
      else if (cur == 1)
        x = x * 10 + (c - '0');
      else
        y = y * 10 + (c - '0');
    } else if (c == ';') {
      cur++;
      digit = 0;
    } else {
      break;
    }
  }
  int lx = x - 1;
  int ly = (y - 1) * 2 + 1;
  nk_input_motion(ctx, lx, ly);
  if (b >= 64) {
    nk_input_scroll(ctx, nk_vec2(0, (b & 1) ? -1.0f : 1.0f));
    return;
  }
  int btn = (b & 3) == 1 ? 1 : ((b & 3) == 2 ? 2 : 0);
  nk_input_button(ctx, (enum nk_buttons)btn, lx, ly, nk_true);
  nk_input_button(ctx, (enum nk_buttons)btn, lx, ly, nk_false);
  u->redraw = 1;
}

/**
 * @brief Parse raw terminal input bytes into keyboard and mouse events.
 *
 * Buffers ANSI escape sequences, recognizing arrow keys, Home/End, mouse events,
 * and standard keys (Tab, j/k, +/-, Enter, h, q) to update UI navigation and flags.
 *
 * @param t Pointer to terminal canvas.
 * @param ctx Nuklear GUI context.
 * @param u Pointer to TUI state struct.
 * @param buf Input byte buffer.
 * @param n Number of bytes available in buf.
 */
static void process_bytes(term *t, struct nk_context *ctx, ui *u,
                          const unsigned char *buf, int n) {
  static unsigned char seq[64];
  static int seqlen = 0;
  for (int i = 0; i < n; i++) {
    unsigned char ch = buf[i];
    if (ch == '\033') {
      seqlen = 1;
      seq[0] = ch;
      continue;
    }
    if (seqlen > 0) {
      seq[seqlen++] = ch;
      if (ch >= 0x40 && ch <= 0x7e) {
        if (seqlen >= 2 && seq[1] == '[') {
          char fin = (char)seq[seqlen - 1];
          switch (fin) {
          case 'A':
            nk_input_key(ctx, NK_KEY_UP, nk_true);
            nk_input_key(ctx, NK_KEY_UP, nk_false);
            break;
          case 'B':
            nk_input_key(ctx, NK_KEY_DOWN, nk_true);
            nk_input_key(ctx, NK_KEY_DOWN, nk_false);
            break;
          case 'C':
            nk_input_key(ctx, NK_KEY_RIGHT, nk_true);
            nk_input_key(ctx, NK_KEY_RIGHT, nk_false);
            break;
          case 'D':
            nk_input_key(ctx, NK_KEY_LEFT, nk_true);
            nk_input_key(ctx, NK_KEY_LEFT, nk_false);
            break;
          case 'H':
            nk_input_key(ctx, NK_KEY_TEXT_START, nk_true);
            nk_input_key(ctx, NK_KEY_TEXT_START, nk_false);
            break;
          case 'F':
            nk_input_key(ctx, NK_KEY_TEXT_END, nk_true);
            nk_input_key(ctx, NK_KEY_TEXT_END, nk_false);
            break;
          case 'M':
          case 'm': {
            int haslt = 0;
            for (int k = 0; k < seqlen; k++)
              if (seq[k] == '<')
                haslt = 1;
            if (haslt)
              csi_mouse(t, ctx, seq, seqlen, u);
            break;
          }
          default:
            break;
          }
        }
        seqlen = 0;
      } else if (seqlen >= (int)sizeof(seq)) {
        seqlen = 0;
      }
      u->redraw = 1;
      continue;
    }
    switch (ch) {
    case '\t':
      nk_input_key(ctx, NK_KEY_TAB, nk_true);
      nk_input_key(ctx, NK_KEY_TAB, nk_false);
      u->panel = !u->panel;
      if (u->panel == 1) {
        if (u->pfocus < 0 || u->pfocus >= NPARAM)
          u->pfocus = 0;
      } else {
        u->pfocus = -1;
      }
      break;
    case 'j':
    case 'J':
      nk_input_key(ctx, NK_KEY_DOWN, nk_true);
      nk_input_key(ctx, NK_KEY_DOWN, nk_false);
      break;
    case 'k':
    case 'K':
      nk_input_key(ctx, NK_KEY_UP, nk_true);
      nk_input_key(ctx, NK_KEY_UP, nk_false);
      break;
    case 'h':
    case 'H':
      u->help = !u->help;
      break;
    case 'q':
    case 'Q':
      u->quit = 1;
      break;
    case '\r':
      nk_input_key(ctx, NK_KEY_ENTER, nk_true);
      nk_input_key(ctx, NK_KEY_ENTER, nk_false);
      break;
    case '+':
      nk_input_key(ctx, NK_KEY_RIGHT, nk_true);
      nk_input_key(ctx, NK_KEY_RIGHT, nk_false);
      break;
    case '-':
      nk_input_key(ctx, NK_KEY_LEFT, nk_true);
      nk_input_key(ctx, NK_KEY_LEFT, nk_false);
      break;
    default:
      break;
    }
    u->redraw = 1;
  }
}

/** Atomic flag set by SIGWINCH handler indicating terminal window resize. */
static volatile sig_atomic_t g_resize = 0;

/**
 * @brief Signal handler for SIGWINCH (window resize).
 *
 * Sets the g_resize flag to trigger terminal buffer reallocation on next event loop iteration.
 *
 * @param sig Signal number (SIGWINCH).
 */
static void on_sigwinch(int sig) {
  (void)sig;
  g_resize = 1;
}

/** Global terminal context pointer used by cleanup signal handler. */
static term *g_term;

/**
 * @brief Signal handler for SIGINT and SIGTERM to restore terminal state before exit.
 *
 * Ensures alternate screen is exited, cursor restored, and termios settings reverted
 * before terminating process.
 *
 * @param sig Signal number received.
 */
static void cleanup_and_exit(int sig) {
  (void)sig;
  term_close(g_term);
  _exit(128 + (sig == 0 ? 128 : sig));
}

/**
 * @brief Application entry point for CMA demo.
 *
 * Parses command-line flags (--ascii, --save FILE, --pts N, --mouse, --help).
 * In ASCII mode, runs a single simulation, generates ASCII charts for all 12
 * variables, prints to stdout, and optionally saves to file.
 * In interactive mode, initializes raw terminal and Nuklear context, runs the
 * event loop with poll(), processes keyboard/mouse input, recalculates simulation
 * trajectories dynamically upon parameter changes, rasterizes the UI, and flushes
 * to the terminal.
 *
 * @param argc Number of command-line arguments.
 * @param argv Array of command-line argument strings.
 * @return 0 on successful termination.
 */
int main(int argc, char **argv) {
  int ascii_mode = 0;
  int save = 0;
  int mouse = 0;
  const char *savepath = "docs/demo_outputs/DEMO_C_OUTPUT.md";
  double pts = 97.0;
  for (int i = 1; i < argc; i++) {
    if (strcmp(argv[i], "--ascii") == 0)
      ascii_mode = 1;
    else if (strcmp(argv[i], "--save") == 0 && i + 1 < argc) {
      save = 1;
      savepath = argv[++i];
    } else if (strcmp(argv[i], "--pts") == 0 && i + 1 < argc)
      pts = atof(argv[++i]);
    else if (strcmp(argv[i], "--mouse") == 0)
      mouse = 1;
    else if (strcmp(argv[i], "--help") == 0 || strcmp(argv[i], "-h") == 0) {
      printf("usage: demo [--ascii] [--save FILE] [--pts N] [--mouse]\n");
      return 0;
    }
  }

  scenario sc;
  results res;
  scenario_default(&sc, pts);
  scenario_run(&sc, &res);
  int N = (int)sc.N;
  int W = 60, H = 12;

  if (ascii_mode) {
    char *buf = malloc(1 << 20);
    size_t pos = 0;
    appendf(buf, 1 << 20, &pos,
            "# demo.c session output (`--ascii`)\n\n"
            "scenario: t=[0..24], N=%d, d=%g taup=%g taug_val=%g, "
            "B=%g Cm=%g toff=%g, tM=[%g,%g,%g], activity=%s\n\n",
            N, sc.d, sc.taup, sc.taug_val, sc.B, sc.Cm, sc.toff, sc.tM[0],
            sc.tM[1], sc.tM[2], sc.act_on ? "on" : "off");
    for (int v = 0; v < NVAR; v++) {
      char chart[4096];
      chart[0] = 0;
      if (v == 11) {
        const double *rows[NMEALS];
        for (int k = 0; k < NMEALS; k++)
          rows[k] = res.g + (size_t)k * N;
        ascii_lines_chart("g", NMEALS, rows, res.t, N, W, H, chart,
                          sizeof(chart));
      } else {
        ascii_chart(VAR_NAMES[v], res_var(&res, v), res.t, N, W, H, chart,
                    sizeof(chart));
      }
      appendf(buf, 1 << 20, &pos, "```text\n%s```\n\n", chart);
    }
    fwrite(buf, 1, pos, stdout);
    if (save) {
      FILE *fh = fopen(savepath, "w");
      if (fh) {
        fwrite(buf, 1, pos, fh);
        fclose(fh);
        fprintf(stderr, "wrote %s\n", savepath);
      } else {
        fprintf(stderr, "could not write %s\n", savepath);
      }
    }
    free(buf);
    return 0;
  }

  ui u;
  memset(&u, 0, sizeof(u));
  u.pfocus = -1;
  u.redraw = 1;
  cparam params[NPARAM];
  scenario_params(&sc, params);
  sc.N = 97.0;

  term t;
  g_term = &t;
  term_open(&t, mouse);
  signal(SIGWINCH, on_sigwinch);
  signal(SIGINT, cleanup_and_exit);
  signal(SIGTERM, cleanup_and_exit);

  memset(&ui_font, 0, sizeof(ui_font));
  ui_font.height = 2.0f;
  ui_font.width = font_width;
  ui_font.userdata = nk_handle_id(0);

  struct nk_context ctx;
  nk_init_default(&ctx, &ui_font);

  struct pollfd pfd = {STDIN_FILENO, POLLIN, 0};

  while (!u.quit) {
    nk_input_begin(&ctx);
    int ready = poll(&pfd, 1, 50);
    if (ready > 0 && (pfd.revents & POLLIN)) {
      unsigned char buf[512];
      int n = term_read(&t, buf, (int)sizeof(buf));
      if (n > 0)
        process_bytes(&t, &ctx, &u, buf, n);
    }
    if (g_resize) {
      g_resize = 0;
      if (term_resize(&t))
        u.redraw = 1;
    }
    nk_input_end(&ctx);

    scenario_run(&sc, &res);

    if (nk_input_is_key_pressed(&ctx.input, NK_KEY_ENTER)) {
      u.redraw = 1;
    }

    if (u.panel == 0) {
      struct nk_vec2 sd = ctx.input.mouse.scroll_delta;
      if (sd.y > 0.0f && u.sel > 0) {
        u.sel--;
        u.redraw = 1;
      }
      if (sd.y < 0.0f && u.sel < NVAR - 1) {
        u.sel++;
        u.redraw = 1;
      }
    }

    if (u.panel == 1 && u.pfocus >= 0) {
      cparam *p = &params[u.pfocus];
      int dec = nk_input_is_key_pressed(&ctx.input, NK_KEY_LEFT);
      int inc = nk_input_is_key_pressed(&ctx.input, NK_KEY_RIGHT);
      int blk_toggle = nk_input_is_key_pressed(&ctx.input, NK_KEY_ENTER) &&
                       p->lo == 0.0 && p->hi == 1.0;
      if (blk_toggle) {
        *p->val = *p->val > 0.5 ? 0.0 : 1.0;
        u.redraw = 1;
      }
      if (dec || inc) {
        if (p->is_bool) {
          *p->val = *p->val > 0.5 ? 0.0 : 1.0;
        } else {
          if (dec)
            *p->val -= p->step;
          if (inc)
            *p->val += p->step;
          if (*p->val < p->lo)
            *p->val = p->lo;
          if (*p->val > p->hi)
            *p->val = p->hi;
        }
        u.redraw = 1;
      }
      if (nk_input_is_key_pressed(&ctx.input, NK_KEY_UP) && u.pfocus > 0) {
        u.pfocus--;
        u.redraw = 1;
      }
      if (nk_input_is_key_pressed(&ctx.input, NK_KEY_DOWN) &&
          u.pfocus < NPARAM - 1) {
        u.pfocus++;
        u.redraw = 1;
      }
      if (u.pfocus < u.poff)
        u.poff = u.pfocus;
      if (u.pfocus >= u.poff + 6)
        u.poff = u.pfocus;
    }

    if (nk_input_has_mouse_click(&ctx.input, NK_BUTTON_LEFT)) {
      struct nk_vec2 mp = ctx.input.mouse.pos;
      int mx = (int)mp.x, my = (int)mp.y;
      if (mx >= 0 && mx < u.lw && my >= u.hdr) {
        int row = (my - u.hdr) / 2;
        if (row >= 0 && row < NVAR) {
          u.sel = row;
          u.panel = 0;
          u.pfocus = -1;
          u.redraw = 1;
        }
      } else if (my >= u.pp_y && my < u.pp_y + u.pp_h && mx >= u.pp_x &&
                 mx < u.pp_x + u.pp_w) {
        int row = (my - u.pp_y - 2) / 2;
        if (row >= 0) {
          u.panel = 1;
          u.pfocus = u.poff + row;
          if (u.pfocus >= NPARAM)
            u.pfocus = NPARAM - 1;
          u.redraw = 1;
        }
      }
    }

    draw_ui(&ctx, &t, &sc, &res, &u, params);

    if (u.redraw) {
      rasterize(&t, &ctx);
      term_flush(&t);
      u.redraw = 0;
    }
    nk_clear(&ctx);
  }

  term_close(&t);
  return 0;
}