#ifndef TERM_H
#define TERM_H

#include <stdint.h>
#include <stddef.h>
#include <termios.h>

typedef struct {
    int cols, rows;
    int vw, vh;
    uint32_t *top, *bot;
    unsigned char *ch;
    int clip_x, clip_y, clip_w, clip_h, clip_on;
    int mouse;
    int fd;
    struct termios tio;
    char *out;
    size_t outcap;
} term;

void term_open(term *t, int mouse);
void term_close(term *t);
int term_resize(term *t);
int term_read(term *t, unsigned char *buf, int cap);
void term_set_clip(term *t, int x, int y, int w, int h);
void term_clip_off(term *t);
void term_fill(term *t, int x, int y, int w, int h, uint32_t color);
void term_line(term *t, int x0, int y0, int x1, int y1, uint32_t color);
void term_ellipse(term *t, int cx, int cy, int rx, int ry, uint32_t color, int filled);
void term_triangle(term *t, int x0, int y0, int x1, int y1, int x2, int y2, uint32_t color, int filled);
void term_polyline(term *t, const int *pts, int n, uint32_t color);
void term_polygon(term *t, const int *pts, int n, uint32_t color);
void term_rect_multi(term *t, int x, int y, int w, int h,
                     uint32_t left, uint32_t top, uint32_t right, uint32_t bottom);
void term_glyph(term *t, int x, int y, unsigned char c, uint32_t fg);
void term_flush(term *t);

#endif