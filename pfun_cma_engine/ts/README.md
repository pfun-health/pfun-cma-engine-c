## TypeScript surface

`engine.ts` is a typed Koffi binding for `run_cma_model` (`runCmaEngine`).
It loads `pfun_cma_engine/libpfun_cma_engine.so` (override with
`PFUN_CMA_ENGINE_LIB`); build it with `make libs`.

Used by `demos/ts/demo.ts`. Checks: `npm test`, `npm run typecheck`.
