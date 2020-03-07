from importlib.machinery import SourceFileLoader
from pathlib import Path

from setuptools import setup

description = 'Tools for Starlette'
THIS_DIR = Path(__file__).resolve().parent
try:
    long_description = '\n\n'.join(
        [THIS_DIR.joinpath('README.md').read_text(), THIS_DIR.joinpath('HISTORY.md').read_text()]
    )
except FileNotFoundError:
    long_description = description

# avoid loading the package before requirements are installed:
version = SourceFileLoader('version', 'foxglove/version.py').load_module()

setup(
    name='foxglove-web',
    version=str(version.VERSION),
    description=description,
    long_description=long_description,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.8',
        'Intended Audience :: Developers',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Operating System :: Unix',
        'Operating System :: POSIX :: Linux',
        'Environment :: MacOS X',
        'Topic :: Internet',
    ],
    author='Samuel Colvin',
    author_email='s@muelcolvin.com',
    url='https://github.com/samuelcolvin/foxglove',
    license='MIT',
    packages=['foxglove', 'foxglove.db'],
    entry_points="""
        [console_scripts]
        foxglove=foxglove.__main__:cli
    """,
    python_requires='>=3.8',
    zip_safe=True,
    install_requires=[
        'starlette>=0.13.2',
        'arq>=0.18',
        'pydantic>=1.4',
        'sentry-sdk>=0.14',
        'uvicorn>=0.11.3',
        'uvloop>=0.14.0',
        'asyncpg>=0.17.0',
        'buildpg>=0.2.1',
    ],
    extras_require={'all': ['cryptography>=2.4.1', 'ipython>=7.7.0']},
)