"""Rate floor for pushes a human tap drives, with no lost final state.

Some server pushes are triggered by a person acting, not by a daemon tick:
waiting-passenger markers are the case this exists for. One tap fans out to
every subscriber of the affected line, viewport or shift, and each of them
answers with a read — so a finger walking down a stop list multiplies into real
work. The fix belongs on the fan-out side, never on the tapping human: a
cooldown on the mover charges the honest user for correcting their own pole and
is walked past anyway by unmark-then-mark.

Floor alone is not enough, though. Dropping the nudges inside the window loses
whichever one was last, which is precisely the state everyone should end up
looking at — the watcher then sits on stale counts until some unrelated tick
refreshes them, and the point of having a channel at all was to beat that tick.
So a suppressed nudge queues one trailing run instead, which reads its data when
it fires and therefore carries the settled state, not an intermediate one.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class TrailingFloor:
    """Run `send` at most once per `interval`, last state always included.

    The first nudge of a quiet period runs immediately — a lone tap must not be
    delayed. Nudges arriving inside the window collapse into a single trailing
    run at the end of it.
    """

    def __init__(self, interval: float, send, name: str = 'push'):
        self._interval = interval
        self._send = send
        self._name = name
        self._last = 0.0
        self._task: asyncio.Task | None = None

    async def nudge(self):
        wait = self._last + self._interval - time.time()
        if wait <= 0:
            await self._run()
        elif self._task is None:
            self._task = asyncio.create_task(self._trailing(wait))

    async def _run(self):
        # Stamped before sending: the floor measures the interval between the
        # starts of two sends, so a slow one cannot let a second through behind it.
        self._last = time.time()
        await self._send()

    async def _trailing(self, delay: float):
        try:
            await asyncio.sleep(delay)
            await self._run()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # A closed socket is the ordinary end here — disconnect cancels the
            # task, but a send racing the close still lands in this branch.
            logger.debug(f'Trailing {self._name} failed: {e}')
        finally:
            self._task = None

    def cancel(self):
        """Drop any queued trailing run. Call from the consumer's disconnect."""
        if self._task:
            self._task.cancel()
            self._task = None
