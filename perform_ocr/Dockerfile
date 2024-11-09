ARG PYTHON=3.9
ARG DEBIAN="bullseye"

FROM python:${PYTHON}-slim-${DEBIAN}
ADD run.py ./
RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install --no-install-recommends -y tesseract-ocr libtesseract-dev \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir pika==1.3.2  pytesseract

ENTRYPOINT ["python", "./run.py"]