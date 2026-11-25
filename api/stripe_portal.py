"""Vercel Python function for /api/stripe/portal."""

from ai.wsgi import app as _flask_app


def app(environ, start_response):
    environ["PATH_INFO"] = "/api/stripe/portal"
    return _flask_app(environ, start_response)


__all__ = ["app"]