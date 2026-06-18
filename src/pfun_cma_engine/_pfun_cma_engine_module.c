#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "pfun_cma_engine.h"

// Minimal module with no methods yet. This provides the required
// PyInit_pfun_cma_engine symbol so the compiled extension can be
// imported. Bindings to the C functions can be added here later.

static PyMethodDef module_methods[] = {
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "pfun_cma_engine",
    "PFun CMA Engine C extension",
    -1,
    module_methods
};

PyMODINIT_FUNC
PyInit_pfun_cma_engine(void)
{
    PyObject *m = PyModule_Create(&moduledef);
    if (!m) return NULL;
    return m;
}
