"""
JIT engine for ORC-based CMA model using llvmlite's MCJIT compiler.

Loads LLVM bitcode at runtime, JIT-compiles it, and provides a ctypes wrapper
around the compiled ``run_cma_model`` function — a drop-in for the ``.so``-based
``pfun_cma_engine.run_cma_engine_c``.
"""

from __future__ import annotations

import ctypes
import logging
import threading
from pathlib import Path
from typing import Optional

import llvmlite.binding as llvm
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------

_PROJECT_ROOT: Path | None = None
_LOCK = threading.Lock()
_SINGLETON: JITEngine | None = None


def _resolve_project_root() -> Path:
    """Return the project root directory (two levels up from this file)."""
    global _PROJECT_ROOT
    if _PROJECT_ROOT is None:
        _PROJECT_ROOT = Path(__file__).resolve().parents[1]
    return _PROJECT_ROOT


def _default_bc_path() -> Path:
    """Return the default path to the LLVM bitcode file."""
    return _resolve_project_root() / "build" / "pfun_cma_engine.bc"


# ---------------------------------------------------------------------------
# JITEngine
# ---------------------------------------------------------------------------

class JITEngine:
    """JIT compiler for the CMA engine bitcode.

    Usage::

        engine = JITEngine()
        result = engine.run_cma_engine_c_jit(t, d, taup, taug_val, ...)
        engine.close()

    Or as a context manager::

        with JITEngine() as engine:
            result = engine.run_cma_engine_c_jit(t, d, taup, taug_val, ...)
    """

    def __init__(self, bc_path: Optional[str | Path] = None) -> None:
        if bc_path is None:
            bc_path = _default_bc_path()
        else:
            bc_path = Path(bc_path)

        # -- Validate bitcode path --------------------------------------------
        if not bc_path.exists():
            raise FileNotFoundError(
                f"Bitcode file not found: {bc_path}. "
                f"Build the project first (e.g. 'make -C {_resolve_project_root()} build')."
            )
        if not bc_path.is_file():
            raise IsADirectoryError(f"Expected a bitcode file, but path is a directory: {bc_path}")

        self._bc_path: Path = bc_path
        self._engine: llvm.ExecutionEngine | None = None
        self._run_cma_model: ctypes.CFUNCTYPE | None = None

        self._initialize_llvm()
        self._compile()

    # -- Private helpers ------------------------------------------------------

    @staticmethod
    def _initialize_llvm() -> None:
        """Ensure LLVM run-time initialisation has been performed."""
        # In llvmlite >= 0.48.0 initialisation is automatic; calls to
        # ``initialize()`` raise RuntimeError.  We attempt each call and
        # silently accept deprecation errors so the same code works across
        # llvmlite versions.
        for init_fn in (
            llvm.initialize,
            llvm.initialize_native_target,
            llvm.initialize_native_asmprinter,
        ):
            try:
                init_fn()
            except RuntimeError:
                #  Deprecated / already initialised – safe to skip.
                pass

    def _compile(self) -> None:
        """Load the bitcode and JIT-compile it with MCJIT."""
        # -- Read bitcode -----------------------------------------------------
        logger.debug("Loading bitcode from %s", self._bc_path)
        try:
            bc_bytes = self._bc_path.read_bytes()
        except OSError as exc:
            raise IOError(f"Failed to read bitcode file {self._bc_path}: {exc}") from exc

        # -- Parse module -----------------------------------------------------
        try:
            module = llvm.parse_bitcode(bc_bytes)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse LLVM bitcode from {self._bc_path}: {exc}"
            ) from exc

        logger.debug("Loaded module: %s", module.name if module.name else "(unnamed)")

        # -- Create target machine -------------------------------------------
        try:
            target = llvm.Target.from_default_triple()
            target_machine = target.create_target_machine()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create target machine for MCJIT compilation: {exc}"
            ) from exc

        # -- JIT compile ------------------------------------------------------
        try:
            self._engine = llvm.create_mcjit_compiler(module, target_machine)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create MCJIT compiler for module: {exc}"
            ) from exc

        # Finalise the compiled object so function addresses are resolvable.
        self._engine.finalize_object()

        # -- Resolve function address & build ctypes wrapper -------------------
        self._build_run_cma_model_ctypes()

    def _build_run_cma_model_ctypes(self) -> None:
        """Resolve ``run_cma_model`` and wrap it in a ctypes ``CFUNCTYPE``."""
        if self._engine is None:
            raise RuntimeError("JIT engine not initialised – cannot resolve symbols.")

        try:
            addr = self._engine.get_function_address("run_cma_model")
        except Exception as exc:
            raise RuntimeError(
                "Failed to locate 'run_cma_model' in the JIT-compiled module. "
                f"Ensure the bitcode contains this function. Original error: {exc}"
            ) from exc

        if addr == 0:
            raise RuntimeError(
                "JIT-compiled 'run_cma_model' resolved to a NULL address. "
                "The symbol may not have been exported."
            )

        logger.debug("run_cma_model JIT address: 0x%x", addr)

        # Create a ctypes function pointer with the correct signature.
        func_type = ctypes.CFUNCTYPE(
            None,  # return type: void
            ctypes.POINTER(ctypes.c_double),  # t
            ctypes.c_int,  # N
            ctypes.c_double,  # d
            ctypes.c_double,  # taup
            ctypes.c_double,  # taug_val
            ctypes.POINTER(ctypes.c_double),  # taug_vec
            ctypes.c_double,  # B
            ctypes.c_double,  # Cm
            ctypes.c_double,  # toff
            ctypes.POINTER(ctypes.c_double),  # tM
            ctypes.c_int,  # n_meals
            ctypes.POINTER(ctypes.c_int),  # seed
            ctypes.c_double,  # eps
            ctypes.POINTER(ctypes.c_double),  # out_L
            ctypes.POINTER(ctypes.c_double),  # out_m
            ctypes.POINTER(ctypes.c_double),  # out_c
            ctypes.POINTER(ctypes.c_double),  # out_a
            ctypes.POINTER(ctypes.c_double),  # out_I_S
            ctypes.POINTER(ctypes.c_double),  # out_I_E
            ctypes.POINTER(ctypes.c_double),  # out_G
            ctypes.POINTER(ctypes.c_double),  # out_g
        )
        self._run_cma_model = func_type(addr)

    # -- Public high-level API ------------------------------------------------

    def get_function_address(self, name: str) -> int:
        """Return the JIT-compiled address of *name*.

        Raises ``RuntimeError`` if the engine is not initialised or the
        symbol does not exist.
        """
        if self._engine is None:
            raise RuntimeError("JIT engine is not initialised.")
        try:
            return self._engine.get_function_address(name)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to obtain address for symbol '{name}': {exc}"
            ) from exc

    def run_cma_engine_c_jit(
        self,
        t: np.ndarray,
        d: float,
        taup: float,
        taug_val: float,
        taug_vec: Optional[np.ndarray] = None,
        B: float = 0.05,
        Cm: float = 0.0,
        toff: float = 0.0,
        tM: Optional[np.ndarray] = None,
        seed: Optional[int] = None,
        eps: float = 1e-18,
    ) -> dict[str, np.ndarray]:
        """Execute the CMA model via the JIT-compiled ``run_cma_model``.

        Parameters and return value match ``pfun_cma_engine.run_cma_engine_c``.
        """
        if self._run_cma_model is None:
            raise RuntimeError(
                "JIT engine has no run_cma_model wrapper. "
                "Has the engine been closed?"
            )

        # -- Parse inputs at the boundary -------------------------------------
        N = len(t)
        if tM is None:
            tM = np.array([7.0, 11.0, 17.5])
        n_meals = len(tM)

        # Prepare input pointer.
        t_ptr = t.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double)
        )
        tM_ptr = tM.astype(np.float64).ctypes.data_as(
            ctypes.POINTER(ctypes.c_double)
        )

        taug_ptr: Optional[ctypes.POINTER] = None
        if taug_vec is not None:
            taug_ptr = taug_vec.astype(np.float64).ctypes.data_as(
                ctypes.POINTER(ctypes.c_double)
            )

        # Seed handling: pass NULL if not provided.
        seed_val: Optional[ctypes.c_int] = None
        seed_ptr: Optional[ctypes.POINTER] = None
        if seed is not None:
            seed_val = ctypes.c_int(seed)
            seed_ptr = ctypes.pointer(seed_val)

        # -- Allocate output buffers ------------------------------------------
        out_L = np.zeros(N, dtype=np.float64)
        out_m = np.zeros(N, dtype=np.float64)
        out_c = np.zeros(N, dtype=np.float64)
        out_a = np.zeros(N, dtype=np.float64)
        out_I_S = np.zeros(N, dtype=np.float64)
        out_I_E = np.zeros(N, dtype=np.float64)
        out_G = np.zeros(N, dtype=np.float64)
        # g has shape (n_meals, N) so total elements = n_meals * N.
        out_g = np.zeros(n_meals * N, dtype=np.float64)

        # Map output buffers to typed pointers.
        L_ptr = out_L.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        m_ptr = out_m.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        c_ptr = out_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        a_ptr = out_a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        IS_ptr = out_I_S.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        IE_ptr = out_I_E.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        G_ptr = out_G.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        g_ptr = out_g.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

        # -- Execute JIT-compiled function ------------------------------------
        self._run_cma_model(
            t_ptr, N, d, taup, taug_val, taug_ptr,
            B, Cm, toff, tM_ptr, n_meals, seed_ptr, eps,
            L_ptr, m_ptr, c_ptr, a_ptr, IS_ptr, IE_ptr, G_ptr, g_ptr,
        )

        return {
            "G": out_G,
            "g": out_g.reshape((n_meals, N)),
            "I_E": out_I_E,
            "L": out_L,
            "m": out_m,
        }

    # -- Cleanup --------------------------------------------------------------

    def close(self) -> None:
        """Release JIT engine resources."""
        if self._engine is not None and not self._engine.closed:
            self._engine.close()
            logger.debug("JIT engine closed.")
        self._engine = None
        self._run_cma_model = None

    # -- Context manager support ----------------------------------------------

    def __enter__(self) -> JITEngine:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

def get_jit_engine(bc_path: Optional[str | Path] = None) -> JITEngine:
    """Return a shared ``JITEngine`` singleton.

    The engine is created once and reused.  Call ``.close()`` on the returned
    object to release resources when the engine is no longer needed.
    """
    global _SINGLETON
    if _SINGLETON is None:
        with _LOCK:
            if _SINGLETON is None:
                _SINGLETON = JITEngine(bc_path=bc_path)
    return _SINGLETON


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def jit_run_cma_engine_c(
    t: np.ndarray,
    d: float,
    taup: float,
    taug_val: float,
    taug_vec: Optional[np.ndarray] = None,
    B: float = 0.05,
    Cm: float = 0.0,
    toff: float = 0.0,
    tM: Optional[np.ndarray] = None,
    seed: Optional[int] = None,
    eps: float = 1e-18,
    bc_path: Optional[str | Path] = None,
) -> dict[str, np.ndarray]:
    """Convenience wrapper: create a temporary ``JITEngine``, run the model,
    and return the result dictionary.

    When *bc_path* is ``None`` the default ``build/pfun_cma_engine.bc`` is
    used.
    """
    with JITEngine(bc_path=bc_path) as engine:
        return engine.run_cma_engine_c_jit(
            t=t,
            d=d,
            taup=taup,
            taug_val=taug_val,
            taug_vec=taug_vec,
            B=B,
            Cm=Cm,
            toff=toff,
            tM=tM,
            seed=seed,
            eps=eps,
        )
