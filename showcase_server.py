"""Executable Flask entry point for the explicit showcase_mvp profile."""

from showcase.flask_app import create_app, main

__all__ = ["create_app", "main"]

if __name__ == "__main__":
    main()
