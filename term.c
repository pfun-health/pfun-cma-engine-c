#include "term.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <poll.h>
#include <sys/ioctl.h>

#define CELL_HALF 0x2580u

static uint32_t blend(uint32_t d, uint32_t s, unsigned a) {
    if (a >= 255) return s;
    if (a == 0) return d;
    unsigned dr = (d >> 16) & 0xff, dg = (d >> 8) & 0xff, db = d & 0xff;
    unsigned sr = (s >> 16) & 0xff, sg = (s >> 8) & 0xff, sb = s & 0xff;
    unsigned nr = (dr * (255 - a) + sr * a) / 255;
    unsigned ng = (dg * (255 - a) + sg * a) / 255;
    unsigned nb = (db * (255 - a) + sb * a) / 255;
    return (nr << 16) | (ng << 8) | nb;
}

static int in_clip(term *t, int x, int y) {
    return x >= 0 && y >= 0 && x < t->vw && y < t->vh &&
           (!t->clip_on || (x >= t->clip_x && y >= t->clip_y &&
            x < t->clip_x + t->clip_w && y < t->clip_y + t->clip_h));
}

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

static void alloc_screen(term *t) {
    size_t n = (size_t)t->cols * (size_t)t->rows;
    t->top = realloc(t->top, n * sizeof(uint32_t));
    t->bot = realloc(t->bot, n * sizeof(uint32_t));
    t->ch = realloc(t->ch, n);
    memset(t->top, 0, n * sizeof(uint32_t));
    memset(t->bot, 0, n * sizeof(uint32_t));
    memset(t->ch, 0, n);
    t->vw = t->cols;
    t->vh = t->rows * 2;
}

static int query_size(int fd, int *cols, int *rows) {
    struct winsize ws;
    if (ioctl(fd, TIOCGWINSZ, &ws) < 0 || ws.ws_col == 0 || ws.ws_row == 0)
        return 0;
    *cols = (int)ws.ws_col;
    *rows = (int)ws.ws_row;
    return 1;
}

void term_open(term *t, int mouse) {
    memset(t, 0, sizeof(*t));
    t->fd = STDIN_FILENO;
    t->mouse = mouse;
    tcgetattr(t->fd, &t->tio);
    struct termios raw = t->tio;
#ifdef __APPLE__
    /* macOS lacks cfmakeraw; set equivalent flags */
    raw.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL | IXON);
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
    if (!query_size(t->fd, &t->cols, &t->rows)) {
        t->cols = 80;
        t->rows = 24;
    }
    alloc_screen(t);
#define ESTR "\033[?1049h\033[?25l\033[2J\033[H"
    write(STDOUT_FILENO, ESTR, sizeof(ESTR) - 1);
    if (mouse)
        write(STDOUT_FILENO, "\033[?1000h\033[?1006h", 16);
#undef ESTR
}

void term_close(term *t) {
    if (t->mouse)
        write(STDOUT_FILENO, "\033[?1000l\033[?1006l", 16);
    write(STDOUT_FILENO, "\033[0m\033[?25h\033[?1049l", sizeof("\033[0m\033[?25h\033[?1049l") - 1);
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

int term_resize(term *t) {
    int c, r;
    if (!query_size(t->fd, &c, &r))
        return 0;
    if (c == t->cols && r == t->rows)
        return 0;
    t->cols = c;
    t->rows = r;
    alloc_screen(t);
    return 1;
}

int term_read(term *t, unsigned char *buf, int cap) {
    ssize_t n = read(t->fd, buf, (size_t)cap);
    return (int)n;
}

void term_set_clip(term *t, int x, int y, int w, int h) {
    t->clip_on = 1;
    t->clip_x = x;
    t->clip_y = y;
    t->clip_w = w < 0 ? 0 : w;
    t->clip_h = h < 0 ? 0 : h;
}

void term_clip_off(term *t) {
    t->clip_on = 0;
}

void term_fill(term *t, int x, int y, int w, int h, uint32_t color) {
    for (int j = y; j < y + h; j++)
        for (int i = x; i < x + w; i++)
            put(t, i, j, color, 255);
}

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

void term_ellipse(term *t, int cx, int cy, int rx, int ry, uint32_t color, int filled) {
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

static int sign3(int x0, int y0, int x1, int y1, int x2, int y2) {
    return (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
}

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

void term_polyline(term *t, const int *pts, int n, uint32_t color) {
    if (n < 2)
        return;
    for (int i = 0; i < n - 1; i++)
        term_line(t, pts[2 * i], pts[2 * i + 1], pts[2 * i + 2], pts[2 * i + 3], color);
}

void term_polygon(term *t, const int *pts, int n, uint32_t color) {
    if (n < 3)
        return;
    int minx = pts[0], maxx = pts[0], miny = pts[1], maxy = pts[1];
    for (int i = 1; i < n; i++) {
        int x = pts[2 * i], y = pts[2 * i + 1];
        if (x < minx) minx = x;
        if (x > maxx) maxx = x;
        if (y < miny) miny = y;
        if (y > maxy) maxy = y;
    }
    for (int y = miny; y <= maxy; y++) {
        for (int x = minx; x <= maxx; x++) {
            int inside = 0;
            for (int i = 0, j = n - 1; i < n; j = i++) {
                int xi = pts[2 * i], yi = pts[2 * i + 1];
                int xj = pts[2 * j], yj = pts[2 * j + 1];
                if (((yi > y) != (yj > y)) && (x < (xj - xi) * (y - yi) / (double)(yj - yi) + xi))
                    inside = !inside;
            }
            if (inside)
                put(t, x, y, color, 255);
        }
    }
}

void term_rect_multi(term *t, int x, int y, int w, int h,
                     uint32_t left, uint32_t top, uint32_t right, uint32_t bottom) {
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

void term_glyph(term *t, int x, int y, unsigned char c, uint32_t fg) {
    if (!in_clip(t, x, y))
        return;
    int row = y >> 1;
    size_t off = (size_t)row * (size_t)t->cols + (size_t)x;
    if (c == ' ' || c == 0 || c == '\n' || c == '\r')
        return;
    t->ch[off] = c;
    t->top[off] = fg;
}

void term_flush(term *t) {
    size_t cap = (size_t)t->cols * (size_t)t->rows * 32 + 256;
    if (cap > t->outcap) {
        t->out = realloc(t->out, cap);
        t->outcap = cap;
    }
    char *o = t->out;
    size_t used = 0;
#define EMIT(...) do { int n = snprintf(o + used, cap - used, __VA_ARGS__); if (n > 0) used += (size_t)n; } while (0)
    EMIT("\033[H");
    for (int r = 0; r < t->rows && used < cap - 512; r++) {
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
                EMIT("\033[38;2;%u;%u;%um\033[48;2;%u;%u;%um",
                     (nf >> 16) & 0xff, (nf >> 8) & 0xff, nf & 0xff,
                     (nb >> 16) & 0xff, (nb >> 8) & 0xff, nb & 0xff);
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