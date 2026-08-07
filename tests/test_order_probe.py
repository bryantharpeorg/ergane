import asyncio
from temporalio import workflow, activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

@activity.defn
async def fast(name: str) -> str:
    return name

@workflow.defn
class OrderWF:
    @workflow.run
    async def run(self) -> list[str]:
        order = []
        async def worker(name: str) -> None:
            await workflow.execute_activity(fast, name, start_to_close_timeout=10)
            order.append(name)
        tasks = [asyncio.create_task(worker(n)) for n in ["us1", "us2", "us3"]]
        await asyncio.gather(*tasks)
        return order

async def test_order_probe():
    env = await WorkflowEnvironment.start_time_skipping()
    try:
        async with Worker(env.client, task_queue="tq", workflows=[OrderWF], activities=[fast]):
            for i in range(5):
                res = await env.client.execute_workflow(OrderWF.run, id=f"w{i}", task_queue="tq")
                print("ORDER:", res)
    finally:
        await env.shutdown()
