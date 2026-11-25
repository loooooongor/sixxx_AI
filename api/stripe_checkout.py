"""Vercel Python function for /api/stripe/checkout."""

from ai.wsgi import app as _flask_app


def app(environ, start_response):
    environ["PATH_INFO"] = "/api/stripe/checkout"
    return _flask_app(environ, start_response)


__all__ = ["app"]