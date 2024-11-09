import os
import pika
import json
import time
import signal
import logging
from dataclasses import asdict, dataclass
from pika.exceptions import NackError, UnroutableError
from abc import ABC, abstractmethod

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


class ServiceBlockingConsumeABPublishC(ABC):
    """Object handling consume and publish of messages. Use it by implementing the
    process_message method in its subclass.
    """
    def __init__(self, host, buffer, queue_a,
                 exchange_b, exchange_c):
        """Setup connection, queues, and custom exchanges if used"""
        self.unresolved_buffer = buffer  # must be grater than the number of ocr replicas
        self.publish_exchange = exchange_c

        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host))

        channel_a = self.connection.channel()
        channel_a.queue_declare(queue=queue_a, durable=True)
        channel_a.basic_qos(prefetch_count=1)
        self.channel_consume_priority = channel_a
        self.consume_queue_priority = queue_a

        channel_b = self.connection.channel()
        if exchange_b:
            channel_b.exchange_declare(exchange=exchange_b, exchange_type='fanout')
        result = channel_b.queue_declare(queue="", durable=True, exclusive=True)
        self.consume_queue_match = result.method.queue
        channel_b.queue_bind(exchange=exchange_b, queue=self.consume_queue_match)
        self.channel_consume_match = channel_b

        channel_c_publish = self.connection.channel()
        if exchange_c:
            channel_c_publish.exchange_declare(exchange=exchange_c, exchange_type='fanout')
        channel_c_publish.queue_declare(queue="", durable=True)
        channel_c_publish.confirm_delivery()
        self.channel_publish = channel_c_publish

        channel_c_consume = self.connection.channel()
        if exchange_c:
            channel_c_consume.exchange_declare(exchange=exchange_c, exchange_type='fanout')
        result = channel_c_consume.queue_declare(queue="", durable=True, exclusive=True)
        self.consume_queue_match_resolved = result.method.queue
        channel_c_consume.queue_bind(exchange=exchange_c, queue=self.consume_queue_match_resolved)
        self.channel_c_consume = channel_c_consume

        self.unresolved_match_messages = {}  # pii messages we might need to correlate to ocr messages
        self.resolved_match_messages = set()  # pii messages processed by replicas

    @abstractmethod
    def process_message(self, message_a: bytes, message_b: bytes) -> bytes:
        """Overwrite with the main service process consuming message and producing the output message"""
        raise NotImplementedError

    def wait_queue_match_message(self):
        while True:
            queue_state = self.channel_consume_match.queue_declare(
                queue=self.consume_queue_match, durable=True, exclusive=True, passive=True)
            if queue_state.method.message_count > 0:
                return
            time.sleep(1)

    def get_message_with(self, correlation_id):
        """Read queue till the correlated message is found"""
        while len(self.unresolved_match_messages) < self.unresolved_buffer:
            if correlation_id in self.unresolved_match_messages:
                return self.unresolved_match_messages[correlation_id]
            self.wait_queue_match_message()
            method, properties, body = self.channel_consume_match.basic_get(self.consume_queue_match)
            log.info(f'Consumed match message: {properties.correlation_id}')
            if properties.correlation_id in self.resolved_match_messages:
                self.resolved_match_messages.remove(properties.correlation_id)
            else:
                self.unresolved_match_messages[properties.correlation_id] = body
            self.channel_consume_match.basic_ack(delivery_tag=method.delivery_tag)

        raise ResourceWarning(f'Figure out a better solution: {len(self.resolved_match_messages)=} '
                              f'{len(self.unresolved_match_messages)=}/{self.unresolved_buffer=}\n'
                              f'{self.unresolved_match_messages=}')

    def clean_unresolved(self):
        """Clean messages that were published to the channel c by all replicas.
        """
        while self.channel_c_consume.queue_declare(queue=self.consume_queue_match_resolved, durable=True,
                                                   exclusive=True, passive=True).method.message_count > 0:
            method, properties, body = self.channel_c_consume.basic_get(self.consume_queue_match_resolved)
            if properties.correlation_id in self.unresolved_match_messages:
                self.unresolved_match_messages.pop(properties.correlation_id)
            else:
                self.resolved_match_messages.add(properties.correlation_id)
            self.channel_c_consume.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        """Main loop consuming, processing and publishing"""
        signal.signal(signal.SIGINT, lambda sig, frame: self.channel_consume_priority.cancel())
        signal.signal(signal.SIGTERM, lambda sig, frame: self.channel_consume_priority.cancel())
        # main loop
        for method, properties, body in self.channel_consume_priority.consume(queue=self.consume_queue_priority):
            log.info(f'Consumed priority message: {properties.correlation_id}')
            message = self.process_message(message_a=body,
                                           message_b=self.get_message_with(properties.correlation_id))
            confirmation_priority = self.channel_consume_priority.basic_ack
            try:
                self.channel_publish.basic_publish(
                    exchange=self.publish_exchange,
                    routing_key="",
                    body=message,
                    properties=pika.BasicProperties(correlation_id=properties.correlation_id))
                log.info(f'Published message: {properties.correlation_id}')
            except NackError as e:
                log.warning(f'Published message was not acknowledged. Sending not acknowledge to '
                            f'consumer queue:{e}')
                confirmation_priority = self.channel_consume_priority.basic_nack
            except UnroutableError as e:
                log.warning(f'Published message was not routed. Sending not acknowledged to '
                            f'consumer queue:{e}')
                confirmation_priority = self.channel_consume_priority.basic_nack
            finally:
                confirmation_priority(delivery_tag=method.delivery_tag)
                self.clean_unresolved()


def filter_to_pii(bounding_boxes: list[TextBoundingBox], pii: list[str]) -> list[TextBoundingBox]:
    """Filter bounding boxes that contain pii"""
    return [x for x in bounding_boxes if x.text.lower() not in pii]


class ServiceFilter(ServiceBlockingConsumeABPublishC):
    """Process ocr_out messages"""
    def process_message(self, message_a: bytes, message_b: bytes) -> bytes:
        """Handle unpacking messages, call filter_to_pii, and return packed message"""
        boxes = [TextBoundingBox(**x) for x in json.loads(message_a.decode())]
        pii_texts = json.loads(message_b.decode())
        return json.dumps([asdict(x) for x in filter_to_pii(boxes, pii_texts)]).encode()


if __name__ == '__main__':
    service = ServiceFilter(host=os.environ.get('RABBITMQ_HOST'),
                            buffer=15,
                            queue_a='ocr_out',
                            exchange_b='pii',
                            exchange_c='pii_out')
    service.run()
