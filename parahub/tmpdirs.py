"""
Process-scoped scratch directories, grouped under a single /tmp entry.

Every temp directory Parahub creates lives under `<tmpdir>/parahub-<uid>/<kind>/`
instead of directly in /tmp. Listing a directory costs one stat per entry — over
sshfs, one round trip per entry — so scratch dirs that leak into the /tmp root
degrade every listing of it. Grouping bounds the damage to one entry regardless
of how many leak.

Leaks are normal rather than exceptional here: cleanup hooks (atexit, __del__)
never run when a process is SIGKILLed, which is exactly how systemd restarts and
the OOM killer end long-running workers. Directories are therefore named after
the PID that created them, so a later process can tell a leftover from one a
live process still depends on and sweep only the former.

No Django imports: settings.py loads this before the app registry exists.
"""

import atexit
import os
import shutil
import tempfile

_SWEPT: set[str] = set()


def scratch_root(kind: str) -> str:
    """Return the shared parent directory for `kind`, creating it if needed."""
    root = os.path.join(tempfile.gettempdir(), f'parahub-{os.getuid()}', kind)
    os.makedirs(root, mode=0o700, exist_ok=True)
    return root


def make_scratch_dir(kind: str, before_remove=None) -> str:
    """
    Create a PID-tagged scratch directory under the shared parent for `kind`.

    Sweeps orphans of the same kind first (once per process), so the parent stays
    small without a separate cleanup job. `before_remove` is called with the path
    of each orphan about to be deleted, for kinds that own more than a directory.
    """
    sweep_orphans(kind, before_remove=before_remove)
    return tempfile.mkdtemp(prefix=f'{os.getpid()}-', dir=scratch_root(kind))


def sweep_orphans(kind: str, before_remove=None) -> None:
    """
    Remove scratch dirs of `kind` whose creating process is gone.

    Runs at most once per kind per process. A recycled PID makes this skip a
    genuine orphan — deliberately biased that way: keeping a stale directory
    costs a few KB, deleting a live one breaks the process using it.
    """
    if kind in _SWEPT:
        return
    _SWEPT.add(kind)

    root = scratch_root(kind)
    try:
        names = os.listdir(root)
    except OSError:
        return

    for name in names:
        pid = name.partition('-')[0]
        if not pid.isdigit() or _pid_alive(int(pid)):
            continue
        path = os.path.join(root, name)
        if before_remove is not None:
            try:
                before_remove(path)
            except Exception:
                pass
        shutil.rmtree(path, ignore_errors=True)


def register_cleanup(path: str) -> None:
    """
    Remove `path` when the process that called this exits.

    Fork-safe: forked children (Django's `test --parallel`) inherit the atexit
    hook but must not delete a tree their parent still owns, so the hook is a
    no-op anywhere but the registering process.
    """
    owner = os.getpid()

    def _cleanup() -> None:
        if os.getpid() != owner:
            return
        shutil.rmtree(path, ignore_errors=True)

    atexit.register(_cleanup)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # alive, just owned by another user
    return True
