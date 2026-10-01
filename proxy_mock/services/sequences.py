"""Process-local response cursors, separate from serializable mock configuration."""

import asyncio
from copy import deepcopy


class SequenceExhausted(Exception):
    """A matching sequence has no responses left and uses the error policy."""


class ResponseSequence:
    def __init__(self, configuration: dict):
        self.configuration = deepcopy(configuration)
        self.position = 0
        self._lock = asyncio.Lock()

    async def take(self) -> dict:
        # Reserve a response before waiting on configured delays. Cancellation consumes the
        # reservation; putting it back could repeat a response already assigned to another call.
        async with self._lock:
            responses = self.configuration["responses"]
            if self.position == len(responses):
                if self.configuration["on_exhaustion"] == "error":
                    raise SequenceExhausted("Response sequence exhausted")
                return deepcopy(responses[-1])
            response = deepcopy(responses[self.position])
            self.position += 1
            return response

    def _state(self) -> dict:
        length = len(self.configuration["responses"])
        return {
            "position": self.position,
            "length": length,
            "exhausted": self.position == length,
            "on_exhaustion": self.configuration["on_exhaustion"],
        }

    async def state(self, *, reset: bool = False) -> dict:
        async with self._lock:
            if reset:
                self.position = 0
            return self._state()


def build_sequences(mock: dict, previous: dict, preserve: set) -> dict[int | None, ResponseSequence]:
    """Rule indexes refer to submitted list order, independently of matching priority."""
    configurations = {None: mock.get("sequence")}
    configurations.update({index: rule.get("sequence") for index, rule in enumerate(mock.get("rules") or [])})
    states = {}
    for key, configuration in configurations.items():
        if configuration is None:
            continue
        old = previous.get(key)
        if key in preserve and old is not None and old.configuration == configuration:
            states[key] = old
        else:
            states[key] = ResponseSequence(configuration)
    return states
