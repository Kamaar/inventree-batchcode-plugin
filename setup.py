from setuptools import setup, find_packages

setup(
    name="inventree-batchcode-plugin",
    version="1.0",
    author="Simone Amadori",
    author_email="simone@amadori.bs.it",
    url="https://github.com/Kamaar/inventree-batchcode-plugin.git",
    description="Plugin InvenTree per generare codici batch progressivi.",
    packages=find_packages(),
    install_requires=["inventree"],
    entry_points={
        "inventree_plugins": ["BatchCodePlugin = batchcode_plugin.plugin:BatchCodePlugin"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
        "Framework :: InvenTree",
    ],
)
