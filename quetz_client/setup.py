import os

import setuptools

here = os.path.dirname(os.path.abspath(__file__))
version_ns = {}
with open(os.path.join(here, 'quetz_client', '_version.py')) as f:
    exec(f.read(), {}, version_ns)


setuptools.setup(
    name="quetz-client",
    version=version_ns['__version__'],
    author="The Quetz Development Team",
    description="A client for the Quetz package server",
    long_description="A client for the Quetz package server",
    url="https://github.com/thesnakepit/quetz",
    packages=setuptools.find_packages(),
    python_requires='>=3.6',
    extras_require={'dev': ['black', 'flake8', 'isort', 'pre-commit']},
    entry_points={'console_scripts': ['quetz-client = quetz_client:main']},
)
