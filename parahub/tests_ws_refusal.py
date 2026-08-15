"""How an authenticated socket says no.

Every one of these turns on the same thing: a socket must be *accepted* before
it is refused. Closing an unaccepted socket makes the server answer the HTTP
upgrade with 403, and then the close code never reaches the client — the
browser reports a bare 1006, and the Android WebView paints the 403 as a
full-page system error over the running app. Without a code to read, a native
client cannot tell "your token did not arrive" from "the train went into a
tunnel", which is exactly the retry it needs to make (issue #465).

That fix was applied to one consumer in April and to none of the others, so
these tests exist to keep it from drifting back a second time.
"""

from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase

from parahub.consumers.driver import DriverConsumer
from parahub.consumers.map_presence import MapPresenceConsumer
from parahub.consumers.realtime import RealtimeConsumer
from parahub.consumers.tracker import TrackerConsumer
from parahub.testing import WebsocketCommunicator

# Each authenticated consumer, the path it is routed on, and the code it
# refuses an anonymous caller with.
CONSUMERS = [
    ('realtime', RealtimeConsumer, '/ws/v1/realtime/', 4001),
    ('map presence', MapPresenceConsumer, '/ws/v1/map/presence/', 4001),
    ('tracker', TrackerConsumer, '/ws/v1/trackers/', 4001),
    ('driver', DriverConsumer, '/ws/v1/driver/', 4001),
]


class UnauthenticatedRefusalTests(TransactionTestCase):
    def _anonymous(self, consumer_cls, path):
        return WebsocketCommunicator(consumer_cls.as_asgi(), path, scope={
            'user': AnonymousUser(),
            'profile': None,
        })

    async def test_every_authed_socket_is_accepted_before_it_is_refused(self):
        for label, consumer_cls, path, code in CONSUMERS:
            with self.subTest(consumer=label):
                communicator = self._anonymous(consumer_cls, path)
                accepted, _ = await communicator.connect()
                self.assertTrue(
                    accepted,
                    f"{label} closed before accepting — the client sees 1006, not {code}")

                # A reason, then the code. Both are what the client branches on.
                refusal = await communicator.receive_json_from()
                self.assertEqual(refusal['type'], 'error')
                self.assertEqual(refusal['code'], 'unauthenticated')
                self.assertTrue(refusal['message'])

                closed = await communicator.receive_output()
                self.assertEqual(closed['type'], 'websocket.close')
                self.assertEqual(closed['code'], code)

    async def test_a_refused_socket_tears_down_without_raising(self):
        """The disconnect handler now runs where it used to be skipped.

        Accepting the socket means channels really opens it, so the refusal is
        followed by a `websocket.disconnect` — and the consumer's teardown then
        runs against a `connect` that returned early. Driver and tracker both
        raised `AttributeError` on their own shift state the first time this
        landed; an exception there is logged as a 500 and leaves the connection
        half-torn-down.
        """
        for label, consumer_cls, path, _ in CONSUMERS:
            with self.subTest(consumer=label):
                communicator = self._anonymous(consumer_cls, path)
                await communicator.connect()
                await communicator.receive_json_from()   # the refusal
                await communicator.receive_output()      # the close

                await communicator.disconnect()
                # `wait` re-raises whatever the application raised.
                self.assertIsNone(communicator.future.exception())
