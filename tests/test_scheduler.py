import asyncio
import pytest
from mesh.scheduler import FairScheduler,CapacityError

def test_admission_and_capacity():
    s=FairScheduler(2)
    s.admit('a')
    with pytest.raises(CapacityError):s.admit('a')
    s.admit('b')
    with pytest.raises(CapacityError):s.admit('c')
    s.leave('a');s.admit('c')
    assert s.status()['active']==2


def test_alternation_and_cancellation():
    async def run():
        s=FairScheduler()
        for user in ['a','b','c']:s.admit(user)
        order=[]
        async def work(user):
            for i in range(3):
                async with s.turn(user):
                    order.append(user)
                    await asyncio.sleep(.001)
        await asyncio.gather(work('a'),work('b'),work('c'))
        assert order==['a','b','c']*3
        async with s.turn('a'):
            pending=asyncio.create_task(work('b'))
            await asyncio.sleep(.001)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):await pending
        async with s.turn('c'):pass
        assert s.running is None and s.status()['waiting']==0
    asyncio.run(run())


def test_old_cleanup_cannot_remove_new_session():
    s=FairScheduler()
    s.admit('a','first');s.leave('a','first');s.admit('a','second')
    s.leave('a','first')
    assert s.active['a']=='second'
