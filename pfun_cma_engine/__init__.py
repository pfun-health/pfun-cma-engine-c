"""Top-level package for pfun_cma_engine.

This package provides a C extension built from ``src/pfun_cma_engine.c``.
The compiled shared library is exposed as ``pfun_cma_engine.pfun_cma_engine``.
Importing the extension here makes it available as ``pfun_cma_engine``
when the package is imported.
"""

# Import the compiled extension module so that users can simply
# ``import pfun_cma_engine`` and access the symbols directly.
try:
	from . import pfun_cma_engine as _ext  # noqa: F401
except Exception as exc:  # pragma: no cover
	# If the extension could not be imported (e.g., missing build tools),
	# expose a clear error message while keeping the package importable.
	raise ImportError(
		"Failed to import the C extension 'pfun_cma_engine.pfun_cma_engine'. "
		"Ensure the extension is built (run `pip install .` or `python -m pip install -e .`)."
	) from exc
