ARG PYTHON=3.9
ARG DEBIAN="bullseye"

FROM python:${PYTHON}-slim-${DEBIAN}
ADD run.py ./
RUN apt-get update \
    && apt-get upgrade -y \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir pika==1.3.2

ENTRYPOINT ["python", "./run.py"]