"""
Guards for parahub.tmpdirs.

The sweep deletes directories based on whether a PID is still alive, so its bias
matters more than its thoroughness: keeping a stale directory wastes a few KB,
while deleting a live one breaks the process holding it (a GPG home vanishing
mid-run takes signature verification down with it). These tests pin both
directions plus the grouping that keeps /tmp's root flat.
"""
import os
import shutil
import subprocess

from django.test import SimpleTestCase

from parahub import tmpdirs


def _reaped_pid() -> int:
    """A PID that is certainly dead: run a trivial process and wait for it."""
    proc = subprocess.Popen(['true'])
    proc.wait()
    return proc.pid


class ScratchDirTests(SimpleTestCase):
    kind = 'unit-test-scratch'

    def setUp(self):
        # _SWEPT makes the sweep once-per-process; tests need it to run each time
        tmpdirs._SWEPT.discard(self.kind)
        self.root = tmpdirs.scratch_root(self.kind)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)
        tmpdirs._SWEPT.discard(self.kind)

    def _make(self, name):
        path = os.path.join(self.root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def test_scratch_dir_is_pid_tagged_and_under_shared_root(self):
        path = tmpdirs.make_scratch_dir(self.kind)
        self.addCleanup(shutil.rmtree, path, True)
        self.assertEqual(os.path.dirname(path), self.root)
        self.assertEqual(os.path.basename(path).split('-')[0], str(os.getpid()))

    def test_orphan_of_dead_process_is_swept(self):
        orphan = self._make(f'{_reaped_pid()}-leftover')
        tmpdirs.sweep_orphans(self.kind)
        self.assertFalse(os.path.exists(orphan))

    def test_dir_of_live_process_survives(self):
        live = self._make(f'{os.getpid()}-in-use')
        tmpdirs.sweep_orphans(self.kind)
        self.assertTrue(os.path.exists(live))

    def test_unrecognised_name_is_left_alone(self):
        # Someone else's directory in the shared root is not ours to delete
        foreign = self._make('not-a-pid')
        tmpdirs.sweep_orphans(self.kind)
        self.assertTrue(os.path.exists(foreign))

    def test_before_remove_runs_for_each_orphan(self):
        orphan = self._make(f'{_reaped_pid()}-leftover')
        seen = []
        tmpdirs.sweep_orphans(self.kind, before_remove=seen.append)
        self.assertEqual(seen, [orphan])

    def test_before_remove_failure_does_not_block_removal(self):
        orphan = self._make(f'{_reaped_pid()}-leftover')

        def boom(path):
            raise RuntimeError('gpgconf missing')

        tmpdirs.sweep_orphans(self.kind, before_remove=boom)
        self.assertFalse(os.path.exists(orphan))

    def test_sweep_runs_once_per_process(self):
        tmpdirs.sweep_orphans(self.kind)
        late_orphan = self._make(f'{_reaped_pid()}-leftover')
        tmpdirs.sweep_orphans(self.kind)  # already swept -> no second pass
        self.assertTrue(os.path.exists(late_orphan))
