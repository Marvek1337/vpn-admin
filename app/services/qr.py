import base64
from io import BytesIO
import qrcode


def make_qr_data_uri(data: str) -> str:
    qr = qrcode.make(data)
    buf = BytesIO()
    qr.save(buf)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
