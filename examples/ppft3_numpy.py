"""Example of the 3D Pseudo-Polar Fourier Transform with default backend."""

import numpy as np

from ppftpy import ppft3

data = np.random.default_rng().random((32, 32, 32))

transformed = ppft3(data)
