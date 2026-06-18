from setuptools import setup, Extension

ext_modules = [
    Extension(
        "pfun_cma_engine.pfun_cma_engine",
        sources=[
            "src/pfun_cma_engine.c",
        ],
        extra_compile_args=["-O3", "-march=native"],
        libraries=["m"],
    )
]

setup(
    name="pfun-cma-engine-c",
    version="0.1.0",
    packages=["pfun_cma_engine"],
    package_dir={"": "pfun_cma_engine"},
    ext_modules=ext_modules,
)
