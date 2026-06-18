# coding: utf-8
import numpy as np
import pandas as pd
from pfun_cma_engine import pfun_cma_engine as pce


def print_docstring():
    print(pce.run_cma_engine_c.__doc__)


def compute_as_dataframe():
    t = np.linspace(0, 24, 13)
    soln = pce.run_cma_engine_c(t, 1.0, 1.2, 1.0)
    soln.pop("g")
    soln["t"] = t
    df = pd.DataFrame(soln, index=t)
    print(df.to_markdown())
    return df


if __name__ == "__main__":
    print_docstring()
    df = compute_as_dataframe()
