from app.drivers.base import DatabaseDriver, DriverFactory
from app.drivers.base import DriverNotImplementedError
from app.drivers.sqlserver import SqlServerDriver
from app.models import Engine

DRIVER_REGISTRY: dict[Engine, DriverFactory] = {
    Engine.sqlserver: SqlServerDriver,
}


def get_driver(engine: Engine) -> DatabaseDriver:
    driver_factory = DRIVER_REGISTRY.get(engine)
    if driver_factory is None:
        raise DriverNotImplementedError(f"{engine.value} is not supported in V1.")
    return driver_factory()
