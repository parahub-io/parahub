"""
Localizable API errors.

`HttpError` only serializes its human message (`{"detail": ...}`), so the
frontend can only display the canonical English text. `LocalizedHttpError`
additionally carries a stable, machine-readable `code` so the client can map
it to a translated string. The English `message` is kept as the canonical
fallback (also what gets logged and shown if the client has no translation
for the code).

Lives in its own module to stay importable from both `parahub.api` (handler
registration) and endpoint modules without a circular import.
"""

from ninja.errors import HttpError


class LocalizedHttpError(HttpError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.code = code
        super().__init__(status_code, message)
