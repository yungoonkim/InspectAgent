"""Drive asyncio deadline callbacks after the final mock request has started."""

import asyncio
from unittest.mock import patch


class ControlledDeadlines:
    def __init__(self):
        self.loop = asyncio.get_running_loop()
        self.original = self.loop.call_at
        self.callbacks = []

    def schedule(self, when, callback, *arguments, context=None):
        handle = self.original(self.loop.time() + 3600, callback, *arguments, context=context)
        self.callbacks.append((callback, arguments, handle))
        return handle

    def __enter__(self):
        self.patcher = patch.object(self.loop, "call_at", self.schedule)
        self.patcher.start()
        return self

    def __exit__(self, *arguments):
        self.patcher.stop()
        for callback, arguments, handle in self.callbacks:
            handle.cancel()

    async def expire(self, kind):
        name = "_on_timeout" if kind == "overall" else "_release_waiter"
        for callback, arguments, handle in reversed(self.callbacks):
            if getattr(callback, "__name__", None) == name and not handle.cancelled():
                self.loop.call_soon(callback, *arguments)
                await asyncio.Event().wait()
        raise AssertionError("DEADLINE_CALLBACK_NOT_REGISTERED")
