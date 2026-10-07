"""API entrypoint (spec 11.1). Middleware, errors and routes are added from T02."""

from fastapi import FastAPI

app = FastAPI(title="Life OS", version="0.1.0")
