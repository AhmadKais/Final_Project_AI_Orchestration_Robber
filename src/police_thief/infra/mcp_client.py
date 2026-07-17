"""Client engine: calls the opponent's FastMCP server tools over the network
(Table 1). Every request carries an Expiry Deadline (Sec. 8.4.1) -- a missed
deadline is a failure, never an invitation to keep waiting.

`send_move` exchanges a plain geometric move (role/move/step, Stage 2).
`send_commit` / `send_ack` / `send_reveal` / `send_final_audit` /
`send_capture_claim` drive the full Commit-Reveal conversation (Sec. 5.3)
over the same transport.
"""

from __future__ import annotations

import asyncio
import time

from fastmcp import Client
from fastmcp.exceptions import McpError

from police_thief.domain.board import Move

# MCP error code FastMCP raises when a call_tool() deadline is exceeded.
_TIMEOUT_ERROR_CODE = 408
_CONNECT_RETRY_INTERVAL_SEC = 0.5


class OpponentClient:
    """Thin wrapper around a FastMCP client bound to the opponent.

    `opponent_url` is normally a public URL string (e.g.
    "http://127.0.0.1:8801/mcp"), but can also be an in-process `FastMCP`
    instance -- fastmcp.Client accepts either, which is what lets tests
    exercise this class without opening a real socket.
    """

    def __init__(self, opponent_url, *, response_timeout_sec: float):
        self.opponent_url = opponent_url
        self.response_timeout_sec = response_timeout_sec

    async def _call(self, tool_name: str, arguments: dict) -> dict:
        """Shared call path: every send_* method routes through here so the
        timeout-to-TimeoutError translation (Sec. 8.4.1) lives in one place.

        Retries a CONNECTION failure (not a tool-level McpError -- a real
        socket/HTTP-transport error, e.g. the opponent's server accepted
        the TCP connection but its own async lifespan hadn't finished
        initializing yet) until `response_timeout_sec` elapses, instead of
        raising on the first attempt. This isn't a hypothetical: a live
        two-real-process test (both peers starting at once, exactly how a
        real match begins) hit this every time -- FastMCP's own
        "Uvicorn running" log line prints before its StreamableHTTP
        session manager's task group finishes initializing, so the very
        first connection attempt from an opponent that started at the same
        moment routinely loses that race. In-process tests never exercise
        this at all (no real ASGI startup sequence), which is exactly why
        211+ passing tests never caught it."""
        deadline = time.monotonic() + self.response_timeout_sec
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                async with Client(self.opponent_url) as client:
                    try:
                        result = await client.call_tool(
                            tool_name, arguments, timeout=self.response_timeout_sec,
                        )
                    except McpError as exc:
                        if exc.error.code == _TIMEOUT_ERROR_CODE:
                            raise TimeoutError(
                                f"{tool_name} to {self.opponent_url!r} timed out "
                                f"after {self.response_timeout_sec}s"
                            ) from exc
                        raise
                    return result.data
            except TimeoutError:
                raise  # a real response-level timeout is not a connection hiccup -- never retried
            except Exception as exc:  # noqa: BLE001 -- deliberately broad: any connect-time failure
                last_error = exc
                await asyncio.sleep(_CONNECT_RETRY_INTERVAL_SEC)
        raise TimeoutError(
            f"Could not connect to {self.opponent_url!r} to call {tool_name} "
            f"within {self.response_timeout_sec}s"
        ) from last_error

    async def send_step0(self, *, role: str, declaration: dict, signature: str) -> dict:
        return await self._call(
            "receive_step0", {"role": role, "declaration": declaration, "signature": signature}
        )

    async def send_move(self, *, role: str, move: Move | str, step: int) -> dict:
        """Call the opponent's `receive_move` tool with a plain geometric move."""
        move_value = move.value if isinstance(move, Move) else move
        return await self._call("receive_move", {"role": role, "move": move_value, "step": step})

    async def send_commit(self, *, role: str, step: int, h_commit: str) -> dict:
        return await self._call("receive_commit", {"role": role, "step": step, "h_commit": h_commit})

    async def send_ack(self, *, role: str, step: int) -> dict:
        return await self._call("receive_ack", {"role": role, "step": step})

    async def send_reveal(self, *, role: str, step: int, move: Move | str, hint: str, intent: str) -> dict:
        move_value = move.value if isinstance(move, Move) else move
        return await self._call(
            "receive_reveal",
            {"role": role, "step": step, "move": move_value, "hint": hint, "intent": intent},
        )

    async def send_final_audit(self, *, role: str, nonces: list[str]) -> dict:
        return await self._call("receive_final_audit", {"role": role, "nonces": nonces})

    async def send_capture_claim(self, *, role: str, claimed: bool) -> dict:
        return await self._call("receive_capture_claim", {"role": role, "claimed": claimed})
