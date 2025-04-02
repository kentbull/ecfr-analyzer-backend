import asyncio
import logging
import logging.config
import os
import shelve
import signal
import ssl
from typing import Any

import falcon
import falcon.asgi
import httpx
import uvloop
from hypercorn import Config
from hypercorn.asyncio import serve

from ecfr import endpoints

logging.config.fileConfig("logging.conf")
logger = logging.getLogger("ecfr")

uvloop.install()
shutdown_event = asyncio.Event()

CACHE="ecfr_cache"

def _shutdown_signal_handler(*_: Any) -> None:
    logger.info("SIGTERM received, shutting down gracefully")
    shutdown_event.set()


# For reporting SSL errors
def _exception_handler(loop, context):
    exception = context.get("exception")
    if isinstance(exception, ssl.SSLError):
        pass  # Handshake failure
    else:
        loop.default_exception_handler(context)

def cors_middleware():
    return falcon.CORSMiddleware(
                allow_origins="*",
                allow_credentials="*",
                expose_headers=[
                    "accept",
                    "accept-encoding",
                    "accept-language",
                    "authorization",
                    "origin",
                    "cesr-attachment",
                    "cesr-date",
                    "content-type",
                ],
            )

def ecfr_app():
    return falcon.asgi.App(
        middleware=[cors_middleware()],
    )

def configure_loop(loop: asyncio.AbstractEventLoop):
    loop.set_debug(False)  # Disable asyncio debug logs
    for sig in [signal.SIGTERM, signal.SIGINT]:
        loop.add_signal_handler(sig, _shutdown_signal_handler)
    loop.set_exception_handler(_exception_handler)
    return loop

def configure_hypercorn(port: int):
    config = Config()
    config.bind = [f"127.0.0.1:{port}"]
    # Hypercorn logs
    config.loglevel = "CRITICAL"
    config.use_reloader = False
    config.accesslog = None  # Access logs
    config.errorlog = None  # Error logs
    config.access_logger = logging.getLogger("hypercorn.access")
    config.error_logger = logging.getLogger("hypercorn.error")
    config.graceful_timeout = 120
    return config

async def start():
    port = os.environ.get("EFCR_PORT", 3001)

    # Hypercorn config
    config = configure_hypercorn(port)
    # Configure Hypercorn asyncio event loop
    configure_loop(asyncio.get_event_loop())

    # Open cache at app level
    with shelve.open(CACHE) as cache:
        limits = httpx.Limits(max_connections=1, max_keepalive_connections=1)
        # Use a common async http client for all requests
        async with httpx.AsyncClient(http2=False, limits=limits, timeout=30.00) as client:
            title_service = endpoints.TitleService(client, cache)

            app = ecfr_app()
            app.add_route("/health", endpoints.HealthResource())
            app.add_route("/word-count", endpoints.WordCountResource())
            app.add_route("/titles", endpoints.TitlesResource(title_service))
            app.add_route("/title-counts", endpoints.TitleCountsResource(title_service))
            app.add_route("/title-counts/{title}", endpoints.TitleCountResource(title_service))
            app.add_route("/section-counts", endpoints.SectionCountsResource(title_service))

            # Falcon App
            logger.info("Starting ECFR server on port %s", port)
            await serve(app, config, shutdown_trigger=shutdown_event.wait)


if __name__ == "__main__":
    asyncio.run(
        start(),
    )