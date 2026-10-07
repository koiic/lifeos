"""Worker entrypoint (spec 11.1, 14.2): `procrastinate --app=app.worker.app worker`."""

import procrastinate

from app.platform import outbox
from app.platform.config import Settings, load_settings
from app.platform.jobs import Runtime, create_runtime, new_job_app, register_maintenance
from app.platform.logging import configure_logging


def create_job_app(settings: Settings, runtime: Runtime) -> procrastinate.App:
    """The worker's Procrastinate app with every platform and module job registered."""
    app = new_job_app(settings)
    outbox.register(app, runtime)
    register_maintenance(app)
    return app


configure_logging()
_settings = load_settings()
runtime = create_runtime(_settings)
app = create_job_app(_settings, runtime)
