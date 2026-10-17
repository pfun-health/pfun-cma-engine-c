# TCLUI PRD: `pfun-cma-tclui` — Toolkit-Agnostic UI Frontend for the PFun CMA Engine

**Status:** Approved (planning complete; Phase 0 in progress)
**Date:** 2026-09-06
**Owner:** pfun-health
**Scope:** A single-executable interactive frontend for `pfun_cma_engine.c` whose
user-interface *operations* are exhaustively specified independent of any
graphics implementation, with a Tcl/Tk reference backend packaged as a
standalone starpack.

This document is the **single source of truth** for the UI protocol.
`PROPOSED.md` carries a condensed summary and the roadmap integration.

---

## 1. Motivation & Context

`pfun-cma-engine-c` is a C numerical engine (activity-extended CMA
glucose-insulin model). It ships a Python ctypes wrapper and an interactive
Nuklear terminal demo (`demo.c`). There is **no portable, distributable UI**
and **no UI specification** decoupled from a rendering toolkit.

The activity pathway (`calc_A`, `calc_c_mod`, `calc_I_E_eff`, extended
`calc_G`/`run_cma_model`) introduced 8 new tunable parameters and 4 new
traceable signals. The UI must surface these.

**Constraint (user directive):** *"Make no assumption. Exhaustively define
user interface operations in a way that can be readily interpreted by existing
graphics implementations of all kinds."*

---

## 2. Goals / Non-Goals

### Goals

- A precise, exhaustive, toolkit-neutral **UI Operations Specification**
  (§6–§8) that *any* existing graphics system can conform to: Tk, Nuklear /
  terminal, GTK, Qt, curses, web, etc.
- A **reference backend** in Tcl/Tk (primary), packaged as a **single
  standalone executable** via `starpacker.tcl`.
- Parity with every capability of `demo.c` (variables, parameters, activity,
  help, keyboard + mouse + scroll).
- Activity parameters surfaced with sensible defaults, ranges, and steps.
- Numerical equivalence across backends and the Python wrapper.
- Nix flake development environment; existing Makefile/CMake/Docker/uv
  workflows unchanged.

### Non-Goals

- Replacing the C engine, Python wrapper, or LLVM pipeline.
- Implementing backends beyond Tk + terminal in this milestone (the spec must
  *allow* them).
- Persistence beyond simple scenario save/load and ASCII/CSV export.
- Real-time charting beyond the 512-point static time-series (no animation of
  live data streams).

---

## 3. User Personas & Use Cases

1. **Researcher / educator** — explores how parameters (incl. activity) move
   G / I_E over 24 h; uses keyboard + mouse; exports charts for docs.
2. **Exercise physiologist** — toggles activity,
   A_amp / k_A / A_thresh / gamma_A / kappa_A / beta_A / eta_A / tau_A;
   inspects glucose response vs. meal times.
3. **Field user (no Tcl/Tk installed)** — runs the standalone starpack on
   Windows / macOS / Linux.
4. **Developer / auditor** — runs the UI logic headless (no display) to diff
   against golden outputs (`DEMO_C_OUTPUT.md`, Python wrapper).

---

## 4. High-Level Architecture

The UI is split into two strictly separated layers. The **logic layer** is
pure (no graphics calls): it consumes normalized events, owns the canonical
state, and emits an abstract **frame** (render-command list). The **backend
layer** maps native input to events and renders frames.

```
native input ──► [input adaptor] ──► event (semantic op)
                                              │
                                              ▼
                ░░░░░░░░░░░ LOGIC (pure) ░░░░░░░
                ui_state + op ──► state transition
                state ──(auto_run/dirty)──► model run ──► results
                state + results ──► compose ──► FRAME
                ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░
                                              │
                                              ▼
FRAME ──► [view sink] ──► native drawing (Tk canvas / term.c / any)
```

Conforming backends implement only two interfaces:

- **`input_adaptor(native_event) → op`** — make every op in §6 reachable.
- **`view_sink(frame)`** — render every primitive in §8.

This makes the UI "readily interpretable by existing graphics implementations
of all kinds": any toolkit already knows how to draw lines, text, rectangles,
and read keys/pointers.

### Separation rule (enforceable)

`ui_core` (logic) must contain **no** calls to any graphics toolkit
(`package require Tk` forbidden inside it; canvas/ttk access forbidden). It
returns frames as nested Tcl lists and accepts op lists as input. This keeps
the logic unit-testable without a display and lets future backends reuse it
verbatim.

---

## 5. Canonical State Model

### 5.1 Scenario (persistent parameter set)

Fixed engine constants (not user-editable): `NMEALS=3`, `MAXPTS=512`,
`EPS=1e-18`, `seed=12345`. Semantics preserved from `demo.c`
(`scenario_default`, `scenario_params`).

| id  | name     | value | min  | max  | step | kind  |
| --- | -------- | ----- | ---- | ---- | ---- | ----- |
| p0  | d        | 1.0   | 0.0  | 4.0  | 0.1  | float |
| p1  | taup     | 1.2   | 0.0  | 4.0  | 0.1  | float |
| p2  | taug_val | 1.0   | 0.5  | 8.0  | 0.25 | float |
| p3  | B        | 0.05  | 0.01 | 0.5  | 0.01 | float |
| p4  | Cm       | 0.0   | 0.0  | 1.0  | 0.05 | float |
| p5  | toff     | 0.0   | 0.0  | 2.0  | 0.1  | float |
| p6  | tM[0]    | 7.0   | 0.0  | 24.0 | 0.5  | float |
| p7  | tM[1]    | 11.0  | 0.0  | 24.0 | 0.5  | float |
| p8  | tM[2]    | 17.5  | 0.0  | 24.0 | 0.5  | float |
| p9  | N pts    | 97    | 97   | 512  | 24   | int   |
| p10 | activity | 0     | 0    | 1    | 1    | bool  |
| p11 | A_amp    | 0.4   | 0.0  | 2.0  | 0.05 | float |
| p12 | k_A      | 5.0   | 0.5  | 20.0 | 0.5  | float |
| p13 | A_thresh | 0.3   | 0.0  | 1.0  | 0.05 | float |
| p14 | gamma_A  | 0.15  | 0.0  | 1.0  | 0.05 | float |
| p15 | kappa_A  | 0.5   | 0.0  | 3.0  | 0.1  | float |
| p16 | beta_A   | 0.20  | 0.0  | 2.0  | 0.05 | float |
| p17 | eta_A    | 0.40  | 0.0  | 2.0  | 0.05 | float |
| p18 | tau_A    | 2.0   | 0.1  | 6.0  | 0.1  | float |
| p19 | noise    | 0     | 0    | 1    | 1    | bool  |

### 5.2 Results (read-only, recomputed)

`t[N]` uniformly spaced over [0, 24]; plus `L, m, c, c_mod, A, a, I_S, I_E,
I_E_eff, s_A, G` (arrays of length N) and `g` (NMEALS×N). Produced solely by
`run_cma_model` with the current scenario.

### 5.3 View state

| id | meaning | init |
| ---- | --------- | ------ |
| `sel` | selected variable index 0..11 | 0 (G) |
| `panel` | focus region: `list` \| `params` | `list` |
| `pfocus` | focused parameter index −1..19 | −1 |
| `poff` | parameter scroll offset | 0 |
| `help` | help overlay visible? | 0 |
| `grid` | plot grid visible? | 1 |
| `mealmarks` | vertical markers at tM visible? | 1 |
| `xview` | time window `{t0 t1}` | `{0 24}` |
| `crosshair` | time for value readout, or none | none |
| `quit` | request application exit | 0 |

### 5.4 Runtime state

| id | meaning | init |
| ---- | --------- | ------ |
| `auto_run` | recompute on every param change | 1 |
| `dirty` | recompute before next frame | 1 |
| `frame` | monotonic frame counter | 0 |
| `toast` | transient message (string or none) | none |

**Computation rule:** a frame is rendered with current results. Before
rendering, if `dirty` (or `auto_run` and any parameter/view-visible change
since last run), the engine runs once and `dirty=0`. With `auto_run=1` this is
observably equivalent to `demo.c` line 819 (results always reflect the latest
parameters) while avoiding per-frame recompute.

---

## 6. Exhaustive User Operations (the controller contract)

Every operation has a canonical id, an exact state-transition semantics, a
default key binding, pointing binding(s), and is **backend-mandatory**
(§6.7). `Δp` = focused parameter's step; `CLAMP(x, lo, hi)` applies.

### 6.1 Focus & navigation

| op | semantics | keys | pointer |
| ---- | ----------- | ------ | --------- |
| `OP_FOCUS_VARLIST` | `panel=list; pfocus=−1` | `Tab` (in params) | click var region |
| `OP_FOCUS_PARAMS` | `panel=params; pfocus=0; poff=0` | `Tab` (in list) | click params region |
| `OP_NEXT_ITEM` | `list`: `sel=min(sel+1,11)`. `params`: `pfocus=min(pfocus+1,19)`; `poff` follows so `pfocus∈[poff, poff+ROWS−1]` | `j`, `J`, `↓` | scroll-down in var region |
| `OP_PREV_ITEM` | mirror of above | `k`, `K`, `↑` | scroll-up in var region |
| `OP_SELECT_VAR(i)` | `sel=i` (0≤i≤11); `panel=list` | optional `1..9` → 0..8, else mapped letters | click row i |
| `OP_SELECT_PARAM(i)` | `pfocus=i` (0≤i≤19); `panel=params` | — | click row i |
| `OP_HELP_TOGGLE` | `help=!help` | `h`, `H` | — |
| `OP_QUIT` | `quit=1`; backend tears down, restores terminal (TUI) / exits loop (GUI) | `q`, `Q`, `Esc` | window close |

### 6.2 Parameter editing

| op | semantics | keys |
| ---- | ----------- | ------ |
| `OP_PARAM_INC` | bool: `val=!val`; int (N): `val=CLAMP(val+step, 97, 512)`; float: `val=CLAMP(val+step, lo, hi)` | `→`, `+`, `=` |
| `OP_PARAM_DEC` | mirror | `←`, `−`, `-` |
| `OP_PARAM_FINE_INC` | float only: `+step/10` (int/bool unchanged); clamps | `Shift→`, `]` |
| `OP_PARAM_FINE_DEC` | mirror | `Shift←`, `[` |
| `OP_PARAM_SET_ABS(v)` | `val=CLAMP(v, lo, hi)` (N forced to valid int) | GUI text entry |
| `OP_PARAM_TOGGLE` | bool: `val=!val` (identical to INC for bool) | `Enter`, `Space` |
| `OP_PARAM_RESET_ONE` | focused param → its default | `r` (params focused) |
| `OP_N_PTS_SET(n)` | set p9 (97..512); recompute | — |
| `OP_MEAL_SET(i, t)` | set tM[i] to t∈[0,24] | — |

All parameter ops set `dirty=1` (then `auto_run` recomputes before the next
frame).

### 6.3 Model / computation

| op | semantics | keys |
|----|-----------|------|
| `OP_RUN_NOW` | run engine now; `dirty=0`; bump frame | `R` |
| `OP_AUTO_RUN_TOGGLE` | `auto_run=!auto_run`; when turning on, `dirty=1` | `a`, `A` |

### 6.4 Plot / inspection

| op | semantics | keys | pointer |
| ---- | ----------- | ------ | --------- |
| `OP_PLOT_SERIES_TOGGLE(j)` | when `sel==11 (g)`: hide/show meal series j∈0..2 | optional `m1/m2/m3` | click legend item |
| `OP_PLOT_GRID_TOGGLE` | `grid=!grid` | `g` | — |
| `OP_PLOT_MEALMARK_TOGGLE` | `mealmarks=!mealmarks` | `M` | — |
| `OP_PLOT_INFO_AT(x)` | armed crosshair at time x; status shows nearest-sample `t`, `value`; click clears | — | hover/click in plot |
| `OP_PLOT_ZOOM_X(f)` | zoom time window around view center by factor f (f>1 in, 0<f<1 out) | `i` in, `o` out | wheel in plot (down = in) |
| `OP_PLOT_PAN_X(dt)` | shift time window by dt; clamped to [0, 24] | `Shift←/→` | drag plot |
| `OP_PLOT_RESET_VIEW` | `xview={0 24}`; clear crosshair | `0` | — |

### 6.5 Persistence & export

| op | semantics | keys |
| ---- | ----------- | ------ |
| `OP_SCENARIO_SAVE(name)` | persist full scenario (p0..p19) to named slot (JSON) | `S` |
| `OP_SCENARIO_LOAD(name)` | restore scenario; run | `L` |
| `OP_SCENARIO_RESET` | scenario → defaults (§5.1); run | `D` |
| `OP_EXPORT_ASCII` | emit results in `demo.c --ascii` format to stdout/file | `e` |

### 6.6 Pointing-device primitives (exhaustive)

| primitive | normalized meaning |
| ----------- | -------------------- |
| `PTR_MOVE(x,y)` | update pointer state; if over plot and info-armed → hover readout |
| `PTR_DOWN(x,y,btn)` / `PTR_UP(x,y,btn)` | btn ∈ {left, right, middle}: region hit-test → `OP_SELECT_VAR`, `OP_SELECT_PARAM`, plot drag-pan, legend click |
| `PTR_SCROLL(x,y,delta)` | var region → `OP_NEXT/OP_PREV_ITEM`; params region → select param row; plot → `OP_PLOT_ZOOM_X` |
| `PTR_DRAG(x,y)` | plot region → `OP_PLOT_PAN_X` |

Backends may reach these operations via native gestures; the **operations**,
not the gestures, are normative.

### 6.7 Backend conformance checklist (mandatory minimum)

1. All ops in §6 are reachable by at least one native input path.
2. `OP_PARAM_SET_ABS` available (GUI: text field; TUI: type-ahead, or disabled
   with coarse + fine increment available).
3. All §8 render primitives emitted correctly.
4. `OP_QUIT` cleanly restores terminal (TUI) / exits the event loop (GUI).
5. Any single op → frame completes in one event-dispatch cycle (<100 ms goal).

---

## 7. Regions (layout contract)

Backends render five + two regions in this canonical geometry; exact mapping is
backend-defined (pixels for GUI, cells for TUI):

```
┌──────────────────────────────────────────────┐
│ R_HEADER  title "PFun CMA" + binding hint    │
├──────────┬───────────────────────────────────┤
│ R_VARLIST│ R_PLOT  (border, grid, title,     │
│ 12 rows, │  series, axes labels, legend,     │
│ selected │  meal markers, crosshair)         │
│ highlight│                                   │
├──────────┴───────────────────────────────────┤
│ R_PARAMS  "parameters" + up to 6 visible rows │
│ + R_STATUS  sel "n/12" │ toast / readout     │
└──────────────────────────────────────────────┘
 R_HELP  ── overlay box, centered, 3–6 lines
 R_TOAST ── transient line (errors, "saved", readout)
```

Mandatory rules:

- If the drawing surface is smaller than 20×12 cells (or equivalent): render
  only `R_TOAST` = `"terminal too small (need >= 20x12)"`.
- `R_VARLIST` shows `VAR_NAMES = {G, I_E, I_E_eff, L, m, c, c_mod, A, s_A, a,
  I_S, g}`.
- `R_PARAMS` row formats: bool → `name [x]`; `N pts` → `name %d`; else →
  `name %.4g`. Focus highlight only when `panel=params`.
- `R_PLOT` always shows the single selected variable; for `sel==11 (g)` it
  shows the 3 meal series with legend.

---

## 8. Render Commands (the view contract / frame)

A frame is an ordered command list. Sinks translate each command to native
draw calls (canvas items, cell glyphs, etc.). Commands:

| cmd | args | notes |
| ----- | ------ | ------- |
| `clear` | — | blank canvas / terminal backing |
| `clip` / `clip_off` | `(x,y,w,h)` | scissor for plot body |
| `fill` | `(x,y,w,h,color)` | region background |
| `frame` | `(x,y,w,h,color)` | outline rect (plot border, panels, help box) |
| `hline` | `(x0,x1,y,color)` | 1-thick line (grid, series segments, borders) |
| `vline` | `(x, y0, y1, color)` | 1-thick vertical line |
| `polyline` | `(pts, color)` | connected series; per meal-series color |
| `point` | `(x, y, glyph, color)` | discrete markers, crosshair, legend |
| `text` | `(x, y, str, color [, style])` | normal / bold / dim / highlighted |
| `select_row` | `(y, h, color)` | var-list selection / param focus band |
| `flush` | — | commit frame to device |

**Color model:** semantic keys only, mapped by backends to native palettes —
`border, grid, text, text_dim, select, highlight, series_1/2/3, warn, bg`.

**FRAME composition (exact per frame):**

1. `clear`
2. `R_HEADER`: `text(0,0, "PFun CMA j/k:sel Tab:panel +/-:adj R:run a:auto q:quit h:help", text)`
3. `R_VARLIST`: for v in 0..11 — `select_row` if `v==sel` (color depends on
   `panel==list`), `text(1, row, ">" or " " + name, highlight-or-text)`
4. `R_PLOT`:
   - `frame`; inset `clip`
   - if `sel==11`: 3 `polyline` (meal colors) + legend `text`s; else 1 `polyline`
   - if `grid`: 3 `hline` (quarter lines) + 1 `vline` (mid-point)
   - if `mealmarks`: `vline` at each visible tM
   - axis `text` labels: y-max (top-left), y-min (bottom-left), t0
     (bottom-left), t1 (bottom-right)
   - title `text` centered above the plot
   - if `crosshair`: `point` glyph + readout text in `R_STATUS`
   - `carortclip_off`
5. `R_PARAMS`: `fill`; `frame`; `text("parameters" | "parameters (editing)")`;
   rows 0..(ROWS−1) visible from `poff`: `select_row` if focused and
   `panel==params`; `text(name + value)`; bool rendered `[x]`/`[ ]`
6. `R_STATUS`: `text("n/12")` top-right when `panel==list`; readout if
   crosshair armed
7. `R_TOAST`: if non-empty, distinct-color `text` at a stable corner
8. if `help`: `fill` + `frame` overlay; 3+ binding lines
9. `flush`

The frame is fully determinable from `(state, results)` — testable headless.

---

## 9. Engine Bridge (C ↔ Tcl)

Hand-written extension `tclui/pfun_cma_tclui.c`. Chosen over Critcl because
Critcl compiles C at *first run*, which is hostile to a sealed starpack; the
hand-written `.so` ships inside the starpack. Critcl remains a dev-time
convenience via the Nix shell.

### Tcl command surface

- `pfun::engine version` → `1.0`
- `pfun::default scenario` → dict of all p0..p19 (single source for defaults)
- `pfun::run scenarioDict` → resultsDict
  - **input dict keys:** `d taup taug_val B Cm toff tM N seed eps A_raw
    k_A A_thresh gamma_A kappa_A beta_A eta_A tau_A`
    (`A_raw` optional; `tM` = NMEALS-list)
  - **output dict keys:** `t L m c c_mod A a I_S I_E I_E_eff s_A G g`
    (`g` = flat NMEALS·N list, row-major meal×time — matches the C API and
    `demo.c` `res-var` indexing)
- Granular wrappers (parity/testing): `pfun::calc_A`, `pfun::calc_c_mod`,
  `pfun::calc_I_E_eff`, `pfun::calc_G`, `pfun::calc_L` … mapping 1:1 to
  `pfun_cma_engine.h`.
- Memory: C allocates temporaries, builds Tcl lists, frees — valgrind-clean
  gate.

### Derivation of inputs (preserved from `demo.c`)

- `t[i] = 24·i/(N−1)`, i ∈ [0, N−1]
- `A_raw` from `A_amp` double-Gaussian at `(8.0, 1.5)` and `(17.0, 2.0)`
  (demo.c lines 150–154), only when `act_on`; else NULL
- `seed_ptr = noise ? &seed : NULL` with `seed=12345`
- `taug_vec = NULL`, `taug_value = taug_val`
- `eps = 1e-18`, `NMEALS = 3`

**Numerical rule:** extension output must match the Python wrapper on the same
scenario within relative tolerance 1e-12 (existing repo posture).

---

## 10. Tcl/Tk Reference Backend (primary)

Files under `tclui/`:

```
tclui/
├── pfun_cma_tclui.c      # engine bridge (§9)
├── main.tcl              # entry; package require Tk/ttk; wires backend
├── ui_core.tcl           # pure logic: state, ops, compose(frames) — NO Tk calls
├── backend_tk.tcl        # view_sink → ttk/canvas items; input_adaptor → ops
├── theme.tcl             # color / ttk theme mapping (§8 palette)
├── model.tcl             # pfun:: calls, results cache, auto_run/dirty
├── scenario.tcl          # defaults, save/load (JSON), export ASCII
└── pkgIndex.tcl
```

- `ui_core.tcl` is display-independent: consumes op lists, emits frames.
- Widgets: `ttk::Treeview`/canvas for the variable list; `ttk::Canvas` for the
  plot (cached polyline items, redrawn on frame change); `ttk::Scale` /
  `ttk::Spinbox` / `ttk::Checkbutton` parameter panel driven from
  `ui_core` frames; key bindings to §6 ops.
- Terminal parity: an optional `backend_tui.tcl` variant drives the same
  `ui_core` onto the existing `term.c`/Nuklear pipeline via a small C
  "view sink" (deferred; Phase 6, spec-level only here).

---

## 11. Packaging (standalone executable)

`starpacker.tcl` is vendored via git submodule at `packaging/starpacker`
(0BSD). It bundles `lib/sdx.kit` and platform `tclkit` runtimes in
`lib/runtimes/`.

Pipeline (cross-platform, per the starpacker procedure):

```
make tclui                        # builds tclui/pfun_cma_tclui.so
assemble tclui.vfs/               # main.tcl + lib/*.tcl + lib/pfun_cma_tclui.so + pkgIndex.tcl
tclkitsh sdx.kit qwrap tclui.vfs → tclui.kit
for runtime in runtimes/*:
    tclkitsh sdx wrap tclui -runtime $runtime → bin/tclui-<platform>
```

- One self-contained executable per platform, produced on a single machine:
  linux-x86_64, linux-ix86, darwin-x86_64, windows exe.
- Verification: `bin/tclui-<platform> --version` exits 0 and
  `--ascii --save out.md` reproduces `DEMO_C_OUTPUT.md` (headless
  conformance gate).
- Dev without packaging: `nix develop` → `tclsh tclui/main.tcl`.

**Note on tclkit:** not available in nixpkgs; starpacker vendors its own
tclkits, so packaging does not depend on a nixpkgs `tclkit` package.

---

## 12. Nix Flake (development environment)

```nix
{
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  outputs = { nixpkgs, ... }:
    let s = nixpkgs.legacyPackages;
        mk = sys: {
          devShells.${sys}.default = s.${sys}.mkShell {
            packages = with s.${sys}; [
              tcl tk tclPackages.critcl tclPackages.tcllib
              tclPackages.tclx tclPackages.bwidget
              gcc clang cmake python3
            ];
            shellHook = ''
              export TCLLIBPATH="${s.${sys}.tk}/${s.${sys}.tk.libdir}:$TCLLIBPATH"
            '';
          };
        };
    in { inherit (mk "x86_64-linux") devShells; };
}
```

`pkgs.tcl`, `pkgs.tk`, and `pkgs.tclPackages.*` are confirmed available in
nixpkgs (tclPackages PR #344716, merged).

---

## 13. Makefile Integration

New targets appended to `Makefile` (existing targets untouched):

- `tclui` — build `tclui/pfun_cma_tclui.so` (needs `pfun_cma_engine/libpfun_cma_engine.so`)
- `tclui-dev` — `nix develop --command tclsh tclui/main.tcl`
- `tclui-test` — run Tcl unit tests (headless `ui_core` + engine-bridge golden diff)
- `tclui-standalone` — invoke starpacker pipeline (§11)
- `tclui-clean` — remove build artifacts

---

## 14. Testing & Verification

| test | method | gate |
| ------ | -------- | ------ |
| Engine-bridge equality | same scenario via Tcl vs Python wrapper; rel-tol 1e-12 | pass |
| Golden ASCII parity | `tclui --ascii --save` diff vs freshly generated `DEMO_C_OUTPUT.md` | pass |
| Logic-layer unit tests | feed §6 op sequences; assert frames/states (no display) | pass |
| Backend conformance | automation drives ops; check all §6.7 items | pass |
| Memory | valgrind on `pfun_cma_tclui.so` against granular commands | clean |
| Packaging | `--version`, `--ascii` on produced starpack | pass |
| Cross-platform | starpack boots on each runtime target | 2 of 3 CI runners |

---

## 15. Milestones

| phase | deliverable | est. |
| ------- | ------------- | ------ |
| 0 | PRD accepted; `PROPOSED.md` updated; scaffold `tclui/`, flake, Makefile targets | 0.5 d |
| 1 | `pfun_cma_tclui.c` engine bridge + Tcl smoke test | 1–2 d |
| 2 | `ui_core.tcl` logic layer + op/state/frame unit tests | 1–2 d |
| 3 | Tk backend (`backend_tk.tcl`, `theme.tcl`, `main.tcl`) + `demo.c` feature parity | 2–3 d |
| 4 | Activity controls, scenario save/load, ASCII/CSV export, plot zoom/pan/meal markers | 1–2 d |
| 5 | starpacker packaging + headless conformance gates | 1 d |
| 6 | (optional) `backend_tui.tcl` onto `term.c` | 2 d |

---

## 16. Risks

| risk | mitigation |
| ------ | ----------- |
| `.so` injection into starkit awkward | pre-assemble full `.vfs` (incl. `.so`) before `qwrap`; test early in Phase 1 |
| tclkit age (starpacker ships 8.6.3 / windows runtimes) | confirm each runtime boots; keep kitcreator runtime drop-in path open via `lib/runtimes/` |
| Critcl not in final artifact | accepted; dev-only |
| Terminal-backend scope creep | Phase 6 optional; the spec alone satisfies "all graphics implementations" |

---

## 17. Out of Scope / Future Work

- Additional backends (GTK/Qt/web): spec is ready; implementation later.
- Live/animated data streams (>512 points, async feed).
- Two-component sensitization, hepatic counter-regulation, and other
  engine-side model changes (tracked in `PROPOSED.md`).
- Autosave / session restore / command-line scripted scenarios.
