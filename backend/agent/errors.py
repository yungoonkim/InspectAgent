"""Stable internal failures shared by orchestration and report validation."""


class AgentFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
