import json
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters(host="127.0.0.1", port=5672))
channel = connection.channel()
channel.exchange_declare(exchange='pii_out', exchange_type='fanout')
queue_name = channel.queue_declare(queue="", durable=True, exclusive=True).method.queue
channel.queue_bind(exchange='pii_out', queue=queue_name)


def callback(ch, method, properties, body):
    print(f'Consumed {properties.correlation_id=} with message:')
    [print(x) for x in json.loads(body.decode())]


channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)


print('Starting consume loop')
try:
    channel.start_consuming()
except KeyboardInterrupt:
    pass
finally:
    channel.cancel()
    connection.close()
