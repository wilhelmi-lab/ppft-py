"""Test data generator CLI.

This CLI generates test matrices that can be used to verify the
correctness of the Python implementation. It generates test arrays that
are passed to the original MATLAB implementation. Both input and output
data are stored on disk to be used within the regression test suite.

See Also
--------
- [MATLAB Engine on GitHub](https://github.com/mathworks/matlab-engine-for-python/)
- [MATLAB Engine on PyPI](https://pypi.org/project/matlabengine/)
- [MATLAB Compatibility Overview](https://www.mathworks.com/support/requirements/python-compatibility.html)

Notes
-----
To automatically run this CLI with its dependencies, you can use uv.
This script additionally requires MATLAB installed on your system.
To generate 2D test data with sizes 2, 4, and 8, run:

```bash
uv run --with matlabengine generate_test_data.py 2 4 8 --dim 2
```

This installs the most recent version of MATLAB Engine and assumes it is
installed at the default installation path. In case you want to use an
older version of MATLAB Engine, you can explicitly set the required
version:

```bash
uv run --with matlabengine==24.2.2 generate_test_data.py 2 4 8 --dim 2
```
"""

# /// script
# requires-python = ">=3.10,<4"
# dependencies = [
#   "numpy==2.2.3",
#   "cyclopts==3.10.1",
#   "httpx==0.28.1",
#   "tqdm==4.67.1",
# ]
# ///

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final, Literal

from cyclopts import App, Group, Parameter, validators
from cyclopts.types import (  # noqa: TC002
    URL,
    NonNegativeInt,
    PositiveInt,
    ResolvedDirectory,
    ResolvedExistingDirectory,
)

if TYPE_CHECKING:
    import httpx
    from numpy.random import Generator
    from numpy.typing import NDArray

Dimension = Literal[2, 3]
MatrixType = Literal["ones", "zeros", "gradient", "random"]

DEFAULT_MATRIX_TYPES: Final[set[MatrixType]] = {"ones", "zeros", "random", "gradient"}
HTTP_DOWNLOAD_TIMEOUT: Final = 10

# Parameter groups.
matlab_source_group = Group(
    "MATLAB source code (Choose one)", validator=validators.MutuallyExclusive()
)

# Parameters.
InputDirectory = Annotated[
    ResolvedExistingDirectory | None, Parameter(group=matlab_source_group)
]
DownloadUrl = Annotated[URL | None, Parameter(group=matlab_source_group)]
MatrixTypes = Annotated[set[MatrixType], Parameter(negative="")]
Functions = Annotated[set[str], Parameter(negative="")]


@dataclass(frozen=True, slots=True, kw_only=True)
class DefaultConfiguration:
    """TODO."""

    download_url: str
    functions: set[str]
    nargout: int


# Default configurations.
DEFAULT_CONFIGS: Final[dict[Dimension, DefaultConfiguration]] = {
    2: DefaultConfiguration(
        download_url="https://github.com/ShkolniskyLab/PPFT2D/archive/69eea1d/main.zip",
        functions={"slowPPFT", "PPFT", "OptimizedPPFT"},
        nargout=2,
    ),
    3: DefaultConfiguration(
        download_url="https://github.com/ShkolniskyLab/PPFT3D/archive/1385e31/main.zip",
        functions={"slowppft3", "ppft3_ref", "ppft3"},
        nargout=1,
    ),
}

app = App()


@app.default
def main(  # noqa: PLR0913
    sizes: Annotated[set[int], Parameter(negative="")],
    *,
    dim: Dimension,
    matrix_types: MatrixTypes = DEFAULT_MATRIX_TYPES,
    functions: Functions | None = None,
    download_url: DownloadUrl = None,
    download_dir: ResolvedDirectory = Path("matlab_source"),
    input_dir: InputDirectory = None,
    output_dir: ResolvedDirectory = Path("test_data"),
    seed: NonNegativeInt | None = None,
    nargout: PositiveInt | None = None,
) -> None:
    """Generate PPFT output based on the reference MATLAB code.

    Parameters
    ----------
    sizes
        Size of matrices to generate.
    dim
        Number of dimensions for the matrices.
    functions
        Function names, case-sensitive. If empty, the known original
        MATLAB functions will be used ('slowPPFT', 'PPFT',
        'OptimizedPPFT' for PPFT2D and 'slowppft3', 'ppft3_ref', 'ppft3'
        for PPFT3D).
    matrix_types
        Matrix content to be generated and transformed with original
        MATLAB functions.
    download_url
        Download URL to the MATLAB source code. If empty, the known
        default URLs will be used.
    download_dir
        Output directory for downloaded MATLAB source code.
    input_dir
        Base directory containing the MATLAB code.
    output_dir
        Directory to save the generated test data.
    seed
        Random seed for reproducibility.
    nargout
        Amount of arguments returned by the MATLAB function and consumed
        by the conversion to the internal representation. This defaults
        to ``nargout=2`` for the PPFT2D (2 distinct sectors) and
        ``nargout=1`` for the PPFT3D (3 sectors in one array).
    """
    import itertools
    import sys

    import numpy as np
    from tqdm import tqdm

    try:
        import matlab.engine as matlab_engine
    except ImportError:
        import textwrap

        print(
            textwrap.dedent("""\
                MATLAB Engine for Python is not installed.
                To install it, please follow the instructions at:
                https://github.com/mathworks/matlab-engine-for-python""")
        )
        sys.exit(1)

    default_config = DEFAULT_CONFIGS[dim]
    if input_dir is None:
        download_url = download_url or default_config.download_url

        print(f"Downloading MATLAB code from '{download_url}'...")
        input_dir = __download_matlab_code(download_url, output_dir=download_dir)

    print("Starting MATLAB Engine...")
    try:
        matlab: Any = matlab_engine.start_matlab()

        # Add paths of MATLAB source files to to the engine.
        matlab.addpath(matlab.genpath(str(input_dir)), nargout=0)

    except Exception as e:  # noqa: BLE001. We cannot import the actual exceptions.
        print(f"Could not start MATLAB Engine: {e}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    nargout = nargout or default_config.nargout
    functions = functions or default_config.functions

    # We store the current run's data to ensure that data is only generated
    # once for each function. Otherwise, data gets unnecessary re-generated
    # and output for random input data would differ between functions.
    data: tuple[int | None, MatrixType | None, NDArray | None] = None, None, None

    print("Generating test data...")
    tqdm_progress = tqdm(sorted(itertools.product(sizes, matrix_types, functions)))

    for n, matrix_type, function in tqdm_progress:
        tqdm.set_postfix(tqdm_progress, n=n, matrix_type=matrix_type, func=function)
        data_id = f"{dim}d_{matrix_type}_{n}"

        if (n, matrix_type) != data[:2] or data[2] is None:
            data = n, matrix_type, __generate_array(matrix_type, n=n, dim=dim, rng=rng)

        np.save(output_dir / f"{data_id}_in.npy", data[2], allow_pickle=False)

        try:
            output_data = getattr(matlab, function)(data[2], nargout=nargout)
        except Exception as e:  # noqa: BLE001. We cannot import the actual exceptions.
            print(f"Failed to run function '{function}': {e}")
            sys.exit(1)

        filename_out = f"{data_id}_out_{function.lower()}.npy"
        np.save(output_dir / filename_out, np.array(output_data), allow_pickle=False)


def __generate_array(
    matrix_type: MatrixType, *, n: int, dim: Dimension, rng: Generator
) -> NDArray:
    import numpy as np

    shape = (n,) * dim

    match matrix_type:
        case "ones":
            return np.ones(shape, dtype=float)
        case "zeros":
            return np.zeros(shape, dtype=float)
        case "random":
            return rng.random(shape, dtype=float)
        case "gradient":
            return np.linspace(0, 1, n**dim, dtype=float).reshape(shape)


def __download_matlab_code(url: URL, output_dir: Path) -> Path:
    import io
    import sys
    import zipfile

    import httpx

    try:
        response = httpx.get(url, follow_redirects=True, timeout=10)
        response.raise_for_status()

        filename = Path(__get_filename_from_response(response)).stem
        out_filedir = output_dir / filename
        out_filedir.mkdir(parents=True, exist_ok=True)

        with io.BytesIO(response.content) as buf, zipfile.ZipFile(buf, "r") as zip_ref:
            zip_ref.extractall(out_filedir)

        print(f"MATLAB code downloaded and extracted to '{out_filedir.absolute()}'")

    except httpx.RequestError as e:
        print(f"HTTP request failed: {e}")
        sys.exit(1)

    except zipfile.BadZipFile:
        print("Downloaded file is not a valid ZIP archive")
        sys.exit(1)

    else:
        return out_filedir


def __get_filename_from_response(response: httpx.Response) -> str:
    import re
    from urllib.parse import urlparse

    cd = response.headers.get("Content-Disposition", "")

    for part in cd.split(";"):
        if part.strip().startswith("filename="):
            filename = part.split("=", 1)[1].strip().strip('"')
            break
    else:
        # Use the URL as path/filename as fallback.
        filename = Path(urlparse(str(response.url)).path).name

    # Remove dangerous characters and restrict to alphanumeric + safe symbols.
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "_", filename)

    # Ensure no directory traversal.
    return Path(filename).name


if __name__ == "__main__":
    app()
