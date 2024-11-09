import pytest
from perform_ocr import run as dut


@pytest.mark.parametrize('img_path, ref', [
    ('tests/Screenshot1.png',
     ['Mimica', 'automates', 'repetitive', 'computer-based', 'tasks', 'through', 'human', 'observation.']),
])
def test_detect_text(img_path, ref):
    with open(img_path, 'rb') as fh:
        out = dut.detect_text(fh.read())
    assert set([x.text for x in out]) == set(ref)


class TestServiceOCR:
    def test_process_message(self, mocker):
        mocker.patch.object(dut, 'detect_text', return_value=[dut.TextBoundingBox('', 1, 2, 3, 4)])
        mocker.patch.object(dut, 'pika', mocker.MagicMock())
        socr = dut.ServiceOCR('host', 'a', 'b', 'b')
        out = socr.process_message(b'')
        assert isinstance(out, bytes)
        out_unpack = dut.json.loads(out.decode())
        assert isinstance(out_unpack, list)
        assert out_unpack[0] == dict(text='', left=1, right=2, top=3, bottom=4)
