"""Tests for JobQueue."""

from __future__ import annotations

import asyncio

import pytest

from beachops.services.job_queue import JobQueue, SubmitResult


@pytest.mark.asyncio
async def test_submit_starts_immediately() -> None:
    queue = JobQueue(max_queue_depth=2)
    started = asyncio.Event()

    async def job() -> None:
        started.set()
        await asyncio.sleep(0.05)

    info = await queue.submit(1, job)
    assert info.result == SubmitResult.STARTED
    await asyncio.wait_for(started.wait(), timeout=1.0)
    await asyncio.sleep(0.1)
    assert not queue.is_active(1)


@pytest.mark.asyncio
async def test_submit_queues_when_busy() -> None:
    queue = JobQueue(max_queue_depth=2)
    gate = asyncio.Event()

    async def long_job() -> None:
        await gate.wait()

    await queue.submit(1, long_job)
    await asyncio.sleep(0.01)
    assert queue.is_active(1)

    info = await queue.submit(1, long_job)
    assert info.result == SubmitResult.QUEUED
    assert info.queue_position == 1

    gate.set()
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_submit_rejects_full_queue() -> None:
    queue = JobQueue(max_queue_depth=2)
    gate = asyncio.Event()

    async def long_job() -> None:
        await gate.wait()

    await queue.submit(1, long_job)
    await asyncio.sleep(0.01)
    await queue.submit(1, long_job)
    await queue.submit(1, long_job)

    info = await queue.submit(1, long_job)
    assert info.result == SubmitResult.REJECTED

    gate.set()
    await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_clear_pending() -> None:
    queue = JobQueue(max_queue_depth=2)
    gate = asyncio.Event()

    async def long_job() -> None:
        await gate.wait()

    await queue.submit(1, long_job)
    await asyncio.sleep(0.01)
    await queue.submit(1, long_job)
    assert queue.clear_pending(1) == 1

    gate.set()
    await asyncio.sleep(0.05)
