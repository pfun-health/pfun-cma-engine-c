# coding: utf-8
import numpy as np
import pandas as pd
from pfun_cma_engine import pfun_cma_engine
print(pfun_cma_engine.run_cma_engine_c.__doc__)
soln = pfun_cma_engine.run_cma_engine_c(np.linspace(0, 24, 12), 1.0, 1.2, 1.0)
soln.pop("g")
df = pd.DataFrame(soln)
df
