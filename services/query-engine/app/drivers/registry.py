from app.drivers.base import DatabaseDriver, DriverFactory
from app.drivers.mysql import MySqlDriver
from app.drivers.sqlserver import SqlServerDriver
from app.models import Engine

DRIVER_REGISTRY: dict[Engine, DriverFactory] = {
    Engine.sqlserver: SqlServerDriver,
    Engine.mysql: MySqlDriver,
}


def get_driver(engine: Engine) -> DatabaseDriver:
    return DRIVER_REGISTRY[engine]()
