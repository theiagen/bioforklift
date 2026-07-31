FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir poetry==2.3.2 poetry-plugin-export==1.9.0
WORKDIR /src
COPY pyproject.toml poetry.lock ./
RUN poetry export --only main -f requirements.txt -o /requirements.txt
COPY . .
RUN poetry build -f wheel

FROM python:3.12-slim

LABEL base.image="python:3.12-slim"
LABEL software="bioforklift"
LABEL description="Bioinformatics data automation between Terra, GCS, BigQuery, and BaseSpace"
LABEL website="https://github.com/theiagen/bioforklift"
LABEL license="https://github.com/theiagen/bioforklift/blob/main/LICENSE"
LABEL maintainer="Theiagen"
LABEL maintainer.email="developers@theiagen.com"

COPY --from=builder /requirements.txt /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir --no-deps /tmp/*.whl && \
    rm -rf /tmp/*
ENV LC_ALL=C.UTF-8
WORKDIR /data