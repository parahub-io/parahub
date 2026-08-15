"""Test helpers that have nowhere better to live.

`WebsocketCommunicator` is the one channels ships, minus everything these tests
do not use. It is reimplemented rather than imported because anything from
`channels.testing` executes that package's `__init__`, which imports daphne —
deliberately absent since 2026-06-19, when it was the only path left to
twisted's HIGH CVEs (see requirements.txt).
"""

import json
from unittest import mock

from asgiref.testing import ApplicationCommunicator


def _no_op():
    pass


class WebsocketCommunicator(ApplicationCommunicator):
    """Speak the few frames a consumer test needs straight to the ASGI app."""

    def __init__(self, application, path, scope=None):
        self.scope = {
            'type': 'websocket', 'path': path, 'query_string': b'',
            'headers': [], 'subprotocols': [], **(scope or {}),
        }
        super().__init__(application, self.scope)

    async def send_input(self, message):
        # channels wraps every dispatch in this; without the patch the real one
        # closes the test transaction's connection mid-test.
        with mock.patch('channels.db.close_old_connections', _no_op):
            return await super().send_input(message)

    async def receive_output(self, timeout=1):
        with mock.patch('channels.db.close_old_connections', _no_op):
            return await super().receive_output(timeout)

    async def connect(self, timeout=1):
        await self.send_input({'type': 'websocket.connect'})
        response = await self.receive_output(timeout)
        if response['type'] == 'websocket.close':
            return False, response.get('code', 1000)
        assert response['type'] == 'websocket.accept'
        return True, response.get('subprotocol')

    async def send_to(self, text_data=None, bytes_data=None):
        if text_data is not None:
            await self.send_input({'type': 'websocket.receive', 'text': text_data})
        else:
            await self.send_input({'type': 'websocket.receive', 'bytes': bytes_data})

    async def send_json_to(self, data):
        await self.send_to(text_data=json.dumps(data))

    async def receive_json_from(self, timeout=1):
        response = await self.receive_output(timeout)
        assert response['type'] == 'websocket.send', f"got {response['type']}"
        return json.loads(response['text'])

    async def receive_bytes_from(self, timeout=1):
        """The next frame, asserted to be binary.

        A consumer that answers with audio (live translation) puts the bytes on
        the wire right behind the JSON describing them, so a test that reads
        this must be able to say which of the two it got.
        """
        response = await self.receive_output(timeout)
        assert response['type'] == 'websocket.send', f"got {response['type']}"
        assert response.get('bytes') is not None, f"expected bytes, got {response}"
        return response['bytes']

    async def disconnect(self, code=1000, timeout=1):
        await self.send_input({'type': 'websocket.disconnect', 'code': code})
        await self.wait(timeout)
