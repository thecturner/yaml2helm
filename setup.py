"""Setup configuration for yaml2helm."""

from setuptools import setup, find_packages

setup(
    name="yaml2helm",
    version="0.1.0",
    packages=find_packages(),
    package_data={
        'yaml2helm': ['templates/*'],
    },
    include_package_data=True,
)
