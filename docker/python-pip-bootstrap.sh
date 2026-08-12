#!/bin/sh
# Docker 构建时 pip 初始化：升级 pip，可选镜像，提高超时与重试。
set -eu

pip install --upgrade pip

if [ -n "${PIP_INDEX_URL:-}" ]; then
  pip config set global.index-url "${PIP_INDEX_URL}"
  if [ -n "${PIP_TRUSTED_HOST:-}" ]; then
    pip config set global.trusted-host "${PIP_TRUSTED_HOST}"
  fi
fi
