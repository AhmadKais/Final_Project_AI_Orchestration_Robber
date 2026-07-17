"""FastMCP server/client round trip: a geometric move sent by one agent is
received and correctly decoded by the other (Stage 2 acceptance criterion,
spec Sec. 10.4). Uses fastmcp's in-process Client(FastMCP) transport, so no
real socket/port is opened -- this exercises the exact same tool-call path
that a real network connection would use.
"""

import asyncio
import socket

import pytest

from police_thief.infra.mcp_client import OpponentClient
from police_thief.infra.mcp_server import MoveMailbox, build_server


def make_server():
    mailbox = MoveMailbox()
    mcp = build_server("test-peer", mailbox)
    return mcp, mailbox


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_move_sent_by_one_agent_is_received_by_the_other():
    mcp, mailbox = make_server()
    client = OpponentClient(mcp, response_timeout_sec=5)

    response = await client.send_move(role="police", move="N", step=1)

    assert response == {"accepted": True, "role": "police", "move": "N", "step": 1}
    received = await asyncio.wait_for(mailbox.get(), timeout=1)
    assert received == {"role": "police", "move": "N", "step": 1}


async def test_send_move_accepts_move_enum_not_just_str():
    from police_thief.domain.board import Move

    mcp, mailbox = make_server()
    client = OpponentClient(mcp, response_timeout_sec=5)

    response = await client.send_move(role="thief", move=Move.WEST, step=2)

    assert response["accepted"] is True
    assert response["move"] == "W"


async def test_unknown_move_is_rejected_not_crashed():
    mcp, mailbox = make_server()
    client = OpponentClient(mcp, response_timeout_sec=5)

    response = await client.send_move(role="police", move="DIAGONAL", step=1)

    assert response["accepted"] is False
    assert mailbox.empty()


async def test_unknown_role_is_rejected():
    mcp, mailbox = make_server()
    client = OpponentClient(mcp, response_timeout_sec=5)

    response = await client.send_move(role="referee", move="N", step=1)

    assert response["accepted"] is False
    assert mailbox.empty()


async def test_receive_reveal_accepts_a_barrier_encoded_move():
    mcp, mailbox = make_server()
    client = OpponentClient(mcp, response_timeout_sec=5)

    response = await client.send_reveal(
        role="police", step=0, move="STAY+BARRIER:2,3", hint="holding position", intent="true"
    )

    assert response == {"accepted": True}
    received = await asyncio.wait_for(mailbox.reveals.get(), timeout=1)
    assert received["move"] == "STAY+BARRIER:2,3"


async def test_receive_reveal_rejects_malformed_barrier_encoding():
    mcp, mailbox = make_server()
    client = OpponentClient(mcp, response_timeout_sec=5)

    response = await client.send_reveal(
        role="police", step=0, move="STAY+BARRIER:not-a-coord", hint="", intent="true"
    )

    assert response["accepted"] is False
    assert mailbox.reveals.empty()


async def test_slow_opponent_raises_timeout_not_a_hang():
    # Sec. 8.4.1: a missed deadline is a failure, never an invitation to
    # keep waiting -- assert this is enforced as a real, bounded timeout.
    from fastmcp import FastMCP

    slow_mcp = FastMCP("slow-peer")

    @slow_mcp.tool
    async def receive_move(role: str, move: str, step: int) -> dict:
        await asyncio.sleep(2)
        return {"accepted": True}

    client = OpponentClient(slow_mcp, response_timeout_sec=0.1)

    with pytest.raises(TimeoutError):
        await client.send_move(role="police", move="N", step=1)


async def test_connection_refused_retries_until_the_opponent_starts_listening():
    """A live two-real-process test (both peers starting at once, exactly
    how a real match begins) found this isn't hypothetical: FastMCP's own
    "Uvicorn running" log line prints before its session manager finishes
    initializing, so an opponent that starts at the same moment routinely
    fails its very first connection attempt. The client must retry through
    that window instead of crashing the whole peer on the first try."""
    port = _free_port()
    client = OpponentClient(f"http://127.0.0.1:{port}/mcp", response_timeout_sec=5)
    mailbox = MoveMailbox()
    mcp = build_server("late-peer", mailbox)

    async def start_server_late():
        await asyncio.sleep(0.6)  # the client's first few attempts must hit connection-refused
        await mcp.run_async(transport="http", host="127.0.0.1", port=port, show_banner=False)

    server_task = asyncio.create_task(start_server_late())
    try:
        response = await client.send_move(role="police", move="N", step=1)
        assert response == {"accepted": True, "role": "police", "move": "N", "step": 1}
    finally:
        server_task.cancel()


async def test_nothing_ever_listening_times_out_bounded_not_a_hang():
    """The retry loop still has to give up eventually -- an opponent that
    genuinely never comes up must fail within response_timeout_sec, not
    retry forever."""
    port = _free_port()  # guaranteed nothing is listening here
    client = OpponentClient(f"http://127.0.0.1:{port}/mcp", response_timeout_sec=1)

    start = asyncio.get_event_loop().time()
    with pytest.raises(TimeoutError):
        await client.send_move(role="police", move="N", step=1)
    elapsed = asyncio.get_event_loop().time() - start
    assert elapsed < 3  # bounded -- generous margin over the 1s budget, not an exact race
