"""
Neo4j Graph Database Client
Connection pool manager for barter exchange matching system
"""

from neo4j import GraphDatabase
from django.conf import settings
from constance import config
import logging

logger = logging.getLogger(__name__)


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

    def execute_read(self, query, parameters=None, database=None):
        """
        Execute read-only Cypher query

        Args:
            query: Cypher query string
            parameters: Dict of query parameters
            database: Database name (defaults to settings.NEO4J_DATABASE)

        Returns:
            List of Record objects
        """
        if self._driver is None:
            raise RuntimeError("Neo4j driver not initialized")

        db = database or settings.NEO4J_DATABASE

        with self._driver.session(database=db) as session:
            try:
                result = session.execute_read(
                    lambda tx: list(tx.run(query, parameters or {}))
                )
                return result
            except Exception as e:
                logger.error(f"Neo4j read query failed: {e}\nQuery: {query}\nParams: {parameters}")
                raise

    def execute_write(self, query, parameters=None, database=None):
        """
        Execute write Cypher query

        Args:
            query: Cypher query string
            parameters: Dict of query parameters
            database: Database name (defaults to settings.NEO4J_DATABASE)

        Returns:
            Result data as list of dicts
        """
        if self._driver is None:
            raise RuntimeError("Neo4j driver not initialized")

        db = database or settings.NEO4J_DATABASE

        with self._driver.session(database=db) as session:
            try:
                result = session.execute_write(
                    lambda tx: tx.run(query, parameters or {}).data()
                )
                return result
            except Exception as e:
                logger.error(f"Neo4j write query failed: {e}\nQuery: {query}\nParams: {parameters}")
                raise

    def verify_connectivity(self):
        """Test Neo4j connection"""
        try:
            with self._driver.session() as session:
                result = session.run("RETURN 1 AS test")
                return result.single()['test'] == 1
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
