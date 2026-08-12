# build context = repo root
FROM python:3.11-slim

ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10

WORKDIR /app

COPY docker/python-pip-bootstrap.sh docker/python-pip-install.sh /tmp/
RUN chmod +x /tmp/python-pip-bootstrap.sh /tmp/python-pip-install.sh && /tmp/python-pip-bootstrap.sh

COPY packages/core /opt/sigtrades/packages/core
RUN /tmp/python-pip-install.sh /opt/sigtrades/packages/core

COPY services/cloud-executor/requirements.txt ./requirements.txt
RUN /tmp/python-pip-install.sh -r requirements.txt

COPY services/cloud-executor/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
