# Queues Challenge

## List of queues used and their content

| Queue    | Type   | Message                            | Property         |
|:---------|--------|:-----------------------------------|:-----------------|
| ocr_in   | direct | image bytes                        | correlation_id   |
| ocr_out  | direct | json list(asdict(TextBoundingBox)) | correlation_id   |
| pii      | fanout | json list(str)                     | correlation_id   |
| pii_out  | fanout | json list(asdict(TextBoundingBox)) | correlation_id   |

```
                                                                                     ┌──┬─────────────────┐               
                                                                                     ▼  │                 │               
                        ┌─────────────────┐                          ┌──────────────────┼─┐               │               
            ┌──────────►│      OCR        ├────────┐           ┌────►│     Filter       │ ├──────┐        │
            │           └─────────────────┘        │           │     └─▲────────────────┼─┘      │        │               
            │           ┌─────────────────┐        │           │       │                ▼        ├────────┴───────► 
            ├──────────►│    OCR          ├───────►│           │     ┌─┼──────────────────┐      │  pii_out(fanout)        
            │           └─────────────────┘        │           ├────►│ │   Filter         ├──────┘ 
  ocr_in    │          ┌──────────────────┐        │  ocr_out  │     └─┼─▲────────────────┘                               
 ───────────┴─────────►│     OCR          ├────────┴───────────┘       │ │                                                
                       └──────────────────┘                            │ │                                                
   pii(fanout)                                                         │ │                                                
 ──────────────────────────────────────────────────────────────────────┴─┘                                                
```
## Assumptions/Limitations:
* Queues oct_in and pii_in are written to in the same order and without delays.

## Future Work
* Type and test coverage
* Implement a statemachine and event store to relax the limitations

## Setup
```shell
sudo apt install tesseract-ocr libtesseract-dev
pip install -r requirementes.txt
```

## Run Tests
In the project root run:
```shell
pytest -s
``` 

## Run Manually
If you haven't yet run `pip install .[dev]`.
You will need 3 shells, one to run docker and two for consume and publish scripts.
Start the environment in shell 1:
```shell
cd tests
docker compose up
```
When RabbitMQ is ready for connections run the consumer script in shell 2:
```shell
python consume_from_mq.py
```
and the publish script in shell 3:
```shell
python publish_to_mq.py
```

