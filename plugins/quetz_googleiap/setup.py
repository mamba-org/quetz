from setuptools import setup

plugin_name = "quetz-googleiap"

setup(
    name=plugin_name,
    install_requires=[],
    entry_points={
        "quetz.middlewares": [f"{plugin_name} = quetz_googleiap.middleware"],
    },
    packages=[
        "quetz_googleiap",
    ],
)
