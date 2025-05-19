#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line for line in fh.read().splitlines() if not line.startswith("#")]

setup(
    name="launcher",
    version="0.1.0",
    author="yz778",
    description="My GTK launcher",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yz778/launcher",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Environment :: X11 Applications :: GTK",
        "Environment :: Wayland",
    ],
    python_requires=">=3.6",
    install_requires=requirements,
    include_package_data=True,
    license="MIT",
    entry_points={
        "console_scripts": [
            "launcher=launcher.launcher:main",
        ],
    },
)
