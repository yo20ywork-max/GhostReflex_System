"""Coordinate worker questions with the UI without reviving cancelled dialogs."""
from dataclasses import dataclass, field
import threading


@dataclass
class Question:
    token: str
    title: str
    prompt: str
    confirmation: bool
    ready: threading.Event = field(default_factory=threading.Event)
    answer: str | None = None


class DialogBroker:
    def __init__(self):
        self._lock = threading.Lock()
        self._cancelled = False
        self._serial = 0
        self._pending = None

    def begin_task(self):
        with self._lock:
            if self._pending is not None:
                raise RuntimeError('A previous question is still pending')
            self._cancelled = False

    def request(self, title, prompt, confirmation):
        with self._lock:
            if self._cancelled:
                return None
            if self._pending is not None:
                raise RuntimeError('Only one active question is supported')
            self._serial += 1
            self._pending = Question(str(self._serial), title, prompt, confirmation)
            return self._pending

    def is_pending(self, token):
        with self._lock:
            return self._pending is not None and self._pending.token == token

    def resolve(self, token, answer):
        with self._lock:
            if self._pending is None or self._pending.token != token:
                return False
            request = self._pending
            self._pending = None
            request.answer = answer or None
            request.ready.set()
            return True

    def cancel(self):
        with self._lock:
            self._cancelled = True
            if self._pending is not None:
                self._pending.ready.set()
                self._pending = None
