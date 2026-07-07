import pytest
from tests.builders import build_observation, build_observation_sequence

from infrastructure.sources.static_observation_source import StaticObservationSource


def test_empty_source_returns_empty_tuple() -> None:
    source = StaticObservationSource([])

    assert source.read() == ()


def test_one_observation() -> None:
    observation = build_observation(id="obs-1")
    source = StaticObservationSource([observation])

    assert source.read() == (observation,)


def test_multiple_observations_preserve_order() -> None:
    observations = build_observation_sequence([10.0, 20.0, 30.0])
    source = StaticObservationSource(observations)

    assert source.read() == observations
    assert [observation.value for observation in source.read()] == [10.0, 20.0, 30.0]


def test_returned_tuple_is_immutable() -> None:
    source = StaticObservationSource([build_observation()])

    result = source.read()

    with pytest.raises(TypeError):
        result[0] = build_observation(id="obs-2")  # type: ignore[index]


def test_repeated_reads_return_identical_data() -> None:
    observations = build_observation_sequence([1.0, 2.0])
    source = StaticObservationSource(observations)

    first_read = source.read()
    second_read = source.read()

    assert first_read == second_read
    assert first_read is second_read


def test_constructor_copies_observations() -> None:
    observations = [build_observation(id="obs-1")]
    source = StaticObservationSource(observations)
    observations.append(build_observation(id="obs-2"))

    assert source.read() == (build_observation(id="obs-1"),)
