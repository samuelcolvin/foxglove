import asyncio
from functools import wraps
from typing import Callable, Optional

from buildpg.asyncpg import BuildPgConnection


class TimedLock(asyncio.Lock):
    def __init__(self, name: str, *, timeout=0.5):
        self.name = name
        self.timeout = timeout
        super().__init__()

    async def acquire(self):
        try:
            await asyncio.wait_for(super().acquire(), timeout=self.timeout)
        except asyncio.TimeoutError as e:
            raise asyncio.TimeoutError(f'{self.name} timed out') from e


class _LockedExecute:
    def __init__(
        self, conn: BuildPgConnection, lock: Optional[TimedLock] = None, transaction_lock: Optional[TimedLock] = None
    ):
        self._conn: BuildPgConnection = conn
        # could also add lock to each method of the returned connection
        self._lock: TimedLock = lock or TimedLock('DummyPgConn query lock')
        self._transaction_lock: TimedLock = transaction_lock or TimedLock('DummyPgConn transaction lock', timeout=2)

    def __getattr__(self, item):
        f = getattr(self._conn, item)

        @wraps(f)
        async def wrapped_function(*args, **kwargs):
            async with self._lock:
                return await f(*args, **kwargs)

        return wrapped_function


class DummyPgTransaction:
    def __init__(
        self,
        conn: BuildPgConnection,
        lock: TimedLock,
        transaction_lock: TimedLock,
        set_lock: Callable[[TimedLock], None],
    ):
        self._conn: BuildPgConnection = conn
        self._lock: TimedLock = lock
        self._transaction_lock: TimedLock = transaction_lock
        self._set_lock = set_lock

    async def __aenter__(self):
        await self._transaction_lock.acquire()
        async with self._lock:
            self._tr = self._conn.transaction()
            await self._tr.start()
            # set a new transaction lock on the connection while it's "in this transaction" so nested transactions
            # still work
            lock = self._transaction_lock
            self._set_lock(TimedLock(lock.name, timeout=lock.timeout))

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        async with self._lock:
            if exc_type:
                await self._tr.rollback()
            else:
                await self._tr.commit()
            self._tr = None
            # put the transaction lock back so multiple transactions can't be run at the same time
            self._set_lock(self._transaction_lock)
            self._transaction_lock.release()


class DummyPgConn(_LockedExecute):
    def _set_transaction_lock(self, lock: TimedLock):
        self._transaction_lock = lock

    def transaction(self):
        return DummyPgTransaction(self._conn, self._lock, self._transaction_lock, set_lock=self._set_transaction_lock)

    def __repr__(self) -> str:
        return f'<DummyPgConn {self._conn._addr} {self._conn._params}>'


class _ConnAcquire:
    def __init__(self, conn: BuildPgConnection, lock: TimedLock, transaction_lock: TimedLock):
        self._conn = conn
        self._lock = lock
        self._transaction_lock = transaction_lock

    async def __aenter__(self) -> DummyPgConn:
        return DummyPgConn(self._conn, self._lock, self._transaction_lock)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def _get_conn(self) -> DummyPgConn:
        return DummyPgConn(self._conn, self._lock, self._transaction_lock)

    def __await__(self):
        return self._get_conn().__await__()


class DummyPgPool(_LockedExecute):
    """
    dummy connection pool useful for testing, only one connection is used, but this will behave like
    Connection or BuildPgConnection, including locking before using the underlying connection.
    """

    def acquire(self):
        return _ConnAcquire(self._conn, self._lock, self._transaction_lock)

    async def close(self):
        pass

    async def release(self, conn):
        pass

    def as_dummy_conn(self) -> DummyPgConn:
        """
        convert to a DummyPgConn.

        **THIS IS OBVIOUSLY ONLY TO BE USED IN TESTS**
        """
        return DummyPgConn(self._conn, self._lock, self._transaction_lock)

    def __repr__(self) -> str:
        return f'<DummyPgPool {self._conn._addr} {self._conn._params}>'


class SyncDb:
    def __init__(self, conn: BuildPgConnection, loop: asyncio.AbstractEventLoop):
        self._conn = conn
        self._loop = loop

    def execute(self, *args, **kwargs):
        return self._loop.run_until_complete(self._conn.execute(*args, **kwargs))

    def execute_b(self, *args, **kwargs):
        return self._loop.run_until_complete(self._conn.execute_b(*args, **kwargs))

    def fetch(self, *args, **kwargs):
        v = self._loop.run_until_complete(self._conn.fetch(*args, **kwargs))
        return [dict(r) for r in v]

    def fetch_b(self, *args, **kwargs):
        v = self._loop.run_until_complete(self._conn.fetch_b(*args, **kwargs))
        return [dict(r) for r in v]

    def fetchval(self, *args, **kwargs):
        return self._loop.run_until_complete(self._conn.fetchval(*args, **kwargs))

    def fetchval_b(self, *args, **kwargs):
        return self._loop.run_until_complete(self._conn.fetchval_b(*args, **kwargs))

    def fetchrow(self, *args, **kwargs):
        v = self._loop.run_until_complete(self._conn.fetchrow(*args, **kwargs))
        return None if v is None else dict(v)

    def fetchrow_b(self, *args, **kwargs):
        v = self._loop.run_until_complete(self._conn.fetchrow_b(*args, **kwargs))
        return None if v is None else dict(v)

    def executemany(self, *args, **kwargs):
        return self._loop.run_until_complete(self._conn.executemany(*args, **kwargs))

    def executemany_b(self, *args, **kwargs):
        return self._loop.run_until_complete(self._conn.executemany_b(*args, **kwargs))
