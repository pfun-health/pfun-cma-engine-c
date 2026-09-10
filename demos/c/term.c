/**
 * @file term.c
 * @brief Terminal graphics backend implementation using Unicode half-blocks and
 * 24-bit color.
 *
 * Implements a virtual pixel drawing surface in terminal emulators using 24-bit
 * truecolor ANSI escape sequences. Doubling vertical resolution is achieved by
 * representing each character cell as two vertical sub-pixels using the Unicode
 * upper half-block character (U+2580, '▀'). Provides Bresenham line drawing,
 * scanline polygon and triangle filling, midpoint ellipses, text glyph overlays
 * with automatic contrast calculation, clipping rectangles, and optimized
 * escape sequence buffering.
 */

#include "term.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <poll.h>
#include <sys/ioctl.h>

/** Unicode codepoint for the upper half-block character (▀). */
#define CELL_HALF 0x2580u

/** Minimum required luminance difference between glyph foreground and
 * background. */
#define FONT_CONTRAST_MIN 90u

/**
 * @brief Calculate ITU-R BT.601 relative luminance (0..255) of a packed color.
 *
 * Computes luma = (77 * R + 150 * G + 29 * B) / 256.
 *
 * @param c Packed 0x00RRGGBB color.
 * @return Relative luminance in the range [0, 255].
 */
static unsigned luma(uint32_t c) {
  return ((77u * ((c >> 16) & 0xff)) + (150u * ((c >> 8) & 0xff)) +
          (29u * (c & 0xff))) >>
         8;
}

/**
 * @brief Linear alpha blending between destination and source colors.
 *
 * Computes component-wise blending: out = (dest * (255 - a) + src * a) / 255.
 *
 * @param d Packed 0x00RRGGBB destination color.
 * @param s Packed 0x00RRGGBB source color.
 * @param a Alpha opacity value in the range [0, 255] (0 = fully transparent,
 * 255 = fully opaque).
 * @return Blended packed 0x00RRGGBB color.
 */
static uint32_t blend(uint32_t d, uint32_t s, unsigned a) {
  if (a >= 255)
    return s;
  if (a == 0)
    return d;
  unsigned dr = (d >> 16) & 0xff, dg = (d >> 8) & 0xff, db = d & 0xff;
  unsigned sr = (s >> 16) & 0xff, sg = (s >> 8) & 0xff, sb = s & 0xff;
  unsigned nr = (dr * (255 - a) + sr * a) / 255;
  unsigned ng = (dg * (255 - a) + sg * a) / 255;
  unsigned nb = (db * (255 - a) + sb * a) / 255;
  return (nr << 16) | (ng << 8) | nb;
}

/**
 * @brief Test if virtual canvas pixel coordinates lie within active clipping
 * bounds.
 *
 * @param t Pointer to terminal context.
 * @param x Virtual pixel X coordinate.
 * @param y Virtual pixel Y coordinate.
 * @return Non-zero if (x, y) is inside canvas and inside clip rect (if
 * enabled); 0 otherwise.
 */
static int in_clip(term *t, int x, int y) {
  return x >= 0 && y >= 0 && x < t->vw && y < t->vh &&
         (!t->clip_on ||
          (x >= t->clip_x && y >= t->clip_y && x < t->clip_x + t->clip_w &&
           y < t->clip_y + t->clip_h));
}

/**
 * @brief Plot a sub-pixel onto the virtual canvas with alpha blending.
 *
 * Translates virtual coordinate y into terminal row (y >> 1) and half-cell
 * indicator (y & 1). When half is 0, the top sub-pixel is updated; when 1,
 * the bottom sub-pixel is updated. Any existing text glyph at this cell is
 * cleared.
 *
 * @param t Pointer to terminal context.
 * @param x Virtual pixel X coordinate.
 * @param y Virtual pixel Y coordinate.
 * @param color Packed 0x00RRGGBB color to plot.
 * @param a Alpha opacity value [0, 255].
 */
static void put(term *t, int x, int y, uint32_t color, unsigned a) {
  if (!in_clip(t, x, y))
    return;
  int col = x;
  int row = y >> 1;
  int half = y & 1;
  size_t off = (size_t)row * (size_t)t->cols + (size_t)col;
  if (half == 0)
    t->top[off] = blend(t->top[off], color, a);
  else
    t->bot[off] = blend(t->bot[off], color, a);
  t->ch[off] = 0;
}

/**
 * @brief Allocate or resize framebuffers for the specified terminal dimensions.
 *
 * Allocates top, bottom, and character cell buffers for cols * rows cells.
 * Updates canvas dimensions (vw = cols, vh = rows * 2).
 *
 * @param t Pointer to terminal context.
 * @param cols Number of terminal columns.
 * @param rows Number of terminal rows.
 * @return 1 on successful allocation, 0 on failure.
 */
static int alloc_screen(term *t, int cols, int rows) {
  size_t n = (size_t)cols * (size_t)rows;
  uint32_t *top = calloc(n, sizeof(uint32_t));
  uint32_t *bot = calloc(n, sizeof(uint32_t));
  unsigned char *ch = calloc(n, 1);

  if ((n > 0) && (!top || !bot || !ch)) {
    free(top);
    free(bot);
    free(ch);
    return 0;
  }

  free(t->top);
  free(t->bot);
  free(t->ch);
  t->top = top;
  t->bot = bot;
  t->ch = ch;
  t->cols = cols;
  t->rows = rows;
  t->vw = cols;
  t->vh = rows * 2;
  return 1;
}

/**
 * @brief Query current terminal window dimensions via ioctl.
 *
 * Issues TIOCGWINSZ ioctl on the specified file descriptor to obtain columns
 * and rows.
 *
 * @param fd Terminal file descriptor.
 * @param cols Output pointer to store column count.
 * @param rows Output pointer to store row count.
 * @return 1 if window size was successfully retrieved, 0 otherwise.
 */
static int query_size(int fd, int *cols, int *rows) {
  struct winsize ws;
  if (ioctl(fd, TIOCGWINSZ, &ws) < 0 || ws.ws_col == 0 || ws.ws_row == 0)
    return 0;
  *cols = (int)ws.ws_col;
  *rows = (int)ws.ws_row;
  return 1;
}

/**
 * @brief Open and configure the terminal for raw graphics rendering.
 *
 * Puts terminal into raw mode (disabling echo, canonical mode, and signals),
 * queries terminal size, allocates display buffers, switches to alternate
 * screen, hides the cursor, and optionally enables SGR extended mouse tracking.
 *
 * @param t Pointer to terminal context to initialize.
 * @param mouse 1 to enable mouse tracking, 0 to disable.
 */
void term_open(term *t, int mouse) {
  memset(t, 0, sizeof(*t));
  t->fd = STDIN_FILENO;
  t->mouse = mouse;
  tcgetattr(t->fd, &t->tio);
  struct termios raw = t->tio;
#ifdef __APPLE__
  /* macOS lacks cfmakeraw; set equivalent flags */
  raw.c_iflag &=
      ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
  raw.c_oflag &= ~OPOST;
  raw.c_lflag &= ~(ECHO | ECHONL | ICANON | ISIG | IEXTEN);
  raw.c_cflag &= ~(CSIZE | PARENB);
  raw.c_cflag |= CS8;
#else
  cfmakeraw(&raw);
#endif
  raw.c_cc[VMIN] = 1;
  raw.c_cc[VTIME] = 0;
  tcsetattr(t->fd, TCSANOW, &raw);
  int cols, rows;
  if (!query_size(t->fd, &cols, &rows)) {
    cols = 80;
    rows = 24;
  }
  if (!alloc_screen(t, cols, rows)) {
    t->cols = t->rows = t->vw = t->vh = 0;
  }
#define ESTR "\033[?1049h\033[?25l\033[2J\033[H"
  write(STDOUT_FILENO, ESTR, sizeof(ESTR) - 1);
  if (mouse)
    write(STDOUT_FILENO, "\033[?1000h\033[?1006h", 16);
#undef ESTR
}

/**
 * @brief Restore terminal to its original state and free all resources.
 *
 * Disables mouse tracking, restores cursor visibility, switches back to the
 * primary screen, resets colors, frees screen and output buffers, and restores
 * original termios settings.
 *
 * @param t Pointer to terminal context.
 */
void term_close(term *t) {
  if (t->mouse)
    write(STDOUT_FILENO, "\033[?1000l\033[?1006l", 16);
  write(STDOUT_FILENO, "\033[0m\033[?25h\033[?1049l",
        sizeof("\033[0m\033[?25h\033[?1049l") - 1);
  if (t->top) {
    free(t->top);
    free(t->bot);
    free(t->ch);
  }
  t->top = t->bot = NULL;
  t->ch = NULL;
  if (t->out) {
    free(t->out);
    t->out = NULL;
  }
  tcsetattr(t->fd, TCSANOW, &t->tio);
}

/**
 * @brief Check for window size changes and reallocate screen buffers
 * accordingly.
 *
 * @param t Pointer to terminal context.
 * @return 1 if screen was resized and reallocated, 0 if unchanged or failed.
 */
int term_resize(term *t) {
  int c, r;
  if (!query_size(t->fd, &c, &r))
    return 0;
  if (c == t->cols && r == t->rows)
    return 0;
  if (!alloc_screen(t, c, r))
    return 0;
  return 1;
}

/**
 * @brief Read raw input bytes from the terminal.
 *
 * @param t Pointer to terminal context.
 * @param buf Destination buffer.
 * @param cap Maximum capacity of buf.
 * @return Number of bytes read, or negative value on error.
 */
int term_read(term *t, unsigned char *buf, int cap) {
  ssize_t n = read(t->fd, buf, (size_t)cap);
  return (int)n;
}

/**
 * @brief Activate rectangular clipping boundary on the virtual canvas.
 *
 * @param t Pointer to terminal context.
 * @param x Left coordinate of clipping rectangle.
 * @param y Top coordinate of clipping rectangle.
 * @param w Width of clipping rectangle.
 * @param h Height of clipping rectangle.
 */
void term_set_clip(term *t, int x, int y, int w, int h) {
  t->clip_on = 1;
  t->clip_x = x;
  t->clip_y = y;
  t->clip_w = w < 0 ? 0 : w;
  t->clip_h = h < 0 ? 0 : h;
}

/**
 * @brief Deactivate clipping, restoring full canvas rasterization.
 *
 * @param t Pointer to terminal context.
 */
void term_clip_off(term *t) { t->clip_on = 0; }

/**
 * @brief Fill an axis-aligned rectangular region with a solid color.
 *
 * @param t Pointer to terminal context.
 * @param x Left coordinate.
 * @param y Top coordinate.
 * @param w Width of region.
 * @param h Height of region.
 * @param color Packed 0x00RRGGBB fill color.
 */
void term_fill(term *t, int x, int y, int w, int h, uint32_t color) {
  for (int j = y; j < y + h; j++)
    for (int i = x; i < x + w; i++)
      put(t, i, j, color, 255);
}

/**
 * @brief Bresenham line rasterization helper for shallow slopes (|dy| <= |dx|).
 *
 * @param t Pointer to terminal context.
 * @param x0 Starting X coordinate.
 * @param y0 Starting Y coordinate.
 * @param x1 Ending X coordinate.
 * @param y1 Ending Y coordinate.
 * @param c Packed 0x00RRGGBB line color.
 */
static void line_low(term *t, int x0, int y0, int x1, int y1, uint32_t c) {
  int dx = x1 - x0, dy = y1 - y0;
  int yi = 1;
  if (dy < 0) {
    yi = -1;
    dy = -dy;
  }
  int D = 2 * dy - dx;
  int y = y0;
  for (int x = x0; x <= x1; x++) {
    put(t, x, y, c, 255);
    if (D > 0) {
      y += yi;
      D -= 2 * dx;
    }
    D += 2 * dy;
  }
}

/**
 * @brief Bresenham line rasterization helper for steep slopes (|dy| > |dx|).
 *
 * @param t Pointer to terminal context.
 * @param x0 Starting X coordinate.
 * @param y0 Starting Y coordinate.
 * @param x1 Ending X coordinate.
 * @param y1 Ending Y coordinate.
 * @param c Packed 0x00RRGGBB line color.
 */
static void line_high(term *t, int x0, int y0, int x1, int y1, uint32_t c) {
  int dx = x1 - x0, dy = y1 - y0;
  int xi = 1;
  if (dx < 0) {
    xi = -1;
    dx = -dx;
  }
  int D = 2 * dx - dy;
  int x = x0;
  for (int y = y0; y <= y1; y++) {
    put(t, x, y, c, 255);
    if (D > 0) {
      x += xi;
      D -= 2 * dy;
    }
    D += 2 * dx;
  }
}

/**
 * @brief Draw a line segment between two virtual pixels using Bresenham's
 * algorithm.
 *
 * Automatically branches to line_low or line_high depending on line slope.
 *
 * @param t Pointer to terminal context.
 * @param x0 Starting X coordinate.
 * @param y0 Starting Y coordinate.
 * @param x1 Ending X coordinate.
 * @param y1 Ending Y coordinate.
 * @param color Packed 0x00RRGGBB line color.
 */
void term_line(term *t, int x0, int y0, int x1, int y1, uint32_t color) {
  if (abs(y1 - y0) < abs(x1 - x0)) {
    if (x0 > x1)
      line_low(t, x1, y1, x0, y0, color);
    else
      line_low(t, x0, y0, x1, y1, color);
  } else {
    if (y0 > y1)
      line_high(t, x1, y1, x0, y0, color);
    else
      line_high(t, x0, y0, x1, y1, color);
  }
}

/**
 * @brief Rasterize an ellipse centered at (cx, cy) with horizontal and vertical
 * radii.
 *
 * Supports both hollow outline and solid filled modes using the normalized
 * ellipse equation (dx/rx)^2 + (dy/ry)^2 <= 1.0.
 *
 * @param t Pointer to terminal context.
 * @param cx Center X coordinate.
 * @param cy Center Y coordinate.
 * @param rx Horizontal radius.
 * @param ry Vertical radius.
 * @param color Packed 0x00RRGGBB drawing color.
 * @param filled 1 for solid fill, 0 for outline.
 */
void term_ellipse(term *t, int cx, int cy, int rx, int ry, uint32_t color,
                  int filled) {
  int x0 = cx - rx, x1 = cx + rx, y0 = cy - ry, y1 = cy + ry;
  if (rx <= 0 || ry <= 0) {
    if (rx == 0 && ry == 0)
      put(t, cx, cy, color, 255);
    return;
  }
  double rx2 = (double)rx * rx, ry2 = (double)ry * ry;
  for (int y = y0; y <= y1; y++) {
    for (int x = x0; x <= x1; x++) {
      double dx = (double)(x - cx), dy = (double)(y - cy);
      double d = dx * dx / rx2 + dy * dy / ry2;
      if (filled) {
        if (d <= 1.0)
          put(t, x, y, color, 255);
      } else {
        if (d >= 0.7 && d <= 1.3)
          put(t, x, y, color, 255);
      }
    }
  }
}

/**
 * @brief Compute the 2D cross product of edge (p0 -> p1) and point p2.
 *
 * Used for point-in-triangle half-plane inclusion tests.
 *
 * @param x0 Edge start X coordinate.
 * @param y0 Edge start Y coordinate.
 * @param x1 Edge end X coordinate.
 * @param y1 Edge end Y coordinate.
 * @param x2 Test point X coordinate.
 * @param y2 Test point Y coordinate.
 * @return Signed area (positive, zero, or negative).
 */
static int sign3(int x0, int y0, int x1, int y1, int x2, int y2) {
  return (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
}

/**
 * @brief Draw a triangle (outline or solid filled) defined by three vertices.
 *
 * Filled triangles iterate across the bounding box and evaluate barycentric
 * edge signs against all three triangle edges.
 *
 * @param t Pointer to terminal context.
 * @param x0 Vertex 0 X coordinate.
 * @param y0 Vertex 0 Y coordinate.
 * @param x1 Vertex 1 X coordinate.
 * @param y1 Vertex 1 Y coordinate.
 * @param x2 Vertex 2 X coordinate.
 * @param y2 Vertex 2 Y coordinate.
 * @param color Packed 0x00RRGGBB color.
 * @param filled 1 for solid fill, 0 for wireframe outline.
 */
void term_triangle(term *t, int x0, int y0, int x1, int y1, int x2, int y2,
                   uint32_t color, int filled) {
  if (filled) {
    int minx = x0 < x1 ? x0 : x1;
    minx = minx < x2 ? minx : x2;
    int maxx = x0 > x1 ? x0 : x1;
    maxx = maxx > x2 ? maxx : x2;
    int miny = y0 < y1 ? y0 : y1;
    miny = miny < y2 ? miny : y2;
    int maxy = y0 > y1 ? y0 : y1;
    maxy = maxy > y2 ? maxy : y2;
    int d0 = sign3(x0, y0, x1, y1, x2, y2);
    for (int y = miny; y <= maxy; y++) {
      for (int x = minx; x <= maxx; x++) {
        int s1 = sign3(x, y, x0, y0, x1, y1);
        int s2 = sign3(x, y, x1, y1, x2, y2);
        int s3 = sign3(x, y, x2, y2, x0, y0);
        int neg = (s1 < 0) || (s2 < 0) || (s3 < 0);
        int pos = (s1 > 0) || (s2 > 0) || (s3 > 0);
        if (d0 <= 0 ? !neg : !pos)
          put(t, x, y, color, 255);
      }
    }
  } else {
    term_line(t, x0, y0, x1, y1, color);
    term_line(t, x1, y1, x2, y2, color);
    term_line(t, x2, y2, x0, y0, color);
  }
}

/**
 * @brief Draw a sequence of connected line segments through an array of points.
 *
 * @param t Pointer to terminal context.
 * @param pts Array of interleaved (x, y) coordinates.
 * @param n Number of vertices.
 * @param color Packed 0x00RRGGBB line color.
 */
void term_polyline(term *t, const int *pts, int n, uint32_t color) {
  if (n < 2)
    return;
  for (int i = 0; i < n - 1; i++)
    term_line(t, pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3],
              color);
}

/**
 * @brief Rasterize a filled polygon using an even-odd ray casting scanline
 * test.
 *
 * @param t Pointer to terminal context.
 * @param pts Array of interleaved (x, y) coordinates.
 * @param n Number of vertices (must be >= 3).
 * @param color Packed 0x00RRGGBB fill color.
 */
void term_polygon(term *t, const int *pts, int n, uint32_t color) {
  if (n < 3)
    return;
  int minx = pts[0], maxx = pts[0], miny = pts[1], maxy = pts[1];
  for (int i = 1; i < n; i++) {
    int x = pts[2 * i], y = pts[2 * i + 1];
    if (x < minx)
      minx = x;
    if (x > maxx)
      maxx = x;
    if (y < miny)
      miny = y;
    if (y > maxy)
      maxy = y;
  }
  for (int y = miny; y <= maxy; y++) {
    for (int x = minx; x <= maxx; x++) {
      int inside = 0;
      for (int i = 0, j = n - 1; i < n; j = i++) {
        int xi = pts[2 * i], yi = pts[2 * i + 1];
        int xj = pts[2 * j], yj = pts[2 * j + 1];
        if (((yi > y) != (yj > y)) &&
            (x < (xj - xi) * (y - yi) / (double)(yj - yi) + xi))
          inside = !inside;
      }
      if (inside)
        put(t, x, y, color, 255);
    }
  }
}

/**
 * @brief Fill a rectangle with a horizontal color gradient from left to right.
 *
 * @param t Pointer to terminal context.
 * @param x Left coordinate.
 * @param y Top coordinate.
 * @param w Rectangle width.
 * @param h Rectangle height.
 * @param left Packed 0x00RRGGBB color at the left edge.
 * @param top Unused parameter (preserved for multi-color rect API
 * compatibility).
 * @param right Packed 0x00RRGGBB color at the right edge.
 * @param bottom Unused parameter (preserved for multi-color rect API
 * compatibility).
 */
void term_rect_multi(term *t, int x, int y, int w, int h, uint32_t left,
                     uint32_t top, uint32_t right, uint32_t bottom) {
  (void)top;
  (void)bottom;
  int span = w > 1 ? w - 1 : 1;
  for (int j = y; j < y + h; j++) {
    for (int i = x; i < x + w; i++) {
      int d = i - x;
      uint32_t c = blend(left, right, (unsigned)((255 * d) / span));
      put(t, i, j, c, 255);
    }
  }
}

/**
 * @brief Overlay an ASCII character glyph onto a terminal cell with contrast
 * enforcement.
 *
 * Maps virtual coordinate y to character row (y >> 1). If the contrast
 * difference between foreground color and cell background is below
 * FONT_CONTRAST_MIN, flips the foreground to solid black or white to guarantee
 * legibility.
 *
 * @param t Pointer to terminal context.
 * @param x Column coordinate.
 * @param y Virtual row coordinate (row = y >> 1).
 * @param c ASCII character code to place.
 * @param fg Packed 0x00RRGGBB foreground font color.
 */
void term_glyph(term *t, int x, int y, unsigned char c, uint32_t fg) {
  if (!in_clip(t, x, y))
    return;
  int row = y >> 1;
  size_t off = (size_t)row * (size_t)t->cols + (size_t)x;
  if (c == ' ' || c == 0 || c == '\n' || c == '\r')
    return;
  /* Glyph cells render as fg = top over bg = bot in term_flush, so force
     the font color to contrast with this cell's background: legibility is
     paramount. */
  uint32_t bg = t->bot[off];
  unsigned bg_luma = luma(bg);
  unsigned fg_luma = luma(fg);
  unsigned delta = fg_luma > bg_luma ? fg_luma - bg_luma : bg_luma - fg_luma;
  if (delta < FONT_CONTRAST_MIN)
    fg = bg_luma >= 128u ? 0x000000u : 0xffffffu;
  t->ch[off] = c;
  t->top[off] = fg;
}

/**
 * @brief Render the framebuffer to stdout using optimized 24-bit ANSI truecolor
 * sequences.
 *
 * Iterates through each terminal cell. If a character glyph is present, prints
 * that character using foreground and background colors. Otherwise, if top and
 * bottom half-pixels match, prints a colored space. If they differ, prints the
 * Unicode upper half-block (▀) with top color as foreground and bottom color as
 * background. Batches output to minimize write syscalls and strips trailing
 * empty cells per row.
 *
 * @param t Pointer to terminal context to flush.
 */
void term_flush(term *t) {
  if (!t->top || !t->bot || !t->ch || t->cols <= 0 || t->rows <= 0)
    return;

  size_t cap = (size_t)t->cols * (size_t)t->rows * 32 + 256;
  if (cap > t->outcap) {
    char *out = realloc(t->out, cap);
    if (!out)
      return;
    t->out = out;
    t->outcap = cap;
  }
  char *o = t->out;
  size_t used = 0;
#define EMIT(...)                                                              \
  do {                                                                         \
    if (used < cap) {                                                          \
      int n = snprintf(o + used, cap - used, __VA_ARGS__);                     \
      if (n < 0) {                                                             \
        used = cap;                                                            \
      } else if ((size_t)n >= cap - used) {                                    \
        used = cap;                                                            \
      } else {                                                                 \
        used += (size_t)n;                                                     \
      }                                                                        \
    }                                                                          \
  } while (0)
  EMIT("\033[H");
  size_t soft_limit = cap > 512 ? cap - 512 : 0;
  for (int r = 0; r < t->rows && used < soft_limit; r++) {
    size_t base = (size_t)r * (size_t)t->cols;
    int last = t->cols - 1;
    while (last >= 0 && (t->ch[base + last] == 0) &&
           t->top[base + last] == t->bot[base + last] &&
           t->bot[base + last] == 0)
      last--;
    if (last < 0) {
      EMIT("\033[0m\033[K\r\n");
      continue;
    }
    uint32_t fg = 0, bg = 0;
    unsigned char ch = 255;
    for (int c = 0; c <= last; c++) {
      uint32_t f = t->top[base + c];
      uint32_t b = t->bot[base + c];
      unsigned char g = t->ch[base + c];
      uint32_t nf, nb;
      unsigned char ng;
      if (g == 0) {
        if (f == b) {
          nf = b;
          nb = b;
          ng = ' ';
        } else {
          nf = b;
          nb = f;
          ng = 0xC2;
        }
      } else {
        nf = f;
        nb = b;
        ng = g;
      }
      if (ng != ch || nf != fg || nb != bg) {
        EMIT("\033[38;2;%u;%u;%um\033[48;2;%u;%u;%um", (nf >> 16) & 0xff,
             (nf >> 8) & 0xff, nf & 0xff, (nb >> 16) & 0xff, (nb >> 8) & 0xff,
             nb & 0xff);
        fg = nf;
        bg = nb;
        ch = ng;
      }
      if (ng == 0xC2)
        EMIT("\xE2\x96\x80");
      else
        EMIT("%c", ng);
    }
    EMIT("\033[0m\033[K\r\n");
  }
#undef EMIT
  write(STDOUT_FILENO, o, used);
}
