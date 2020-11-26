from setuptools import setup

plugin_name = "quetz-runexports"

setup(
    name=plugin_name,
    install_requires="quetz",
    entry_points={
        "quetz": [f"{plugin_name} = quetz_runexports.main"],
        "quetz.migrations": [f"{plugin_name} = quetz_runexports.migrations"],
        "quetz.models": [f"{plugin_name} = quetz_runexports.db_models"],
    },
    packages=[
        "quetz_runexports",
        "quetz_runexports.migrations",
        "quetz_runexports.migrations.versions",
    ],
)
