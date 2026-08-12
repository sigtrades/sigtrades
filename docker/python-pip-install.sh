#!/bin/sh
# 用法: docker/python-pip-install.sh -r requirements.txt
#       docker/python-pip-install.sh /path/to/local/pkg
set -eu

pip install --default-timeout="${PIP_DEFAULT_TIMEOUT:-300}" \
  --retries="${PIP_RETRIES:-10}" \
  --no-cache-dir \
  "$@"
