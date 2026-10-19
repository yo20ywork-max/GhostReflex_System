"""Observe path entry metadata without reading contents or following its leaf."""
import os
from pathlib import Path
import stat


def inspect_path(path, workspace, allow_outside=False):
    root = Path(workspace).resolve()
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    # Resolve parents for confinement, but retain a leaf link as a link.
    candidate = candidate.parent.resolve() / candidate.name
    if not allow_outside and not candidate.is_relative_to(root):
        raise ValueError('路徑不在允許的工作區內。')
    try:
        value = os.lstat(candidate)
    except FileNotFoundError:
        return {'path': str(candidate), 'exists': False, 'is_file': False,
                'is_directory': False, 'is_symlink': False, 'content_read': False}
    return {'path': str(candidate), 'exists': True, 'is_file': stat.S_ISREG(value.st_mode),
            'is_directory': stat.S_ISDIR(value.st_mode), 'is_symlink': stat.S_ISLNK(value.st_mode),
            'content_read': False}
