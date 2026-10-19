"""Fail before downloads/GPU work unless a locked, bounded launch is approved."""
from datetime import datetime, timezone
import json


def require_launch(root, lock, *, mode, now=None):
    if 'LAUNCH_STATUS.json' not in lock.get('sha256', {}):
        raise RuntimeError('Launch status must be part of the verified data lock')
    status=json.loads((root/'LAUNCH_STATUS.json').read_text(encoding='utf8'))
    if status.get('launch_allowed') is not True:
        raise RuntimeError('Training launch disabled: storage clearance and bounded provider plan are pending')
    if status.get('temporary_storage_user_approved') is not True:
        raise RuntimeError('Temporary storage clearance missing')
    if mode not in status.get('allowed_modes', []):
        raise RuntimeError('This launch mode is not approved')
    for key in ('max_temporary_gib','max_charge_usd','max_run_seconds'):
        value=status.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not 0<value<float('inf'):
            raise RuntimeError('Missing positive launch bound: '+key)
    if not isinstance(status.get('pod_id'),str) or not status['pod_id'].strip():
        raise RuntimeError('Verified provider pod ID missing')
    try:
        deadline=datetime.fromisoformat(status['deadline_utc'])
        if deadline.tzinfo is None:raise ValueError('timezone required')
    except (KeyError,TypeError,ValueError) as exc:
        raise RuntimeError('Valid UTC launch deadline required') from exc
    if (now or datetime.now(timezone.utc))>=deadline:
        raise RuntimeError('Launch deadline expired')
    return status
