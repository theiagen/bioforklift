# bioforklift

[![Tests](https://github.com/theiagen/bioforklift/actions/workflows/pytests.yml/badge.svg)](https://github.com/theiagen/bioforklift/actions/actions/workflows/pytests.yml)
[![PyPI version](https://badge.fury.io/py/bioforklift.svg)](https://badge.fury.io/py/bioforklift)
[![Downloads](https://pepy.tech/badge/bioforklift)](https://pepy.tech/project/bioforklift)
[![Python versions](https://img.shields.io/pypi/pyversions/bioforklift.svg)](https://pypi.org/project/bioforklift/)
[![License](https://img.shields.io/pypi/l/bioforklift.svg)](https://pypi.org/project/bioforklift/)

It is highly recommend to serve the documentation locally, as the instructions here are not as thorough as the documentation.

### Getting Setup

#### Installing bioforklift

To install bioforklift, run `pip install bioforklift`

#### Using the latest unpublished version

This project uses `poetry` for project management

If you don't have poetry present, please install it with:
`pip install poetry`

Then run poetry env activate which will create your environment:
`poetry env activate`

Next, install the dependencies listed in `poetry.lock` utilizing:
`poetry install`

The dependencies will be installed based on the locked versions in the `poetry.lock` file, since I already ran `poetry install` and pushed the lock file. For more information on poetry, read here: https://python-poetry.org/docs/basic-usage/

Finally, re authorize your gcloud authentication. This obtains your credentials via a web flow and stores them in 'the well-known location for Application Default Credentials'. Now any code/SDK you run will be able to find the credentials automatically. This is a good stand-in when you want to locally test code which would normally run on a server and use a server-side credentials file. `gcloud auth application-default login`

### Overview
<img src="assets/diagrams/Forklift_Base_Architecture.png" alt="bioforklift Base Architecture" width="800" style="max-width: 100%;" />
