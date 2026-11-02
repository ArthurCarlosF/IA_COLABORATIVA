"""Alternância cooperativa por identidade; não considera saldo para prioridade."""
import asyncio
from collections import deque
from contextlib import asynccontextmanager

class CapacityError(ValueError):pass

class FairScheduler:
    def __init__(self,max_sessions=8):
        if not 1<=max_sessions<=8:raise ValueError('Capacidade deve estar entre 1 e 8')
        self.max_sessions=max_sessions
        self.active={}
        self.queues={}
        self.order=deque()
        self.running=None
        self.turns=0

    def admit(self,user,ticket=None):
        if user in self.active:raise CapacityError('Já há uma tarefa desta conta em andamento')
        if len(self.active)>=self.max_sessions:raise CapacityError('Capacidade de sessões atingida; aguarde')
        self.active[user]=ticket

    def leave(self,user,ticket=None):
        if ticket is None or self.active.get(user)==ticket:self.active.pop(user,None)

    def _dispatch(self):
        if self.running is not None:return
        while self.order:
            user=self.order.popleft()
            queue=self.queues.get(user)
            if not queue:continue
            future=queue.popleft()
            if queue:self.order.append(user)
            else:self.queues.pop(user,None)
            if future.done():continue
            self.running=future
            self.turns+=1
            future.set_result(None)
            return

    @asynccontextmanager
    async def turn(self,user,disconnected=None):
        if user not in self.active:raise ValueError('Sessão não admitida')
        future=asyncio.get_running_loop().create_future()
        if user not in self.queues:
            self.queues[user]=deque()
            self.order.append(user)
        self.queues[user].append(future)
        self._dispatch()
        try:
            while not future.done():
                if disconnected and await disconnected():raise asyncio.CancelledError()
                try:await asyncio.wait_for(asyncio.shield(future),.2)
                except asyncio.TimeoutError:pass
            yield
        finally:
            if self.running is future:self.running=None
            else:
                queue=self.queues.get(user)
                if queue and future in queue:
                    queue.remove(future)
                    if not queue:
                        self.queues.pop(user,None)
                        try:self.order.remove(user)
                        except ValueError:pass
            self._dispatch()

    def status(self):
        return dict(active=len(self.active),capacity=self.max_sessions,waiting=sum(len(q) for q in self.queues.values()),turns=self.turns,policy='round-robin-by-account',prefill_quantum=32)
