# job_queue.py

import asyncio
import threading
from concurrent.futures import Future as ThreadFuture

class JobQueue:
    def __init__(self):
        self.__job_queue = asyncio.Queue()
        self.__loop = None
        self.__isRunning = False
        self.__stopFlag = True
        self.__dispatchThread = None

    async def __dispatcher(self):
        while not self.__stopFlag:
            job, args, kwargs, future = await self.__job_queue.get()

            try:
                if asyncio.iscoroutinefunction(job):
                    result = await job(*args, **kwargs)
                else:
                    # Run the synchronous job in an executor
                    result = await self.__loop.run_in_executor(None, job, *args, **kwargs)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
    
    def start(self):
        if self.__isRunning:
            return
        
        self.__isRunning = True
        self.__stopFlag = False
        self.__dispatchThread = threading.Thread(target=self.__run_loop)
        self.__dispatchThread.start()

    def stop(self):
        if not self.__isRunning:
            return
        
        self.__isRunning = False
        self.__stopFlag = True
        self.__dispatchThread.join()


    def __run_loop(self):
        self.__loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.__loop)
        self.__loop.run_until_complete(self.__dispatcher())

    def submit_job(self, job, *args, **kwargs):
        future = ThreadFuture()
        asyncio.run_coroutine_threadsafe(self.__job_queue.put((job, args, kwargs, future)), self.__loop)
        return asyncio.wrap_future(future)
