from application.event_publisher import InMemoryEventPublisher
from domain.events.decision_context_created import DecisionContextCreated
from domain.events.observation_recorded import ObservationRecorded
from tests.builders import DEFAULT_TIMESTAMP


def test_publish_appends_events_in_order() -> None:
    publisher = InMemoryEventPublisher()
    first = ObservationRecorded(
        observation_id="obs-1",
        recorded_at=DEFAULT_TIMESTAMP,
    )
    second = DecisionContextCreated(
        context_id="context-1",
        created_at=DEFAULT_TIMESTAMP,
    )

    publisher.publish(first)
    publisher.publish(second)

    assert publisher.events == (first, second)
