import logging
import datetime
import json
import sys
import os
import yaml
import threading
import signal
import argparse
import re
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
from gsmmodem.modem import GsmModem, Sms
from gsmmodem.pdu import Concatenation

CONFIG = {
    'mobileDevice': '/dev/mobile',
    'mobileBaudrate': 115200,
    'mobilePinCode': None,
    'mqttClientId': 'simplesms2mqtt',
    'mqttPrefix': 'sms',
    'mqttHost': 'localhost',
    'mqttPort': 1883,
    'mqttUsername': None,
    'mqttPassword': None,
    'logFile': None,
    'logLevel': 'INFO',
    'logStdout': False
}

TOPICS = {
    'READY': "ready",
    'SEND': "send",
    'SENT': "sent",
    'RECEIVED': "received",
    'ERROR': "error"
}

concat_sms = {}
modem = None
mqtt_thread = None
stop_event = threading.Event()


def camel_to_snake(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def parse_arguments():
    parser = argparse.ArgumentParser(description="SMS Manager Configuration")
    parser.add_argument('--mobileDevice', '-md', default=None, help='Modem Device')
    parser.add_argument('--mobileBaudrate', '-mb', default=None, type=int, help='Modem Baudrate')
    parser.add_argument('--mobilePinCode', '-mc', default=None, help='Modem Pin Code')
    parser.add_argument('--mqttClientId', '-i', default=None, help='Mqtt Client ID')
    parser.add_argument('--mqttPrefix', '-r', default=None, help='MQTT Prefix')
    parser.add_argument('--mqttHost', '-o', default=None, help='MQTT Host')
    parser.add_argument('--mqttPort', '-p', default=None, type=int, help='MQTT Port')
    parser.add_argument('--mqttUsername', '-u', default=None, help='MQTT Username')
    parser.add_argument('--mqttPassword', '-x', default=None, help='MQTT Password')
    parser.add_argument('--logFile', '-lf', default=None, help='Log File path')
    parser.add_argument('--logLevel', '-ll', default=None, help='Log Level')
    parser.add_argument('--logStdout', '-ls', default=False, action='store_true', help='Log to standard output')

    return parser.parse_args()


def load_from_args(args):
    global CONFIG

    if args.mobileDevice:
        CONFIG['mobileDevice'] = args.mobileDevice
    if args.mobileBaudrate:
        CONFIG['mobileBaudrate'] = args.mobileBaudrate
    if args.mobilePinCode:
        CONFIG['mobilePinCode'] = args.mobilePinCode
    if args.mqttClientId:
        CONFIG['mqttClientId'] = args.mqttClientId
    if args.mqttPrefix:
        CONFIG['mqttPrefix'] = args.mqttPrefix
    if args.mqttHost:
        CONFIG['mqttHost'] = args.mqttHost
    if args.mqttPort:
        CONFIG['mqttPort'] = args.mqttPort
    if args.mqttUsername:
        CONFIG['mqttUsername'] = args.mqttUsername
    if args.mqttPassword:
        CONFIG['mqttPassword'] = args.mqttPassword
    if args.logFile:
        CONFIG['logFile'] = args.logFile
    if args.logLevel:
        CONFIG['logLevel'] = args.logLevel
    if args.logStdout:
        CONFIG['logStdout'] = args.logStdout


def load_from_yaml(file_path):
    global CONFIG
    try:
        with open(file_path, 'r') as file:
            yaml_config = yaml.safe_load(file)
            for key in yaml_config:
                CONFIG[key] = yaml_config[key]
                logging.info(f"Yaml var {key} has been found")
    except FileNotFoundError:
        logging.error(f"File {file_path} doesn't exist.")


def load_from_env():
    global CONFIG

    for key in CONFIG:
        camel_case_key = camel_to_snake(key).upper()

        if camel_case_key in os.environ:
            CONFIG[key] = os.environ[camel_case_key]
            logging.info(f"Env var {camel_case_key} has been found")


def mqtt_prefix(suffix):
    global CONFIG

    return "{}/{}".format(CONFIG['mqttPrefix'], suffix)


def publish_mqtt(topic, payload):
    global CONFIG
    logging.info("MQTT publish to {}".format(topic))

    auth = {}

    if CONFIG['mqttUsername'] and CONFIG['mqttPassword']:
        auth = {
            'username': CONFIG['mqttUsername'],
            'password': CONFIG['mqttPassword']
        }

    publish.single(
        topic,
        payload=payload,
        hostname=CONFIG['mqttHost'],
        port=int(CONFIG['mqttPort']),
        auth=auth
    )


def handle_sms(sms):
    global TOPICS

    logging.info('SMS is coming...')
    concat = None
    message = None
    for i in sms.udh:
        if isinstance(i, Concatenation):
            concat = i
            break
    if concat:
        if concat.reference not in concat_sms:
            concat_sms[concat.reference] = {}

        concat_sms[concat.reference][concat.number] = sms.text
        # logging.info('Partial message received [{}/{}] reference {}'.format(len(concat_sms[concat.reference]), concat.parts, concat.reference))

        if len(concat_sms[concat.reference]) == concat.parts:
            sorted_parts = sorted(concat_sms[concat.reference].items())
            message = "".join([x[1] for x in sorted_parts])
            del concat_sms[concat.reference]
    else:
        message = sms.text

    if message:
        logging.info('SMS message fully received From: {}, Time: {}, Message:, {}'.format(sms.number, sms.time, message))
        publish_mqtt(mqtt_prefix(TOPICS['RECEIVED']), json.dumps({'number': sms.number, 'text': message}))


def send_sms(to, message):
    global modem, TOPICS

    try:
        modem.sendSms(to, message)
        current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        payload = {
            "result": "success",
            "datetime": current_time,
            "number": to,
            "text": message
        }
        publish_mqtt(mqtt_prefix(TOPICS['SENT']), json.dumps(payload))
        logging.info(f"Message sent to {to}.")
    except Exception as e:
        logging.error(f"Failed to send SMS: {str(e)}")
        publish_mqtt(mqtt_prefix(TOPICS['ERROR']), json.dumps({"error": str(e)}))


def on_connect(client, userdata, flags, rc):
    global TOPICS
    logging.info("Connected to MQTT Broker with result code: " + str(rc))
    client.subscribe(mqtt_prefix(TOPICS['SEND']))


def on_message(client, userdata, msg):
    payload = json.loads(msg.payload)
    number = payload.get("number")
    text = payload.get("text")
    if number and text:
        logging.info(f"Sending SMS to {number} with text: {text}")
        try:
            send_sms(number, text)
        except Exception as e:
            logging.error(f"Failed to send SMS: {str(e)}")
    else:
        logging.error("Invalid MQTT payload received.")


def on_log(client, userdata, level, buf):
    if level == mqtt.MQTT_LOG_ERR:
        logging.error("MQTT Error: " + buf)


def init_sender_mqtt_client():
    global CONFIG, stop_event

    MQTT_KEEPALIVE_INTERVAL = 45
    MQTT_RECONNECT_DELAY = 5

    client = mqtt.Client(client_id=CONFIG['mqttClientId'])
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_log = on_log

    if CONFIG['mqttUsername'] and CONFIG['mqttPassword']:
        client.username_pw_set(CONFIG['mqttUsername'], CONFIG['mqttPassword'])

    client.reconnect_delay_set(min_delay=1, max_delay=MQTT_RECONNECT_DELAY)

    try:
        client.connect(CONFIG['mqttHost'], int(CONFIG['mqttPort']), MQTT_KEEPALIVE_INTERVAL)
        logging.info("MQTT connected to {}:{} using prefix {}".format(CONFIG['mqttHost'], int(CONFIG['mqttPort']), CONFIG['mqttPrefix']))
        while not stop_event.is_set():
            client.loop(timeout=1.0)
    except Exception as e:
        logging.error(f"Failed to connect to MQTT broker. Error: {str(e)}")


def signal_handler(signal, frame):
    """Handle the SIGINT signal for a clean shutdown."""
    global modem, stop_event, mqtt_thread
    logging.info("Shutting down...")

    stop_event.set()

    if mqtt_thread:
        mqtt_thread.join()
        logging.info("Mqtt... DOWN")

    if modem:
        modem.close()
        logging.info("Modem... DOWN")


def start():
    global modem, mqtt_thread, TOPICS, CONFIG

    logging.info('Initializing modem...')
    modem = GsmModem(CONFIG['mobileDevice'], int(CONFIG['mobileBaudrate']), smsReceivedCallbackFunc=handle_sms)
    modem.smsTextMode = False
    modem.connect(CONFIG['mobilePinCode'])

    logging.info('Initializing MQTT client...')
    mqtt_thread = threading.Thread(target=init_sender_mqtt_client)
    mqtt_thread.start()

    logging.info('Waiting for new SMS message...')
    current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    publish_mqtt(
        mqtt_prefix(TOPICS['READY']),
        json.dumps({
            'device': CONFIG['mobileDevice'],
            'baudrate': int(CONFIG['mobileBaudrate']),
            'at': current_time
        })
    )


def configure_logging():
    global CONFIG

    log_level_str = CONFIG.get('logLevel', 'INFO').upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(log_level)

    if CONFIG['logFile']:
        file_handler = logging.FileHandler(CONFIG['logFile'])
        file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    if CONFIG['logStdout']:
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)


if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    configure_logging()
    args = parse_arguments()

    load_from_yaml(file_path='config.yaml')
    load_from_env()
    load_from_args(args)

    start()
