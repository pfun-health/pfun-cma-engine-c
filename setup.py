#!/usr/bin/env python3
"""Setup script for pfun-cma-engine C extension.
This script ensures the C extension is built into the correct package directory
and that the resulting shared library can be imported by the Python package.
"""

from pathlib import Path
from setuptools import setup, Extension

# Get the absolute path to src directory for include paths
src_dir = Path("src").resolve()

# Define the package directory where the compiled extension will be placed
package_dir = Path(__file__).parent / "pfun_cma_engine"

# Define the extension module
# The extension will be built as pfun_cma_engine/pfun_cma_engine.so
ext_modules = [
    Extension(
        str(package_dir / "libpfun_cma_engine.so"),
        sources=list(Path("src").glob("*.c")),
        extra_compile_args=["-O3", "-march=native"],
        include_dirs=[str(src_dir), ],
    )
]

setup(
    name="pfun-cma-engine",
    version="0.1.0",
    ext_modules=ext_modules,
    include_package_data=True,
    zip_safe=False,
    # Include the header file in package data for C extension
    package_data={"pfun_cma_engine": ["*.so", "*.a", "*.c", "*.h", "*.py"]},
)
