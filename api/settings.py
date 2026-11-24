"""Vercel Python function for /api/settings."""

from ai.wsgi import app as _flask_app


def app(environ, start_response):
    # Vercel may pass the function's own path; force the route Flask expects.
    environ["PATH_INFO"] = "/api/settings"
    return _flask_app(environ, start_response)


__all__ = ["app"]