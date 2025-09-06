from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line for line in fh.read().splitlines() if not line.startswith("#")]

setup(
    name="launcher",
    version="1.0.0",
    author="yz778",
    description="GTK Launcher",
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
    python_requires=">=3.12",
    install_requires=requirements,
    include_package_data=True,
    license="MIT",
)
