import os
import time
import pika


def delayed_nack(ch, method, properties, body):
    time.sleep(5)
    ch.basic_nack(delivery_tag=method.delivery_tag)


def main() -> None:
    connection = pika.BlockingConnection(pika.ConnectionParameters(host=os.environ.get('RABBITMQ_HOST')))
    channel = connection.channel()
    channel.confirm_delivery()

    channel.queue_declare(queue='ocr_in', durable=True)
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='ocr_in', auto_ack=False,
                          on_message_callback=delayed_nack)
    channel.start_consuming()


if __name__ == '__main__':
    main()
