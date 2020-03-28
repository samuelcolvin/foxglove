import asyncio
from typing import Optional

from asyncpg import Connection


class TimedLock(asyncio.Lock):
    def __init__(self, *, loop=None, timeout=0.5):
        self.timeout = timeout
        super().__init__(loop=loop)

    async def acquire(self):
        try:
            await asyncio.wait_for(super().acquire(), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise asyncio.TimeoutError('DummyPg query lock timed out') from e


class _LockedExecute:
    def __init__(self, conn: Connection, lock: Optional[TimedLock] = None):
        self._conn: Connection = conn
        # could also add lock to each method of the returned connection
        self._lock: TimedLock = lock or TimedLock(loop=self._conn._loop)

    async def execute(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.execute(*args, **kwargs)

    async def execute_b(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.execute_b(*args, **kwargs)

    async def fetch(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.fetch(*args, **kwargs)

    async def fetch_b(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.fetch_b(*args, **kwargs)

    async def fetchval(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.fetchval(*args, **kwargs)

    async def fetchval_b(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.fetchval_b(*args, **kwargs)

    async def fetchrow(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.fetchrow(*args, **kwargs)

    async def fetchrow_b(self, *args, **kwargs):
        async with self._lock:
            return await self._conn.fetchrow_b(*args, **kwargs)


class DummyPgTransaction(_LockedExecute):
    _tr = None

    async def __aenter__(self):
        async with self._lock:
            self._tr = self._conn.transaction()
            await self._tr.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type:
                await self._tr.rollback()
            else:
                await self._tr.commit()
            self._tr = None


class DummyPgConn(_LockedExecute):
    def transaction(self):
        return DummyPgTransaction(self._conn, self._lock)

    def __repr__(self) -> str:
        return f'<DummyPgConn {self._conn._addr} {self._conn._params}>'


class _ConnAcquire:
    def __init__(self, conn: Connection, lock: TimedLock):
        self._conn = conn
        self._lock = lock

    async def __aenter__(self) -> DummyPgConn:
        return DummyPgConn(self._conn, self._lock)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummyPgPool(_LockedExecute):
    """
    dummy connection pool useful for testing, only one connection is used, but this will behave like
    Connection or BuildPgConnection, including locking before using the underlying connection.
    """

    def acquire(self):
        return _ConnAcquire(self._conn, self._lock)

    async def close(self):
        pass

    def as_dummy_conn(self) -> DummyPgConn:
        """
        convert to a DummyPgConn.

        **THIS IS OBVIOUSLY ONLY TO BE USED IN TESTS**
        """
        return DummyPgConn(self._conn, self._lock)

    def __repr__(self) -> str:
        return f'<DummyPgPool {self._conn._addr} {self._conn._params}>'
