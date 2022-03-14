import asyncio
import concurrent.futures
import inspect
import json
import logging
import pickle
import time
import uuid
from abc import abstractmethod
from multiprocessing import get_context
from typing import Callable, Dict, Optional, Union

from quetz.config import Config
from quetz.jobs.models import JobStatus, Task, TaskStatus

try:
    import redis
    from rq import Queue

    rq_available = True
except ImportError:
    rq_available = False

logger = logging.getLogger("quetz.tasks")


def prepare_arguments(func: Callable, **resources):
    "select arguments for a function for resources based on its signature." ""

    # poorman's dependency injection pattern

    argnames = list(inspect.signature(func).parameters.keys())
    kwargs = {arg: value for arg, value in resources.items() if arg in argnames}

    return kwargs


def get_worker(config, num_procs=None):
    if config.configured_section("worker"):
        worker = config.worker_type
    else:
        worker = "thread"
    if worker == "thread":
        worker = ThreadingWorker(config)
    elif worker == "subprocess":
        worker = SubprocessWorker(config, executor_args={'max_workers': num_procs})
    elif worker == "redis":
        if rq_available:
            worker = RQManager(
                config.worker_redis_ip,
                config.worker_redis_port,
                config.worker_redis_db,
                config,
            )
        else:
            raise ValueError("redis and rq not installed on machine")
    else:
        raise ValueError("wrong configuration in worker.type")
    logger.debug(f"created worker of class {worker.__class__.__name__}")
    return worker


class WorkerProcess:
    def __init__(self, func, *args, **kwargs):
        self._exception = None
        self._connection = None
        self.func = func
        if isinstance(func, Callable):
            self._pickled_func = pickle.dumps(func)
        else:
            self._pickled_func = func
        self.func_args = args
        self.func_kwargs = kwargs

    @staticmethod
    def jobexecutor(conn, pickled_func, *args, **kwargs):
        """function executed in child process"""
        try:
            job_wrapper(pickled_func, *args, exc_passthrou=True, **kwargs)
        except Exception as exc:
            conn.send(exc)
            raise
        else:
            conn.send('ok')
        finally:
            conn.close()

    def fork_job(self):
        self.ctx = get_context("spawn")
        parent_conn, child_conn = self.ctx.Pipe(duplex=False)
        self._parent_conn = parent_conn

        self._process = self.ctx.Process(
            target=self.jobexecutor,
            args=(child_conn, self._pickled_func) + self.func_args,
            kwargs=self.func_kwargs,
        )
        self._process.start()

    def wait_for_job(self):
        exc = self._parent_conn.recv()
        self._process.join()
        if self._process.exitcode > 0:
            raise exc
        return

    def __call__(self):
        self.fork_job()
        self.wait_for_job()


def job_wrapper(
    func: Union[Callable, bytes],
    config,
    task_id=None,
    exc_passthrou=False,
    **kwargs,
):

    # database connections etc. are not serializable
    # so we need to recreate them in the process.
    # This allows us to manage database connectivity prior
    # to running a job.

    import logging
    import pickle

    from quetz.authorization import Rules
    from quetz.config import configure_logger
    from quetz.dao import Dao
    from quetz.database import get_session
    from quetz.deps import get_remote_session

    configure_logger(config)

    logger = logging.getLogger("quetz.worker")

    pkgstore = kwargs.pop("pkgstore", None)
    db = kwargs.pop("db", None)
    dao = kwargs.pop("dao", None)
    auth = kwargs.pop("auth", None)
    session = kwargs.pop("session", None)

    if db:
        close_session = False
    elif dao:
        db = dao.db
        close_session = False
    else:
        db = get_session(config.sqlalchemy_database_url)
        close_session = True

    user_id: Optional[str]
    if task_id:
        task = db.query(Task).filter(Task.id == task_id).one_or_none()
        # take extra arguments from job definition
        if task.job.extra_args:
            job_extra_args = json.loads(task.job.extra_args)
            kwargs.update(job_extra_args)
        if task.job.owner_id:
            user_id = str(uuid.UUID(bytes=task.job.owner_id))
        else:
            user_id = None
    else:
        task = None
        user_id = None

    if not pkgstore:
        pkgstore = config.get_package_store()

    dao = Dao(db)

    if not auth:
        browser_session: Dict[str, str] = {}
        api_key = None
        if user_id:
            browser_session['user_id'] = user_id
        auth = Rules(api_key, browser_session, db)
    if not session:
        session = get_remote_session()

    if task:
        task.status = TaskStatus.running
        task.job.status = JobStatus.running
        db.commit()

    callable_f: Callable = pickle.loads(func) if isinstance(func, bytes) else func

    extra_kwargs = prepare_arguments(
        callable_f,
        dao=dao,
        auth=auth,
        session=session,
        config=config,
        pkgstore=pkgstore,
        user_id=user_id,
    )

    kwargs.update(extra_kwargs)

    try:
        callable_f(**kwargs)
    except Exception as exc:
        if task:
            task.status = TaskStatus.failed
        logger.error(
            f"exception occurred when evaluating function {callable_f.__name__}:{exc}"
        )
        if exc_passthrou:
            raise exc
    else:
        if task:
            task.status = TaskStatus.success
    finally:
        db.commit()
        if close_session:
            db.close()


class AbstractWorker:
    @abstractmethod
    def execute(self, func, **kwargs):
        """execute function func on the worker."""

    @abstractmethod
    def wait(self):
        """wait for all jobs to finish"""


class AbstractJob:
    """Single job (function call)"""

    @property
    @abstractmethod
    def done(self):
        """job status"""


class FutureJob(AbstractJob):
    def __init__(self, future: concurrent.futures.Future):
        self._future = future

    @property
    def status(self):
        is_running = self._future.running()
        if is_running:
            return "running"

        completed = self._future.done()
        if completed:
            if self._future.exception():
                return "failed"
            else:
                return "success"
        return "pending"

    @property
    def done(self):
        return self.status in ["failed", "success"]

    async def wait(self, waittime=0.1):
        while not self.done:
            await asyncio.sleep(waittime)
        if self.status == "failed":
            raise self._future.exception()


class PoolExecutorWorker(AbstractWorker):
    _executor = None
    executor_cls: type

    def __init__(
        self,
        config: Config,
        executor_args: dict = {},
    ):

        if self._executor is None:
            logger.debug(f"creating a new executor of class {self.executor_cls}")
            type(self)._executor = self.executor_cls(**executor_args)

        self.config = config
        self.future = None

    def execute(self, func, *args, **kwargs):

        self.future = self._executor.submit(
            job_wrapper, func, self.config, *args, **kwargs
        )
        return FutureJob(self.future)

    async def wait(self):
        "helper function mainly used in tests"
        loop = asyncio.get_event_loop()
        if self.future:
            return await loop.run_in_executor(None, self.future.result)


class ThreadingWorker(PoolExecutorWorker):
    """simple worker that runs jobs in threads"""

    executor_cls = concurrent.futures.ThreadPoolExecutor


class SubprocessWorker(PoolExecutorWorker):
    """subprocess worker runs each job in a subprocess and destroys it after
    the job is finished to release resources
    """

    executor_cls = concurrent.futures.ProcessPoolExecutor

    def __init__(self, config: Config, executor_args: dict = {}):
        if 'max_workers' not in executor_args:
            executor_args['max_workers'] = 2
        super().__init__(config, executor_args)

    def execute(self, func, *args, **kwargs):
        process = WorkerProcess(func, self.config, *args, **kwargs)
        self.future = self._executor.submit(process)
        return FutureJob(self.future)


class RQManager(AbstractWorker):
    def __init__(
        self,
        host,
        port,
        db,
        config: Config,
        no_testing=True,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.config = config
        self.conn = redis.StrictRedis(host=self.host, port=self.port, db=self.db)
        self.queue = Queue(connection=self.conn, is_async=no_testing)

    def execute(self, func, *args, **kwargs):
        self.job = self.queue.enqueue(
            job_wrapper,
            func,
            self.config,
            *args,
            **kwargs,
        )

    # the function is blocking in nature and is declared
    # as 'async' so as to make redis-queue compatible
    # with the testing framework. It is not to be used otherwise.
    async def wait(self):
        while not self.job.is_finished:
            time.sleep(1)
        if self.job.result:
            return self.job.result
