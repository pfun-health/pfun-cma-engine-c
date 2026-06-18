#!/usr/bin/env python3
"""Setup script for pfun-cma-engine C extension.
This script ensures the C extension is built into the correct package directory
and that the resulting shared library can be imported by the Python package.
"""

from pathlib import Path
from setuptools import setup, Extension

# Define the extension module
# The extension will be built as pfun_cma_engine/pfun_cma_engine.so
ext_modules = [
    Extension(
        str(Path("pfun_cma_engine") / "pfun_cma_engine.so"),
        sources=[str(Path("src") / "pfun_cma_engine.c")],
        extra_compile_args=["-O3", "-march=native"],
        include_dirs=[str(Path("src").resolve())],
    )
]

setup(
    name="pfun-cma-engine",
    version="0.1.0",
    packages=["pfun_cma_engine"],
    #package_dir={"": "pfun_cma_engine"},
    ext_modules=ext_modules,
    include_package_data=True,
    zip_safe=False,
)
