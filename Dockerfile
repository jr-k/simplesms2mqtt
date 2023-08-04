FROM python:3.9.17-alpine3.17

RUN apk add --no-cache gammu-dev

RUN apk add --no-cache --virtual .build-deps git gcc musl-dev \
     && pip install pyyaml python-gammu paho-mqtt git+https://github.com/babca/python-gsmmodem \
     && apk del .build-deps gcc musl-dev

WORKDIR /app

COPY simplesms2mqtt.py .

ENTRYPOINT ["python", "/app/simplesms2mqtt.py"]
