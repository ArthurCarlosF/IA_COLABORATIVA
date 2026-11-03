"""Read only the requested rows/columns from immutable safetensors sources."""
import hashlib
import re
import numpy as np
import torch
from .partition_store import PROFILES, DTYPES, CHUNK, canonical, read_range, tensor_header


class RemoteWeights:
    def __init__(self, model, revision, client, maximum_bytes=65536):
        if (model, revision) not in PROFILES.values():
            raise ValueError('Unapproved immutable checkpoint')
        self.model, self.revision, self.client = model, revision, client
        self.maximum_bytes = maximum_bytes
        self.headers = {}
        self.downloaded_bytes = 0

    def metadata(self, entry):
        filename = entry['file']
        if not re.fullmatch(r'model(?:-\d+-of-\d+)?\.safetensors', filename):
            raise ValueError('Invalid source file')
        url = f'https://huggingface.co/{self.model}/resolve/{self.revision}/{filename}'
        if filename not in self.headers:
            self.headers[filename] = tensor_header(self.client, url)
        descriptor = self.headers[filename][entry['source']]
        if descriptor['shape'] != entry['source_shape']:
            raise ValueError('Source shape differs from the operation')
        return url, descriptor

    def decode(self, raw, dtype):
        self.downloaded_bytes += len(raw)
        kind = {'F32': torch.float32, 'F16': torch.float16, 'BF16': torch.bfloat16}[dtype]
        return torch.frombuffer(raw, dtype=kind).float().numpy().copy()

    def matrix(self, entry):
        return RemoteMatrix(self, entry)

    def vector(self, entry):
        url, descriptor = self.metadata(entry)
        start, end = entry['rows']
        element = DTYPES[descriptor['dtype']]
        if (end-start)*4 > self.maximum_bytes:
            raise ValueError('Vector exceeds streaming buffer')
        return self.decode(read_range(self.client, url, descriptor['start']+start*element,
                                      (end-start)*element), descriptor['dtype'])


class RemoteMatrix:
    def __init__(self, source, entry):
        if len(entry['shape']) != 2:
            raise ValueError('Expected a matrix')
        self.source, self.entry = source, entry
        self.shape = tuple(entry['shape'])
        self.source_id = hashlib.sha256(canonical(dict(
            model=source.model, revision=source.revision, tensor=entry))).hexdigest()

    def fetch(self, row_start, row_end, col_start, col_end):
        if not (0 <= row_start < row_end <= self.shape[0]
                and 0 <= col_start < col_end <= self.shape[1]):
            raise ValueError('Invalid matrix tile bounds')
        if (row_end-row_start)*(col_end-col_start)*4 > self.source.maximum_bytes:
            raise ValueError('Matrix tile exceeds streaming buffer')
        url, descriptor = self.source.metadata(self.entry)
        element = DTYPES[descriptor['dtype']]
        width = self.entry['source_shape'][1]
        start = descriptor['start']
        if col_start==0 and col_end==width:
            size=(row_end-row_start)*width*element
            if size<=CHUNK:
                offset=start+(row_start+self.entry['rows'][0])*width*element
                return self.source.decode(read_range(self.source.client,url,offset,size),
                                          descriptor['dtype']).reshape(row_end-row_start,width)
        result = np.empty((row_end-row_start, col_end-col_start), np.float32)
        for local, row in enumerate(range(row_start, row_end)):
            offset = start + ((row+self.entry['rows'][0])*width+col_start)*element
            data = read_range(self.source.client, url, offset, (col_end-col_start)*element)
            result[local] = self.source.decode(data, descriptor['dtype'])
        return result
