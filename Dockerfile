FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir poetry==2.3.2 poetry-plugin-export==1.9.0

WORKDIR /bioforklift

COPY pyproject.toml poetry.lock ./
RUN poetry export --only main -f requirements.txt -o requirements.txt

FROM python:3.12-slim AS base

# install runtime dependencies from exported requirements which only rebuilds when poetry.lock changes
COPY --from=builder /bioforklift/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

WORKDIR /bioforklift

# copy everything allowed by .dockerignore
COPY . .

# install the bioforklift package without dependencies (installed in previous step)
# this layer is separate because it rebuilds whenever the source code changes
RUN pip install --no-cache-dir --no-deps .

# verify the image before it ships and clean up logs
RUN bioforklift --help > /dev/null && \
    pytest -q && \
    rm bioforklift.log

LABEL base.image="python:3.12-slim"
LABEL software="bioforklift"
LABEL description="Bioinformatics data automation between Terra, GCS, BigQuery, and BaseSpace"
LABEL website="https://github.com/theiagen/bioforklift"
LABEL license="https://github.com/theiagen/bioforklift/blob/main/LICENSE"
LABEL maintainer="Theiagen"
LABEL maintainer.email="developers@theiagen.com"

ENV LC_ALL=C

WORKDIR /data