/**
 * @file term.h
 * @brief Virtual terminal canvas with half-block 24-bit truecolor graphics.
 *
 * Provides a software-rasterized drawing surface rendered into terminal
 * emulators using ANSI 24-bit truecolor escape sequences. Each terminal
 * cell is split vertically into two sub-pixels using the Unicode upper
 * half-block glyph (U+2580, '▀'), doubling the effective vertical resolution
 * (virtual height = rows * 2). Also supports overlaying text glyphs with
 * automatic background contrast adjustment, clipping, mouse input, and raw
 * mode terminal configuration.
 */

#ifndef TERM_H
#define TERM_H

#include <stddef.h>
#include <stdint.h>
#include <termios.h>

/**
 * @struct term
 * @brief Terminal display state and raster buffer context.
 *
 * Maintains screen geometry, framebuffers for top and bottom sub-pixels,
 * character overlay buffer, active clipping rectangle, terminal I/O descriptors,
 * original termios state, and escape sequence output buffer.
 */
typedef struct {
  int cols;           /**< Terminal width in character columns. */
  int rows;           /**< Terminal height in character rows. */
  int vw;             /**< Virtual canvas width in pixels (equals cols). */
  int vh;             /**< Virtual canvas height in pixels (rows * 2). */
  uint32_t *top;      /**< Packed 0x00RRGGBB pixel buffer for upper sub-pixel / foreground. */
  uint32_t *bot;      /**< Packed 0x00RRGGBB pixel buffer for lower sub-pixel / background. */
  unsigned char *ch;  /**< Character overlay buffer; 0 indicates half-block graphics mode. */
  int clip_x;         /**< Left coordinate of active clip rectangle. */
  int clip_y;         /**< Top coordinate of active clip rectangle. */
  int clip_w;         /**< Width of active clip rectangle. */
  int clip_h;         /**< Height of active clip rectangle. */
  int clip_on;        /**< Non-zero if clipping is currently enabled. */
  int mouse;          /**< Non-zero if SGR extended mouse tracking is enabled. */
  int fd;             /**< File descriptor for terminal input (typically STDIN_FILENO). */
  struct termios tio; /**< Saved terminal attributes for restoration on exit. */
  char *out;          /**< Output buffer for batched ANSI escape sequences. */
  size_t outcap;      /**< Allocated capacity of output buffer in bytes. */
} term;

/**
 * @brief Initialize terminal in raw mode, query dimensions, and set up alternate screen.
 *
 * Configures the terminal file descriptor for non-canonical, unbuffered input
 * without echo, queries window size via TIOCGWINSZ, allocates top/bot/ch buffers,
 * switches to the alternate screen buffer, hides the cursor, and optionally enables
 * SGR 1006 mouse event reporting.
 *
 * @param t Pointer to terminal context to initialize.
 * @param mouse Non-zero to enable mouse tracking sequences (1000h + 1006h).
 */
void term_open(term *t, int mouse);

/**
 * @brief Restore terminal state and release allocated screen buffers.
 *
 * Disables mouse tracking, restores cursor visibility, switches back to the main
 * screen buffer, resets text attributes, frees pixel and output buffers, and restores
 * original termios settings.
 *
 * @param t Pointer to terminal context to close.
 */
void term_close(term *t);

/**
 * @brief Query current terminal window size and reallocate buffers if changed.
 *
 * Checks terminal dimensions via ioctl. If the column or row count has changed,
 * reallocates pixel and character buffers to match the new size.
 *
 * @param t Pointer to terminal context.
 * @return 1 if terminal was resized and buffers reallocated, 0 if unchanged or failed.
 */
int term_resize(term *t);

/**
 * @brief Read available input bytes from the terminal.
 *
 * Performs a read on the terminal file descriptor (in raw mode).
 *
 * @param t Pointer to terminal context.
 * @param buf Destination buffer for read bytes.
 * @param cap Maximum number of bytes to read into buf.
 * @return Number of bytes read, 0 on EOF, or -1 on error.
 */
int term_read(term *t, unsigned char *buf, int cap);

/**
 * @brief Set the active rectangular clipping region for raster operations.
 *
 * Future drawing calls will restrict pixel modifications to the intersection
 * of the canvas boundaries and this rectangle.
 *
 * @param t Pointer to terminal context.
 * @param x Left coordinate of clipping rectangle.
 * @param y Top coordinate of clipping rectangle.
 * @param w Width of clipping rectangle.
 * @param h Height of clipping rectangle.
 */
void term_set_clip(term *t, int x, int y, int w, int h);

/**
 * @brief Disable clipping, allowing drawing across the entire virtual canvas.
 *
 * @param t Pointer to terminal context.
 */
void term_clip_off(term *t);

/**
 * @brief Fill an axis-aligned rectangle with a solid color.
 *
 * @param t Pointer to terminal context.
 * @param x Left coordinate of rectangle.
 * @param y Top coordinate of rectangle.
 * @param w Width of rectangle.
 * @param h Height of rectangle.
 * @param color Packed 0x00RRGGBB fill color.
 */
void term_fill(term *t, int x, int y, int w, int h, uint32_t color);

/**
 * @brief Draw a straight line between two points using Bresenham's algorithm.
 *
 * @param t Pointer to terminal context.
 * @param x0 Starting X coordinate.
 * @param y0 Starting Y coordinate.
 * @param x1 Ending X coordinate.
 * @param y1 Ending Y coordinate.
 * @param color Packed 0x00RRGGBB line color.
 */
void term_line(term *t, int x0, int y0, int x1, int y1, uint32_t color);

/**
 * @brief Draw an ellipse (outline or solid fill) centered at (cx, cy).
 *
 * @param t Pointer to terminal context.
 * @param cx Center X coordinate.
 * @param cy Center Y coordinate.
 * @param rx Horizontal radius.
 * @param ry Vertical radius.
 * @param color Packed 0x00RRGGBB drawing color.
 * @param filled Non-zero for filled ellipse; zero for outline.
 */
void term_ellipse(term *t, int cx, int cy, int rx, int ry, uint32_t color,
                  int filled);

/**
 * @brief Draw a triangle (outline or filled) defined by three vertices.
 *
 * Filled triangles are rasterized using barycentric/edge-function half-plane tests.
 *
 * @param t Pointer to terminal context.
 * @param x0 Vertex 0 X coordinate.
 * @param y0 Vertex 0 Y coordinate.
 * @param x1 Vertex 1 X coordinate.
 * @param y1 Vertex 1 Y coordinate.
 * @param x2 Vertex 2 X coordinate.
 * @param y2 Vertex 2 Y coordinate.
 * @param color Packed 0x00RRGGBB triangle color.
 * @param filled Non-zero for filled triangle; zero for wireframe outline.
 */
void term_triangle(term *t, int x0, int y0, int x1, int y1, int x2, int y2,
                   uint32_t color, int filled);

/**
 * @brief Draw connected line segments through an array of points.
 *
 * @param t Pointer to terminal context.
 * @param pts Array of interleaved (x, y) vertex coordinates; length >= 2 * n.
 * @param n Number of vertices (points) in the polyline.
 * @param color Packed 0x00RRGGBB line color.
 */
void term_polyline(term *t, const int *pts, int n, uint32_t color);

/**
 * @brief Draw a filled convex or concave polygon.
 *
 * Rasterizes the polygon across its bounding box using an even-odd ray-casting rule.
 *
 * @param t Pointer to terminal context.
 * @param pts Array of interleaved (x, y) vertex coordinates; length >= 2 * n.
 * @param n Number of vertices in the polygon.
 * @param color Packed 0x00RRGGBB fill color.
 */
void term_polygon(term *t, const int *pts, int n, uint32_t color);

/**
 * @brief Fill a rectangle with a horizontal color gradient.
 *
 * Blends horizontally between left and right colors across the rectangle width.
 *
 * @param t Pointer to terminal context.
 * @param x Left coordinate of rectangle.
 * @param y Top coordinate of rectangle.
 * @param w Width of rectangle.
 * @param h Height of rectangle.
 * @param left Packed 0x00RRGGBB color at the left edge.
 * @param top Unused parameter preserved for multi-color rect API symmetry.
 * @param right Packed 0x00RRGGBB color at the right edge.
 * @param bottom Unused parameter preserved for multi-color rect API symmetry.
 */
void term_rect_multi(term *t, int x, int y, int w, int h, uint32_t left,
                     uint32_t top, uint32_t right, uint32_t bottom);

/**
 * @brief Draw a single character glyph over the canvas with automatic contrast.
 *
 * Sets the character at terminal row (y / 2), column x. Enforces a minimum
 * luminance difference against the background cell color for readability.
 *
 * @param t Pointer to terminal context.
 * @param x X coordinate (column).
 * @param y Y coordinate (in virtual pixels; mapped to row = y >> 1).
 * @param c ASCII character code to display.
 * @param fg Requested packed 0x00RRGGBB foreground color.
 */
void term_glyph(term *t, int x, int y, unsigned char c, uint32_t fg);

/**
 * @brief Flush canvas state to stdout as optimized 24-bit ANSI escape sequences.
 *
 * Converts the virtual screen buffer into ANSI truecolor escape sequences
 * using upper half-block characters (U+2580) where top/bottom sub-pixel colors
 * differ, spaces where both sub-pixels are identical, or overlaid glyph characters.
 * Emits terminal escape sequences with row-end trimming and batched writes.
 *
 * @param t Pointer to terminal context to flush.
 */
void term_flush(term *t);

#endif /* TERM_H */