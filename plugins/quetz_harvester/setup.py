from setuptools import setup

setup(
    name="quetz-harvester",
    # you should install libcflib using
    # $ pip install git+https://git@github.com/regro/libcflib@master --no-deps
    install_requires=["quetz", "libcflib"],
    entry_points={"quetz": ["quetz-harvester = quetz_harvester.main"]},
    packages=["quetz_harvester"],
)
