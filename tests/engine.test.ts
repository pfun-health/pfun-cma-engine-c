import { test } from "node:test";
import assert from "node:assert/strict";
import { MAX_POINTS, runCmaEngine } from "../pfun_cma_engine/ts/engine.ts";

const base = {
  modelParams: { d: 0, taup: 1, B: 0.05, Cm: 0, toff: 0, eps: 1e-18 },
  taug: 1,
  mealWidths: Float64Array.from([1, 1, 1]),
  meals: Float64Array.from([7, 11.5, 18]),
  activity: null,
  activityParams: {
    k_A: 5, A_thresh: 0.3, gamma_A: 0.15, kappa_A: 0.5, beta_A: 0.2,
    eta_A: 0.4, tau_A: 2,
  },
};
const grid = (n: number) =>
  Float64Array.from({ length: n }, (_, i) => (24 * i) / (n - 1));

test("runs and returns finite glucose series", () => {
  const r = runCmaEngine({ ...base, time: grid(97) });
  assert.equal(r.G.length, 97);
  assert.equal(r.g.length, 97 * 3);
  assert.ok(r.G.every(Number.isFinite));
});

test("is deterministic", () => {
  const a = runCmaEngine({ ...base, time: grid(49) });
  const b = runCmaEngine({ ...base, time: grid(49) });
  assert.deepEqual(a.G, b.G);
});

test("rejects bad point counts", () => {
  assert.throws(() => runCmaEngine({ ...base, time: grid(1) }), RangeError);
  assert.throws(
    () => runCmaEngine({ ...base, time: new Float64Array(MAX_POINTS + 1) }),
    RangeError,
  );
});
