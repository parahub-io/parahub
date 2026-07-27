"""
Neo4j Graph Database Client
Connection pool manager for barter exchange matching system
"""

from neo4j import GraphDatabase, unit_of_work
from django.conf import settings
from constance import config
import logging
import threading

logger = logging.getLogger(__name__)

# Hard per-query deadline (seconds). The Python driver exposes no client-side
# read timeout: if the server accepts TCP but never answers (wedged JVM,
# threads stuck in uninterruptible I/O), tx.run() blocks forever and takes the
# uvicorn worker with it. Callers with legitimately long queries (bulk sync,
# GDS) pass an explicit `timeout=`.
DEFAULT_QUERY_TIMEOUT = 10.0


class Neo4jQueryTimeout(Exception):
    """Raised when a Neo4j query exceeds its client-side deadline"""
    pass


def _run_with_deadline(fn, timeout_seconds, description):
    """
    Run fn() in a disposable daemon thread and abandon it after the deadline.

    A per-call thread (not a shared executor) so that abandoned hung calls can
    never exhaust a worker pool and reintroduce the infinite hang. A leaked
    thread and its bolt connection are reclaimed when the connection dies.
    """
    outcome = {}

    def target():
        try:
            outcome['value'] = fn()
        except BaseException as e:  # propagate everything, including driver errors
            outcome['error'] = e

    worker = threading.Thread(target=target, daemon=True, name='neo4j-query')
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise Neo4jQueryTimeout(
            f"Neo4j query exceeded {timeout_seconds}s deadline: {description}"
        )
    if 'error' in outcome:
        raise outcome['error']
    return outcome.get('value')


class Neo4jClient:
    """
    Singleton Neo4j connection pool manager

    Usage:
        client = Neo4jClient()
        results = client.execute_read(query, parameters)
    """
    _instance = None
    _driver = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._initialize_driver()
        return cls._instance

    @classmethod
    def _initialize_driver(cls):
        """Initialize Neo4j driver with connection pool (uses dynamic config from Constance)"""
        try:
            cls._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_lifetime=config.NEO4J_MAX_CONNECTION_LIFETIME,
                max_connection_pool_size=config.NEO4J_MAX_CONNECTION_POOL_SIZE,
                connection_acquisition_timeout=config.NEO4J_CONNECTION_ACQUISITION_TIMEOUT,
            )
            logger.info(f"Neo4j driver initialized: {settings.NEO4J_URI}")
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j driver: {e}")
            raise

    def execute_read(self, query, parameters=None, database=None, timeout=None):
        """
        Execute read-only Cypher query

        Args:
            query: Cypher query string
            parameters: Dict of query parameters
            database: Database name (defaults to settings.NEO4J_DATABASE)
            timeout: Per-query deadline in seconds (default: DEFAULT_QUERY_TIMEOUT)

        Returns:
            List of Record objects
        """
        if self._driver is None:
            raise RuntimeError("Neo4j driver not initialized")

        db = database or settings.NEO4J_DATABASE
        deadline = timeout or DEFAULT_QUERY_TIMEOUT

        def run():
            with self._driver.session(database=db) as session:
                # Server-side transaction timeout aborts runaway queries on a
                # healthy server (cycle enumeration can explode combinatorially)
                work = unit_of_work(timeout=deadline)(
                    lambda tx: list(tx.run(query, parameters or {}))
                )
                return session.execute_read(work)

        try:
            # Client deadline sits above the server-side timeout so a healthy
            # server gets to abort the query first; also covers pool acquisition.
            return _run_with_deadline(run, deadline + 2.0, query)
        except Neo4jQueryTimeout as e:
            logger.error(f"{e}\nParams: {parameters}")
            raise
        except Exception as e:
            logger.error(f"Neo4j read query failed: {e}\nQuery: {query}\nParams: {parameters}")
            raise

    def execute_write(self, query, parameters=None, database=None, timeout=None):
        """
        Execute write Cypher query

        Args:
            query: Cypher query string
            parameters: Dict of query parameters
            database: Database name (defaults to settings.NEO4J_DATABASE)
            timeout: Per-query deadline in seconds (default: DEFAULT_QUERY_TIMEOUT)

        Returns:
            Result data as list of dicts
        """
        if self._driver is None:
            raise RuntimeError("Neo4j driver not initialized")

        db = database or settings.NEO4J_DATABASE
        deadline = timeout or DEFAULT_QUERY_TIMEOUT

        def run():
            with self._driver.session(database=db) as session:
                work = unit_of_work(timeout=deadline)(
                    lambda tx: tx.run(query, parameters or {}).data()
                )
                return session.execute_write(work)

        try:
            return _run_with_deadline(run, deadline + 2.0, query)
        except Neo4jQueryTimeout as e:
            logger.error(f"{e}\nParams: {parameters}")
            raise
        except Exception as e:
            logger.error(f"Neo4j write query failed: {e}\nQuery: {query}\nParams: {parameters}")
            raise

    def verify_connectivity(self):
        """Test Neo4j connection"""
        try:
            def run():
                with self._driver.session() as session:
                    result = session.run("RETURN 1 AS test")
                    return result.single()['test'] == 1

            return _run_with_deadline(run, DEFAULT_QUERY_TIMEOUT, "connectivity check")
        except Exception as e:
            logger.error(f"Neo4j connectivity test failed: {e}")
            return False

    def close(self):
        """Close Neo4j driver (call on application shutdown)"""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j driver closed")

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing)"""
        if cls._driver:
            cls._driver.close()
        cls._instance = None
        cls._driver = None
