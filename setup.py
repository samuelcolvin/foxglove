import sys

sys.stderr.write(
    """
===============================
Unsupported installation method
===============================
foxglove-web no longer supports installation with `python setup.py install`.
Please use `python -m pip install .` instead.
"""
)
sys.exit(1)


# The below code will never execute, however GitHub is particularly
# picky about where it finds Python packaging metadata.
# See: https://github.com/github/feedback/discussions/6456
#
# To be removed once GitHub catches up.

setup(
    name='foxglove-web',
    install_requires=[
        'arq>=0.23',
        'asyncpg>=0.23.0',
        'fastapi>=0.72',
        'itsdangerous>=1.1.0',
        'buildpg>=0.3.0',
        'httpx>=0.21.1',
        'pydantic>=1.8.2',
        'sentry-sdk>=1',
        'typer>=0.3.2',
        'uvicorn>=0.13.3',
    ],
)
