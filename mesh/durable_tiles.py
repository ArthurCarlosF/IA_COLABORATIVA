"""Small matrix tasks with atomic, non-expiring progress.

The memory bound covers each task's arrays, not the Python/PyTorch runtime.
No model weights or credentials are stored in the checkpoint database.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import threading
import numpy as np


ALGORITHM = 'fp32-row-column-tiles-v1'


def tile_bytes(batch, rows, columns):
    return 4*(batch*columns + rows*columns + 4*batch*rows)


def matmul_tile(inputs, weights, maximum_bytes=65536):
    """Portable task: inputs[M,K] times weights[N,K] transposed."""
    a, w = np.asarray(inputs), np.asarray(weights)
    if (a.dtype != np.float32 or w.dtype != np.float32
            or a.ndim != 2 or w.ndim != 2 or a.shape[1] != w.shape[1]
            or min(*a.shape, *w.shape) < 1):
        raise ValueError('Invalid FP32 matrix tile')
    if tile_bytes(a.shape[0], w.shape[0], a.shape[1]) > maximum_bytes:
        raise ValueError('Tile exceeds declared working memory')
    if not np.isfinite(a).all() or not np.isfinite(w).all():
        raise ValueError('Non-finite tile')
    output = a @ w.T
    if not np.isfinite(output).all():
        raise ValueError('Non-finite tile result')
    return output


class DurableMatmul:
    def __init__(self, database, tile_rows=16, tile_columns=256, maximum_bytes=65536,
                 kernel=matmul_tile,kernel_id='numpy-local-v1'):
        if any(type(n) is not int or n < 1
               for n in (tile_rows, tile_columns, maximum_bytes)):
            raise ValueError('Invalid tile configuration')
        self.rows, self.columns, self.maximum_bytes = tile_rows, tile_columns, maximum_bytes
        self.kernel,self.kernel_id=kernel,kernel_id
        path = Path(database)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.executescript("""
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
CREATE TABLE IF NOT EXISTS tile_jobs(
 id TEXT PRIMARY KEY, descriptor TEXT NOT NULL, status TEXT NOT NULL,
 committed_tiles INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS tile_rows(
 job TEXT NOT NULL, row_start INTEGER NOT NULL, next_column INTEGER NOT NULL,
 partial BLOB NOT NULL, checksum TEXT NOT NULL,
 PRIMARY KEY(job,row_start));
""")

    def close(self):
        self.db.close()

    def run(self, inputs, source_id, weight_shape, fetch, max_tiles=None,
            after_commit=None, cancel=None):
        """Fetch receives (row_start,row_end,column_start,column_end).

        A retry resumes from the last committed column. A crash before commit
        repeats only that calculation and cannot apply its sum twice.
        """
        if not isinstance(source_id, str) or not source_id or len(source_id) > 4096:
            raise ValueError('An immutable source identifier is required')
        x = np.asarray(inputs)
        if (x.dtype != np.float32 or x.ndim != 2 or min(x.shape) < 1
                or not np.isfinite(x).all()):
            raise ValueError('Expected finite FP32 inputs[M,K]')
        if (len(weight_shape) != 2 or any(type(n) is not int or n < 1 for n in weight_shape)
                or x.shape[1] != weight_shape[1]):
            raise ValueError('Invalid weight shape')
        if max_tiles is not None and (type(max_tiles) is not int or max_tiles < 0):
            raise ValueError('Invalid tile execution limit')
        m, k = x.shape
        n = weight_shape[0]
        rows, columns = min(self.rows, n), min(self.columns, k)
        if tile_bytes(m, rows, columns) > self.maximum_bytes:
            raise ValueError('Tile configuration exceeds memory before fetching weights')
        descriptor = dict(algorithm=ALGORITHM, source=source_id,
                          input_shape=list(x.shape), weight_shape=list(weight_shape),
                          input_sha256=hashlib.sha256(x.tobytes()).hexdigest(),
                          rows=self.rows, columns=self.columns,
                          numpy=np.__version__, dtype='float32')
        if self.kernel_id!='numpy-local-v1':
            descriptor['kernel']=self.kernel_id
        encoded = json.dumps(descriptor, sort_keys=True, separators=(',', ':'))
        job = hashlib.sha256(encoded.encode()).hexdigest()
        with self.lock:
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO tile_jobs(id,descriptor,status) VALUES (?,?,?)',
                                (job, encoded, 'running'))
            executed = 0
            for start in range(0, n, self.rows):
                end = min(n, start+self.rows)
                row = self.db.execute(
                    'SELECT next_column,partial,checksum FROM tile_rows WHERE job=? AND row_start=?',
                    (job, start)).fetchone()
                if row:
                    column, data, checksum = row
                    if hashlib.sha256(data).hexdigest() != checksum:
                        raise ValueError('Corrupted arithmetic checkpoint')
                    if not 0 <= column <= k or len(data) != m*(end-start)*4:
                        raise ValueError('Invalid arithmetic checkpoint')
                    accumulator = np.frombuffer(data, np.float32).reshape(m, end-start).copy()
                else:
                    column = 0
                    accumulator = np.zeros((m, end-start), np.float32)
                while column < k:
                    if (max_tiles is not None and executed >= max_tiles) or (
                            cancel is not None and cancel.is_set()):
                        return dict(id=job, status='paused', executed=executed)
                    next_column = min(k, column+self.columns)
                    weights = np.asarray(fetch(start, end, column, next_column))
                    if weights.shape != (end-start, next_column-column):
                        raise ValueError('Source returned a different matrix tile')
                    delta = self.kernel(x[:, column:next_column], weights, self.maximum_bytes)
                    if (delta.shape != accumulator.shape or delta.dtype != np.float32
                            or not np.isfinite(delta).all()):
                        raise ValueError('Invalid arithmetic result')
                    updated = accumulator + delta
                    if not np.isfinite(updated).all():
                        raise ValueError('Non-finite accumulated result')
                    data = updated.tobytes()
                    with self.db:
                        self.db.execute('BEGIN IMMEDIATE')
                        current = self.db.execute(
                            'SELECT next_column,partial,checksum FROM tile_rows '
                            'WHERE job=? AND row_start=?', (job, start)).fetchone()
                        if current and current[0] != column:
                            if (current[0] < column or
                                    hashlib.sha256(current[1]).hexdigest() != current[2]):
                                raise ValueError('Conflicting arithmetic checkpoint')
                            column = current[0]
                            accumulator = np.frombuffer(current[1], np.float32).reshape(
                                m, end-start).copy()
                            continue
                        self.db.execute('INSERT OR REPLACE INTO tile_rows VALUES (?,?,?,?,?)',
                                        (job, start, next_column, data,
                                         hashlib.sha256(data).hexdigest()))
                        self.db.execute(
                            'UPDATE tile_jobs SET committed_tiles=committed_tiles+1 WHERE id=?',
                            (job,))
                    accumulator, column = updated, next_column
                    executed += 1
                    if after_commit:
                        after_commit(dict(job=job, row=start, next_column=column))
            output = np.empty((m, n), np.float32)
            for start, column, data, checksum in self.db.execute(
                    'SELECT row_start,next_column,partial,checksum FROM tile_rows '
                    'WHERE job=? ORDER BY row_start', (job,)):
                if column != k or hashlib.sha256(data).hexdigest() != checksum:
                    raise ValueError('Incomplete or corrupted matrix result')
                end = min(n, start+self.rows)
                output[:, start:end] = np.frombuffer(data, np.float32).reshape(m, end-start)
            with self.db:
                self.db.execute("UPDATE tile_jobs SET status='completed' WHERE id=?", (job,))
            return dict(id=job, status='completed', executed=executed, output=output)
