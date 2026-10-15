import ctypes
from pathlib import Path
from typing import Dict, Optional
import numpy as np

# Load the shared library
try:
    _lib = ctypes.CDLL(Path(__file__).parent / "libpfun_cma_engine.so")
except OSError:
    # Fallback for absolute path if relative fails
    import pfun_path_helper as pph
    lib_path = Path(pph.get_lib_path("pfun_cma_engine"))
    _lib = ctypes.CDLL(lib_path.joinpath("libpfun_cma_engine.so"))

# --- Function Prototypes ---

# double exp_clipped(double x)
_exp_clipped = _lib.exp_clipped
_exp_clipped.argtypes = [ctypes.c_double]
_exp_clipped.restype = ctypes.c_double

# void run_cma_model(
#     const double* t, int N,
#     double d, double taup, double taug_val,
#     const double* taug_vec,
#     double B, double Cm, double toff,
#     const double* tM, int n_meals,
#     int* seed, double eps,
#     const double* A_raw,
#     double k_A, double A_thresh,
#     double gamma_A, double kappa_A,
#     double beta_A,
#     double eta_A, double tau_A,
#     double* out_L, double* out_m, double* out_c, double* out_c_mod,
#     double* out_A,
#     double* out_a, double* out_I_S, double* out_I_E,
#     double* out_I_E_eff,
#     double* out_s_A,
#     double* out_G, double* out_g
# )
_run_cma_model = _lib.run_cma_model
_run_cma_model.argtypes = [
    ctypes.POINTER(ctypes.c_double), # t
    ctypes.c_int,                    # N
    ctypes.c_double,                 # d
    ctypes.c_double,                 # taup
    ctypes.c_double,                 # taug_val
    ctypes.POINTER(ctypes.c_double), # taug_vec
    ctypes.c_double,                 # B
    ctypes.c_double,                 # Cm
    ctypes.c_double,                 # toff
    ctypes.POINTER(ctypes.c_double), # tM
    ctypes.c_int,                    # n_meals
    ctypes.POINTER(ctypes.c_int),    # seed
    ctypes.c_double,                 # eps
    ctypes.POINTER(ctypes.c_double), # A_raw
    ctypes.c_double,                 # k_A
    ctypes.c_double,                 # A_thresh
    ctypes.c_double,                 # gamma_A
    ctypes.c_double,                 # kappa_A
    ctypes.c_double,                 # beta_A
    ctypes.c_double,                 # eta_A
    ctypes.c_double,                 # tau_A
    ctypes.POINTER(ctypes.c_double), # out_L
    ctypes.POINTER(ctypes.c_double), # out_m
    ctypes.POINTER(ctypes.c_double), # out_c
    ctypes.POINTER(ctypes.c_double), # out_c_mod
    ctypes.POINTER(ctypes.c_double), # out_A
    ctypes.POINTER(ctypes.c_double), # out_a
    ctypes.POINTER(ctypes.c_double), # out_I_S
    ctypes.POINTER(ctypes.c_double), # out_I_E
    ctypes.POINTER(ctypes.c_double), # out_I_E_eff
    ctypes.POINTER(ctypes.c_double), # out_s_A
    ctypes.POINTER(ctypes.c_double), # out_G
    ctypes.POINTER(ctypes.c_double), # out_g
]
_run_cma_model.restype = None

def run_cma_engine_c(
    t: np.ndarray,
    d: float,
    taup: float,
    taug_val: float,
    taug_vec: Optional[np.ndarray] = None,
    B: float = 0.05,
    Cm: float = 0.0,
    toff: float = 0.0,
    tM: np.ndarray = np.array([7.0, 11.0, 17.5]),
    seed: Optional[int] = None,
    eps: float = 1e-18,
    # Activity parameters (all ignored when A_raw is None)
    A_raw: Optional[np.ndarray] = None,
    k_A: float = 5.0,
    A_thresh: float = 0.3,
    gamma_A: float = 0.15,
    kappa_A: float = 0.5,
    beta_A: float = 0.20,
    eta_A: float = 0.40,
    tau_A: float = 2.0,
) -> Dict[str, np.ndarray]:
    """Run the full CMA model engine.

    When ``A_raw`` is ``None`` (default), activity effects are disabled and the
    output is identical to the original model (backward compatible).

    Activity input note: ``A_raw`` must be pre-normalized to ``[0, 1]``, where
    ``0`` represents complete rest and ``1`` represents maximal exercise.  If
    your raw signal is cardiac output (``HR × SV_est``), normalize it first::

        A_raw_norm = (HR * SV_est - CO_rest) / (CO_max - CO_rest)

    where ``CO_rest ≈ 65`` and ``CO_max ≈ 260`` (bpm × fraction).
    """
    N = len(t)
    n_meals = len(tM)

    # Prepare input arrays
    t_ptr = t.astype(np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    tM_ptr = tM.astype(np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double))

    taug_ptr = None
    if taug_vec is not None:
        taug_ptr = taug_vec.astype(np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double))

    seed_val = ctypes.c_int(seed) if seed is not None else None
    seed_ptr = ctypes.pointer(seed_val) if seed_val is not None else None

    A_raw_ptr = None
    if A_raw is not None:
        A_raw_ptr = A_raw.astype(np.float64).ctypes.data_as(ctypes.POINTER(ctypes.c_double))

    # Pre-allocate output buffers
    out_L = np.zeros(N, dtype=np.float64)
    out_m = np.zeros(N, dtype=np.float64)
    out_c = np.zeros(N, dtype=np.float64)
    out_c_mod = np.zeros(N, dtype=np.float64)
    out_A = np.zeros(N, dtype=np.float64)
    out_a = np.zeros(N, dtype=np.float64)
    out_I_S = np.zeros(N, dtype=np.float64)
    out_I_E = np.zeros(N, dtype=np.float64)
    out_I_E_eff = np.zeros(N, dtype=np.float64)
    out_s_A = np.zeros(N, dtype=np.float64)
    out_G = np.zeros(N, dtype=np.float64)
    out_g = np.zeros(n_meals * N, dtype=np.float64)

    # Map output pointers
    def _dptr(arr):
        return arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))

    # Execute C function
    _run_cma_model(
        t_ptr, N, d, taup, taug_val, taug_ptr,
        B, Cm, toff, tM_ptr, n_meals, seed_ptr, eps,
        A_raw_ptr, k_A, A_thresh, gamma_A, kappa_A, beta_A, eta_A, tau_A,
        _dptr(out_L), _dptr(out_m), _dptr(out_c), _dptr(out_c_mod),
        _dptr(out_A), _dptr(out_a), _dptr(out_I_S), _dptr(out_I_E),
        _dptr(out_I_E_eff), _dptr(out_s_A), _dptr(out_G), _dptr(out_g),
    )

    return {
        "G": out_G,
        "g": out_g.reshape((n_meals, N)),
        "I_E": out_I_E,
        "I_E_eff": out_I_E_eff,
        "L": out_L,
        "m": out_m,
        "c": out_c,
        "c_mod": out_c_mod,
        "A": out_A,
        "s_A": out_s_A,
        "a": out_a,
        "I_S": out_I_S,
    }
