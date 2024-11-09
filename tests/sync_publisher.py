import pika
import logging
from retry import retry
from pika.exceptions import NackError, UnroutableError
from pika.exchange_type import ExchangeType

LOG_FORMAT = ('%(levelname) -10s %(asctime)s %(name) -30s %(funcName) '
              '-35s %(lineno) -5d: %(message)s')
log = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT)


class RMQPublisher:
    def __init__(self, amqp_url, exchange="", exchange_type="direct"):
        self._url = amqp_url
        self.connection = None
        self.channel = None
        self.exchange = exchange
        self.exchange_type = ExchangeType(exchange_type)

    def connect(self):
        self.connection = pika.BlockingConnection(pika.URLParameters(self._url))
        self.channel = self.connection.channel()
        if self.exchange:
            self.channel.exchange_declare(exchange=self.exchange,
                                          exchange_type=self.exchange_type)
        self.channel.confirm_delivery()

    @retry(pika.exceptions.NackError, delay=5, jitter=(1, 3))
    def publish(self, routing_key: str, message: bytes, correlation_id=None):
        properties = pika.BasicProperties(correlation_id=correlation_id) if correlation_id else None
        self.channel.basic_publish(
            exchange=self.exchange,
            routing_key=routing_key,
            body=message,
            properties=properties)

    def publish_messages(self, queue: str, messages: list):
        self.connect()
        self.channel.queue_declare(queue=queue, durable=True)
        for uuid, message in messages:
            self.publish(routing_key=queue, message=message, correlation_id=uuid)
        self.channel.close()
        self.connection.close()
