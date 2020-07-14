import os
import setuptools


here = os.path.dirname(os.path.abspath(__file__))
version_ns = {}
with open(os.path.join(here, 'quetz', '_version.py')) as f:
    exec(f.read(), {}, version_ns)


setuptools.setup(
    name="quetz",
    version=version_ns['__version__'],
    author="The Quetz Development Team",
    description="The Mamba package server",
    long_description="The Mamba package server",
    url="https://github.com/thesnakepit/quetz",
    packages=setuptools.find_packages(),
    include_package_data=True,
    python_requires='>=3.7',
)
