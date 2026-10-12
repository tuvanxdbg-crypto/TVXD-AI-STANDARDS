"""Error type shared by every cadaudit module. `code` is a closed identifier printed on stderr."""


class CadAuditError(Exception):
    """An input, rules or output error. The run stops and no report file is produced."""

    def __init__(self, code: str, message: str, exit_code: int = 2):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.exit_code = exit_code
