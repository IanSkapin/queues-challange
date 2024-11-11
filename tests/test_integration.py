import json
import time

import pika
import pytest
from uuid import uuid4
from pathlib import Path
from .sync_publisher import RMQPublisher


@pytest.fixture(scope="session")
def compose(docker_ip, docker_services):
    """Builds and runs Docker Compose services and yields pika interface."""
    attempts = 3
    port = docker_services.port_for("rabbitmq", 5672)
    time.sleep(30)
    yield f"amqp://guest:guest@{docker_ip}:{port}/%2F?connection_attempts={attempts}&heartbeat=3600"


data = [
    # (pii_list, image_file, ref_list)
    (['mimica'], 'Screenshot1.png',
     ['automates', 'repetitive', 'computer-based', 'tasks', 'through', 'human', 'observation']),
    (['alice', 'snowdrop'], 'Screenshot2.png',
     ['chapter', 'one', 'looking-glass', 'house', 'is', 'playing', 'with', 'a', 'white', 'kitten',
      'whom', 'she', 'calls', 'and']),
    (['ocr', 'pii'], 'Screenshot3.png',
     ['image', 'perform', 'bounding', 'boxes', 'list', 'of', 'terms']),
]


@pytest.mark.timeout(120)
def test_ocr_pipeline(compose):
    """Tests the OCR pipeline by sending images to RabbitMQ and verifying results."""
    url_chunk = compose.split('@')[1]
    ip, url_chunk = url_chunk.split(':', 1)
    port = int(url_chunk.split('/%2F')[0])
    ocr_in_messages: list[tuple] = []
    pii_in_messages: list[tuple] = []
    reference = {}
    for ppi_list, image_file, ref_list in data*10:
        path = 'tests' / Path(image_file)
        assert path.is_file(), f'{Path.cwd()}'
        with open(path, "rb") as f:
            img_data = f.read()
            uuid = str(uuid4())
            ocr_in_messages.append((uuid, img_data))
            pii_in_messages.append((uuid, json.dumps(ppi_list)))
            reference[uuid] = ref_list
    # declare publishers
    ocr_publisher = RMQPublisher(compose)
    pii_publisher = RMQPublisher(compose, exchange='pii', exchange_type='fanout')
    # declare consumer
    connection = pika.BlockingConnection(pika.ConnectionParameters(host="127.0.0.1", port=5672))
    channel = connection.channel()
    channel.exchange_declare(exchange='pii_out', exchange_type='fanout')
    queue_name = channel.queue_declare(queue="", durable=True, exclusive=True).method.queue
    channel.queue_bind(exchange='pii_out', queue=queue_name)
    results = 0

    def callback(ch, method, properties, body):
        nonlocal results
        results += 1
        pii_out = [x['text'] for x in json.loads(body.decode())]
        match = 'OK' if set(reference[properties.correlation_id]) == set(pii_out) else 'MISMATCH'

        print(f'Received [{results}/{len(reference)}] {properties.correlation_id=} {match}:\n\t{pii_out}')

        if results >= len(reference):
            channel.stop_consuming()
            connection.close()

    channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)

    print('Test data ready to publish')
    pii_publisher.publish_messages(queue="", messages=pii_in_messages)
    print('Done publishing to pii_in')
    ocr_publisher.publish_messages(queue="ocr_in", messages=ocr_in_messages)
    print('Done publishing to ocr_in')

    print('Starting consume loop')
    channel.start_consuming()

