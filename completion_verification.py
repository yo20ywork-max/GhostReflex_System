"""Retry an unavailable checker without re-planning or repeating user actions."""
import copy
import time


class VerificationUnavailable(RuntimeError):
    def __init__(self, message, *, retryable=True):
        super().__init__(message)
        self.retryable = retryable


class VerificationCancelled(RuntimeError):
    pass


def verify_with_retry(assess, prompt, history, *, cancel_event=None,
                      max_attempts=3, retry_delay=0.5, on_unavailable=None):
    """Bound attempts, not transport duration; an in-flight call may take 180s.

    Only unavailable verification is retried. A valid negative assessment is
    returned immediately. Every attempt receives a fresh copy of the same
    observations, including if a third-party checker accidentally mutates them.
    """
    if max_attempts < 1 or retry_delay < 0:
        raise ValueError('Invalid verification retry policy')
    snapshot = copy.deepcopy(history)
    for attempt in range(1, max_attempts + 1):
        if cancel_event is not None and cancel_event.is_set():
            raise VerificationCancelled('已取消核對。')
        try:
            result = assess(prompt, copy.deepcopy(snapshot))
        except VerificationUnavailable as exc:
            if cancel_event is not None and cancel_event.is_set():
                raise VerificationCancelled('已取消核對。') from exc
            if on_unavailable is not None:
                on_unavailable(attempt, str(exc), exc.retryable)
            if not exc.retryable or attempt == max_attempts:
                raise
            if cancel_event is not None:
                if cancel_event.wait(retry_delay):
                    raise VerificationCancelled('已取消核對。') from exc
            else:
                time.sleep(retry_delay)
        else:
            if cancel_event is not None and cancel_event.is_set():
                raise VerificationCancelled('已取消核對。')
            return result
