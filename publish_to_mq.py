import json

from uuid import uuid4
from pathlib import Path
from tests.sync_publisher import RMQPublisher


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

ampq = "amqp://guest:guest@127.0.0.1:5672/%2F?connection_attempts=3&heartbeat=3600"
ocr_publisher = RMQPublisher(ampq)
pii_publisher = RMQPublisher(ampq, exchange='pii', exchange_type='fanout')

ocr_in_messages: list[tuple] = []
pii_in_messages: list[tuple] = []
reference = {}
for ppi_list, image_file, ref_list in data:
    path = 'tests' / Path(image_file)
    assert path.is_file(), f'{Path.cwd()}'
    with open(path, "rb") as f:
        img_data = f.read()
        uuid = str(uuid4())
        ocr_in_messages.append((uuid, img_data))
        pii_in_messages.append((uuid, json.dumps(ppi_list)))
        reference[uuid] = ref_list
print('Test data ready to publish')
# publish messages
pii_publisher.publish_messages(queue="", messages=pii_in_messages)
print('Done publishing to pii_in')
ocr_publisher.publish_messages(queue="ocr_in", messages=ocr_in_messages)
print('Done publishing to ocr_in')
