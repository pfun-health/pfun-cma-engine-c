import koffi from "koffi";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const MAX_POINTS = 768;

export type ActivityParams = {
  k_A: number;
  A_thresh: number;
  gamma_A: number;
  kappa_A: number;
  beta_A: number;
  eta_A: number;
  tau_A: number;
};

export type ModelParams = {
  d: number;
  taup: number;
  B: number;
  Cm: number;
  toff: number;
  eps: number;
};

export type EngineInput = {
  time: Float64Array;
  modelParams: ModelParams;
  /** Scalar taug used when `mealWidths` is not given per-meal. */
  taug: number;
  mealWidths: Float64Array;
  meals: Float64Array;
  activity: Float64Array | null;
  activityParams: ActivityParams;
};

export type EngineOutput = {
  L: Float64Array;
  m: Float64Array;
  c: Float64Array;
  c_mod: Float64Array;
  A: Float64Array;
  a: Float64Array;
  I_S: Float64Array;
  I_E: Float64Array;
  I_E_eff: Float64Array;
  s_A: Float64Array;
  G: Float64Array;
  /** Per-meal glucose components, flattened row-major (meal * N + i). */
  g: Float64Array;
};

const SIGNATURE =
  "void run_cma_model(const double *t, int N, double d, double taup, double taug_val, const double *taug_vec, double B, double Cm, double toff, const double *tM, int n_meals, int *seed, double eps, const double *A_raw, double k_A, double A_thresh, double gamma_A, double kappa_A, double beta_A, double eta_A, double tau_A, double *out_L, double *out_m, double *out_c, double *out_c_mod, double *out_A, double *out_a, double *out_I_S, double *out_I_E, double *out_I_E_eff, double *out_s_A, double *out_G, double *out_g)";

type RunFn = (...args: unknown[]) => void;
let cached: { path: string; fn: RunFn } | undefined;

export function defaultRepoRoot(): string {
  return resolve(dirname(fileURLToPath(import.meta.url)), "../..");
}

export function libraryPath(): string {
  return (
    process.env.PFUN_CMA_ENGINE_LIB ??
    resolve(defaultRepoRoot(), "pfun_cma_engine/libpfun_cma_engine.so")
  );
}

function load(): RunFn {
  const path = libraryPath();
  if (cached?.path === path) return cached.fn;
  if (!existsSync(path)) {
    throw new Error(`Engine library not found at ${path}; run \`make libs\`.`);
  }
  const fn = koffi.load(path).func(SIGNATURE) as RunFn;
  cached = { path, fn };
  return fn;
}

export function runCmaEngine(input: EngineInput): EngineOutput {
  const n = input.time.length;
  if (n < 2 || n > MAX_POINTS) {
    throw new RangeError(`time must have 2..${MAX_POINTS} points (got ${n})`);
  }
  if (input.mealWidths.length !== input.meals.length) {
    throw new RangeError("mealWidths and meals must have equal length");
  }
  const run = load();
  const { modelParams: p, activityParams: a } = input;
  const out = Array.from({ length: 11 }, () => new Float64Array(n));
  const g = new Float64Array(n * input.meals.length);
  run(
    input.time, n, p.d, p.taup, input.taug, input.mealWidths, p.B, p.Cm,
    p.toff, input.meals, input.meals.length, null, p.eps, input.activity,
    a.k_A, a.A_thresh, a.gamma_A, a.kappa_A, a.beta_A, a.eta_A, a.tau_A,
    ...out, g,
  );
  const [L, m, c, c_mod, A, a_, I_S, I_E, I_E_eff, s_A, G] = out;
  return { L, m, c, c_mod, A, a: a_, I_S, I_E, I_E_eff, s_A, G, g };
}
