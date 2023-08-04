# Prerequisites

You need a GSM dongle "compatible" with Gammu : https://wammu.eu/phones/  
Even if your dongle is not listed, it should works with.

# Install
For Docker, run it by executing the following commmand:

```bash
docker run \
    -d \
    --name simplesms2mqtt \
    --restart=always \
    --device=/dev/ttyUSB0:/dev/mobile \
    -e MOBILE_DEVICE="/dev/sms" \
    -e MOBILE_BAUDRATE=115200 \
    -e MOBILE_PIN_CODE=1234 \
    -e MQTT_CLIENT_ID="simplesms2mqtt" \
    -e MQTT_PREFIX="sms" \
    -e MQTT_HOST="192.168.1.1" \
    -e MQTT_PORT=1883 \
    -e MQTT_USER="username" \
    -e MQTT_PASSWORD="password" \
    jierka/simplesms2mqtt
```
For Docker-Compose, use the following yaml:


```yaml
version: '3'
services:
  sms2mqtt:
    container_name: simplesms2mqtt
    restart: unless-stopped
    image: jierka/simplesms2mqtt
    devices:
    - /dev/serial/by-id/usb-HUAWEI_HUAWEI_Mobile-if00-port0:/dev/mobile
    environment:
    - MOBILE_DEVICE=/dev/mobile
    - MOBILE_BAUDRATE=115200
    - MOBILE_PIN_CODE=1234
    - MQTT_CLIENT_ID=simplesms2mqtt
    - MQTT_PREFIX=sms
    - MQTT_HOST=192.168.1.1
    - MQTT_PORT=1883
    - MQTT_USERNAME=username
    - MQTT_PASSWORD=password
    - LOG_LEVEL=INFO
```

# Usage

### Send

The default {prefix} for topics is sms2mqtt.  

To send SMS: 
1. Publish this payload to topic **sms/send** :  
`{"number":"+33612345678", "text":"This is a test message"}`  
2. SMS is sent  
3. A confirmation is sent back through MQTT to topic **sms/sent** :  
`{"result":"success", "datetime":"2021-01-23 13:00:00", "number":"+3312345678", "text":"test message"}`

### Receive

Received SMS are published to topic **sms/received** like this :  
`{"datetime":"2021-01-23 13:30:00", "number":"+3312345678", "text":"hey you!"}`

# Troubleshoot
### Logs
You need to have a look at logs using :  
`docker logs simplesms2mqtt`

# Updating
To update to the latest Docker image:
```bash
docker stop simplesms2mqtt
docker rm simplesms2mqtt
docker rmi jierka/simplesms2mqtt
# Now run the container again, Docker will automatically pull the latest image.
```
