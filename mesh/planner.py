from functools import lru_cache

def plan(layer_bytes, capacities, first_bytes=0, last_bytes=0):
    """Partições contíguas não vazias; minimiza pico de ocupação relativa.

    Capacidades são orçamento de pesos, após reservar runtime e KV cache.
    Não promete estimativa de velocidade a partir de memória.
    """
    if not layer_bytes or not capacities or len(capacities)>len(layer_bytes):
        raise ValueError('Invalid layer or worker count')
    if any(type(n) is not int or n<=0 for n in [*layer_bytes,*capacities]):
        raise ValueError('Byte budgets must be positive integers')
    prefix=[0]
    for size in layer_bytes:prefix.append(prefix[-1]+size)
    count=len(capacities)
    @lru_cache(None)
    def solve(worker,start):
        if worker==count:
            return (0,[]) if start==len(layer_bytes) else None
        best=None
        for end in range(start+1,len(layer_bytes)-(count-worker-1)+1):
            size=prefix[end]-prefix[start]+(first_bytes if worker==0 else 0)+(last_bytes if worker==count-1 else 0)
            if size>capacities[worker]:continue
            tail=solve(worker+1,end)
            if tail is None:continue
            cost=max(size/capacities[worker],tail[0])
            if best is None or cost<best[0]:
                best=(cost,[(start,end)]+tail[1])
        return best
    answer=solve(0,0)
    if answer is None:raise ValueError('Insufficient memory for contiguous partition')
    return answer[1]
