import asyncio


async def gather_with_concurrency(concurrency, *tasks, **kwargs):
    """
    This is just a wrapper around the asyncio.gather that configures
    max concurrent number of I/O tasks via semaphores.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def sem_task(task):
        async with semaphore:
            return await task

    sem_tasks = [sem_task(task) for task in tasks]
    return await asyncio.gather(*sem_tasks, **kwargs)
