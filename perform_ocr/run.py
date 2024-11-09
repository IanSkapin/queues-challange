import io
import os
import csv
import pika
import json
import signal
import logging
import pytesseract

from PIL import Image
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pika.exceptions import NackError, UnroutableError

log = logging.getLogger(__name__)


@dataclass(order=True)
class TextBoundingBox:
    """Pillow-type Bound Box.
    Co-ordinates start in (0,0) in the Top Left Corner.
    """
    text: str
    left: int
    right: int
    top: int
    bottom: int


class ServiceBlockingConsumeAPublishB(ABC):
    """Object handling consume and publish of messages. Use it by implementing the
    process_message method in its subclass.
    """
    def __init__(self, host, queue_a, queue_b, routing_key_b, exchange_a="", exchange_b=""):
        """Setup connection, queues, and custom exchanges if used"""
        # TODO add support for other types of exchanges
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host))

        channel_a = self.connection.channel()
        if exchange_a:
            channel_a.exchange_declare(exchange=exchange_a)
        channel_a.queue_declare(queue=queue_a, durable=True)
        channel_a.confirm_delivery()
        channel_a.basic_qos(prefetch_count=1)

        channel_b = self.connection.channel()
        if exchange_b:
            channel_b.exchange_declare(exchange=exchange_b)
        channel_b.queue_declare(queue=queue_b, durable=True)
        channel_b.confirm_delivery()

        self.publish_exchange = exchange_b
        self.channel_consume = channel_a
        self.channel_publish = channel_b
        self.consume_queue = queue_a
        self.publish_routing_key = routing_key_b

    @abstractmethod
    def process_message(self, message: bytes) -> bytes:
        """Overwrite with the main service process consuming message and producing the output message"""
        raise NotImplementedError

    def run(self) -> None:
        """Start consuming, processing and publishing"""
        # prepare to clean up on interrupt and terminate signal
        signal.signal(signal.SIGINT, lambda sig, frame: self.channel_consume.cancel())
        signal.signal(signal.SIGTERM, lambda sig, frame: self.channel_consume.cancel())
        # main loop
        for method, properties, body in self.channel_consume.consume(queue=self.consume_queue):
            log.info(f'Consumed message: {properties.correlation_id}')
            message = self.process_message(body)
            confirmation = self.channel_consume.basic_ack
            try:
                self.channel_publish.basic_publish(
                    exchange=self.publish_exchange,
                    routing_key=self.publish_routing_key,
                    body=message,
                    properties=pika.BasicProperties(correlation_id=properties.correlation_id))
                log.info(f'Published message: {properties.correlation_id}')
            except NackError as e:
                log.warning(f'Published message was not acknowledged. Sending not acknowledge to '
                            f'consumer queue:{e}')
                confirmation = self.channel_consume.basic_nack
            except UnroutableError as e:
                log.warning(f'Published message was not routed. Sending not acknowledged to '
                            f'consumer queue:{e}')
                confirmation = self.channel_consume.basic_nack
            finally:
                confirmation(delivery_tag=method.delivery_tag)


def detect_text(image: bytes) -> list[TextBoundingBox]:
    """Load the image in tesseract ocr and extract its data in to TextBoundingBox objects"""
    trs_data = pytesseract.image_to_data(Image.open(io.BytesIO(image)))
    csv_reader = csv.reader(io.StringIO(trs_data), delimiter='\t')
    next(csv_reader)  # remove the header
    return [TextBoundingBox(text=x[11],
                            left=int(x[6]),
                            right=int(x[6]) + int(x[8]),  # left + width
                            top=int(x[7]),
                            bottom=int(x[7]) + int(x[9])  # top + height
                            ) for x in csv_reader if int(x[5]) > 0]  # skip non word data


class ServiceOCR(ServiceBlockingConsumeAPublishB):
    def process_message(self, message: bytes) -> bytes:
        """Pop the image from the message and replace it with the text recognised."""
        return json.dumps([asdict(x) for x in detect_text(message)]).encode()


if __name__ == '__main__':
    service = ServiceOCR(host=os.environ.get('RABBITMQ_HOST'),
                         queue_a='ocr_in',
                         queue_b='ocr_out',
                         routing_key_b='ocr_out')
    service.run()
