"""
VCL utils - a setuptools based python package.
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages

# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, "README.rst"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="vcl_utils",
    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version="1.0",
    description="An example Python package",
    long_description=long_description,
    # Package url
    url="https://github.com/reustleco/dojo-vcl/vcl-utils/",
    # Author details
    author="Muhammad Rehan",
    author_email="muhammed.rehan@strata.co.jp",
    license="MIT",
    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # Maturity scale:
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.9",
    ],
    # keywords that are most relevant
    keywords="vcl utils vcl-utils vcl_utils",
    packages=find_packages(exclude=["contrib", "docs", "tests"]),
    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
        "awscli>=1.22.73",
        "boto3>=1.21.3",
        "pika>=1.2.0",
        "pytz>=2021.3",
        "kubernetes>=21.7.0",
    ],
)
