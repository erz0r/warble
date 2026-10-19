"""errors that carry enough context for an agent to act on them."""


class WarbleError(Exception):
    """an error with a stable code, a message, and an optional hint on how to fix it."""

    def __init__(self, code, message, hint=None, **details):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.details = details

    def to_json(self):
        out = {"error": self.code, "message": self.message}
        if self.hint:
            out["hint"] = self.hint
        if self.details:
            out["details"] = self.details
        return out
