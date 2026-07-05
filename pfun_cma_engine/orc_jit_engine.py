"""
ORC JIT engine for CMA model using llvmlite's ORC JIT compiler.

Loads LLVM bitcode at runtime, JIT-compiles it via ORC JIT (``LLJIT`` /
``JITLibraryBuilder``), and provides a ctypes wrapper around the compiled
``run_cma_model`` function — a drop-in for the ``.so``-based
``pfun_cma_engine.run_cma_engine_c``.

This is the **more advanced** JIT backend compared to ``jit_engine.py`` (which
uses the older MCJIT API).  The ORC variant offers better performance, support
for incremental compilation, and proper JIT library lifetime management.
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
_SINGLETON: ORCJITEngine | None = None


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
# ORCJITEngine
# ---------------------------------------------------------------------------

class ORCJITEngine:
    """ORC JIT compiler for the CMA engine bitcode.

    Usage::

        engine = ORCJITEngine()
        result = engine.run_cma_engine_c_jit(t, d, taup, taug_val, ...)
        engine.close()

    Or as a context manager::

        with ORCJITEngine() as engine:
            result = engine.run_cma_engine_c_jit(t, d, taup, taug_val, ...)
    """

    _lib_counter: int = 0
    """Class-level counter for generating unique JIT library names."""

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
            raise IsADirectoryError(
                f"Expected a bitcode file, but path is a directory: {bc_path}"
            )

        self._bc_path: Path = bc_path
        self._lljit: llvm.LLJIT | None = None
        self._tracker: llvm.ResourceTracker | None = None
        self._func_addr: int = 0
        self._run_cma_model: ctypes.CFUNCTYPE | None = None
        self._library_name: str = ""

        self._initialize_llvm()
        self._compile()

    # -- Private helpers ------------------------------------------------------

    @staticmethod
    def _initialize_llvm() -> None:
        """Ensure LLVM run-time initialisation has been performed.

        In llvmlite >= 0.48.0 initialisation is automatic; calls to
        ``initialize()`` raise RuntimeError.  We attempt each call and
        silently accept deprecation errors so the same code works across
        llvmlite versions.
        """
        for init_fn in (
            llvm.initialize,
            llvm.initialize_native_target,
            llvm.initialize_native_asmprinter,
        ):
            try:
                init_fn()
            except RuntimeError:
                # Deprecated / already initialised – safe to skip.
                pass

    def _compile(self) -> None:
        """Load the bitcode and JIT-compile it with ORC JIT."""
        # -- Read bitcode -----------------------------------------------------
        logger.debug("Loading bitcode from %s", self._bc_path)
        try:
            bc_bytes = self._bc_path.read_bytes()
        except OSError as exc:
            raise IOError(
                f"Failed to read bitcode file {self._bc_path}: {exc}"
            ) from exc

        # -- Parse module -----------------------------------------------------
        try:
            module = llvm.parse_bitcode(bc_bytes)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse LLVM bitcode from {self._bc_path}: {exc}"
            ) from exc

        logger.debug("Loaded module: %s", module.name if module.name else "(unnamed)")

        # -- Convert module to IR text (ORC JIT takes IR string) -------------
        ir_string = str(module)

        # -- Create LLJIT instance --------------------------------------------
        try:
            self._lljit = llvm.create_lljit_compiler()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create LLJIT compiler: {exc}. "
                "Ensure llvmlite >= 0.48.0 is installed."
            ) from exc

        # -- Generate a unique library name ----------------------------------
        ORCJITEngine._lib_counter += 1
        self._library_name = f"cma_lib_{ORCJITEngine._lib_counter}"

        # -- Build and link the JIT library ----------------------------------
        try:
            self._tracker = (
                llvm.JITLibraryBuilder()
                .add_ir(ir_string)
                .add_current_process()  # Required: provides C runtime / math symbols
                .export_symbol("run_cma_model")
                .link(self._lljit, self._library_name)
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to link JIT library '{self._library_name}': {exc}"
            ) from exc

        # -- Resolve function address -----------------------------------------
        try:
            self._func_addr = self._tracker["run_cma_model"]
        except KeyError:
            raise RuntimeError(
                "Failed to locate 'run_cma_model' in the JIT-compiled library. "
                "Ensure the bitcode exports this symbol. "
                f"Available symbols: {list(self._tracker._ResourceTracker__addresses.keys())}"
            ) from None

        if self._func_addr == 0:
            raise RuntimeError(
                "JIT-compiled 'run_cma_model' resolved to a NULL address. "
                "The symbol may not have been exported."
            )

        logger.debug("run_cma_model JIT address: 0x%x", self._func_addr)

        # -- Build ctypes wrapper ---------------------------------------------
        self._build_run_cma_model_ctypes()

    def _build_run_cma_model_ctypes(self) -> None:
        """Wrap the resolved function address in a ctypes ``CFUNCTYPE``."""
        if self._func_addr == 0:
            raise RuntimeError(
                "JIT function address is NULL – cannot build ctypes wrapper."
            )

        func_type = ctypes.CFUNCTYPE(
            None,  # return type: void
            ctypes.POINTER(ctypes.c_double),  # t
            ctypes.c_int,                     # N
            ctypes.c_double,                  # d
            ctypes.c_double,                  # taup
            ctypes.c_double,                  # taug_val
            ctypes.POINTER(ctypes.c_double),  # taug_vec
            ctypes.c_double,                  # B
            ctypes.c_double,                  # Cm
            ctypes.c_double,                  # toff
            ctypes.POINTER(ctypes.c_double),  # tM
            ctypes.c_int,                     # n_meals
            ctypes.POINTER(ctypes.c_int),     # seed
            ctypes.c_double,                  # eps
            ctypes.POINTER(ctypes.c_double),  # out_L
            ctypes.POINTER(ctypes.c_double),  # out_m
            ctypes.POINTER(ctypes.c_double),  # out_c
            ctypes.POINTER(ctypes.c_double),  # out_a
            ctypes.POINTER(ctypes.c_double),  # out_I_S
            ctypes.POINTER(ctypes.c_double),  # out_I_E
            ctypes.POINTER(ctypes.c_double),  # out_G
            ctypes.POINTER(ctypes.c_double),  # out_g
        )
        self._run_cma_model = func_type(self._func_addr)

    # -- Public high-level API ------------------------------------------------

    def get_function_address(self, name: str) -> int:
        """Return the JIT-compiled address of *name* from the linked library.

        Uses ``LLJIT.lookup()`` to resolve the symbol by library name.

        Raises ``RuntimeError`` if the JIT engine is closed, the library
        is not found, or the symbol does not exist.
        """
        if self._lljit is None:
            raise RuntimeError("LLJIT engine is not initialised.")
        if not self._library_name:
            raise RuntimeError("No JIT library has been linked.")
        try:
            tracker = self._lljit.lookup(self._library_name, name)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to obtain address for symbol '{name}' "
                f"in library '{self._library_name}': {exc}"
            ) from exc
        return tracker[name]

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
        """Execute the CMA model via the ORC JIT-compiled ``run_cma_model``.

        Parameters and return value match ``pfun_cma_engine.run_cma_engine_c``.
        """
        if self._run_cma_model is None:
            raise RuntimeError(
                "ORC JIT engine has no run_cma_model wrapper. "
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
        """Release JIT engine and library resources.

        The LLJIT engine's ``close()`` handles cleanup of all linked
        libraries, so we simply drop our reference to the resource tracker
        and then close the engine.  We do **not** call
        ``ResourceTracker._dispose()`` explicitly — doing so *before*
        closing the LLJIT can trigger a double-free assertion in LLVM's
        reference counting when the engine tears down.
        """
        # Drop the tracker reference first (avoids ordering issues during
        # LLJIT teardown).
        self._tracker = None

        # Close the LLJIT engine (this unloads all JIT libraries).
        if self._lljit is not None:
            try:
                if not self._lljit.closed:
                    self._lljit.close()
            except Exception:
                logger.debug("Error closing LLJIT (ignored).", exc_info=True)
            self._lljit = None
            logger.debug("LLJIT engine closed.")

        self._run_cma_model = None
        self._func_addr = 0

    # -- Context manager support ----------------------------------------------

    def __enter__(self) -> ORCJITEngine:
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

def get_orc_jit_engine(bc_path: Optional[str | Path] = None) -> ORCJITEngine:
    """Return a shared ``ORCJITEngine`` singleton.

    The engine is created once and reused.  Call ``.close()`` on the returned
    object to release resources when the engine is no longer needed.
    """
    global _SINGLETON
    if _SINGLETON is None:
        with _LOCK:
            if _SINGLETON is None:
                _SINGLETON = ORCJITEngine(bc_path=bc_path)
    return _SINGLETON


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def orc_jit_run_cma_engine_c(
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
    """Convenience wrapper: create a temporary ``ORCJITEngine``, run the model,
    and return the result dictionary.

    When *bc_path* is ``None`` the default ``build/pfun_cma_engine.bc`` is
    used.
    """
    with ORCJITEngine(bc_path=bc_path) as engine:
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
