"""TODO."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays

from ppftpy import ppft2, rppft2

if TYPE_CHECKING:
    from collections.abc import Callable

    from numpy.typing import NDArray

MAX_SHAPE_SIZE: Final = 32
VALID_SHAPE_2D: Final = (
    st.integers(2, MAX_SHAPE_SIZE).filter(lambda x: x % 2 == 0).map(lambda n: (n, n))
)


def __odd_square_matrices() -> st.SearchStrategy:
    return arrays(
        dtype=np.float64,
        shape=st.integers(3, MAX_SHAPE_SIZE + 1)
        .filter(lambda x: x % 2 != 0)
        .map(lambda n: (n, n)),
        elements=st.floats(),
    )


def __non_square_matrices() -> st.SearchStrategy:
    return arrays(
        dtype=np.float64,
        shape=st.tuples(
            st.integers(2, MAX_SHAPE_SIZE).filter(lambda x: x % 2 == 0),
            st.integers(3, MAX_SHAPE_SIZE + 1).filter(lambda x: x % 2 != 0),
        ),
        elements=st.floats(),
    )


def __invalid_dim_matrices() -> st.SearchStrategy:
    return st.one_of(
        # 0D array (scalar wrapped in NumPy array)
        arrays(dtype=np.float64, shape=(), elements=st.floats()),
        # 1D array
        arrays(
            dtype=np.float64,
            shape=st.tuples(st.integers(2, MAX_SHAPE_SIZE)),
            elements=st.floats(),
        ),
        # 4D array
        arrays(
            dtype=np.float64,
            shape=st.tuples(
                st.integers(1, 10),
                st.integers(2, MAX_SHAPE_SIZE),
                st.integers(2, MAX_SHAPE_SIZE),
                st.integers(2, MAX_SHAPE_SIZE),
            ),
            elements=st.floats(),
        ),
    )


@given(data=__odd_square_matrices())
@pytest.mark.parametrize("ppft_func", [ppft2, rppft2])
def test_ppft2_odd_sized_matrix_raises(data: NDArray, ppft_func: Callable) -> None:
    """Ensure function fails for matrices with odd dimensions."""
    with pytest.raises(ValueError, match="Input data must have even sides"):
        ppft_func(data)


@given(data=__non_square_matrices())
@pytest.mark.parametrize("ppft_func", [ppft2, rppft2])
def test_ppft2_non_square_matrix_raises(data: NDArray, ppft_func: Callable) -> None:
    """Ensure function fails for non-square matrices."""
    with pytest.raises(
        ValueError, match="Input data must have sides with same lengths"
    ):
        ppft_func(data)


@given(data=__invalid_dim_matrices())
@pytest.mark.parametrize("ppft_func", [ppft2, rppft2])
def test_ppft2_invalid_dimensions_raises(data: NDArray, ppft_func: Callable) -> None:
    """Ensure function fails for non-2D (0D, 1D, 4D, etc.) matrices."""
    with pytest.raises(
        ValueError,
        match="Input data must a single NxN matrix or an array of NxN matrices",
    ):
        ppft_func(data)
