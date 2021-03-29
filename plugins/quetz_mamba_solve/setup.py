from setuptools import setup

setup(
    name="quetz-mamba_solve",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-mamba_solve = quetz_mamba_solve.main"]},
    packages=["quetz_mamba_solve"],
)
