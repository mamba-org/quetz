from setuptools import setup

setup(
    name="quetz-harvester",
    # you should install libcflib using
    # $ pip install git+https://git@github.com/regro/libcflib@master --no-deps
    install_requires=["libcflib"],
    entry_points={
        "quetz.jobs": ["quetz-harvester=quetz_harvester.jobs"],
    },
    packages=["quetz_harvester"],
)
