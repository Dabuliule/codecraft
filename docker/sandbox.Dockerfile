FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        git \
        jq \
        ripgrep \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.19

WORKDIR /workspace
