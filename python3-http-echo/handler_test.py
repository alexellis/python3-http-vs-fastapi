from .handler import handle


class Event:
    def __init__(self, method="GET", body=b""):
        self.method = method
        self.body = body


class Context:
    pass


def test_get_returns_a_greeting():
    res = handle(Event(), Context())
    assert res["statusCode"] == 200
    assert res["body"]["message"] == "Hello from python3-http"


def test_post_echoes_the_body():
    res = handle(Event(method="POST", body=b"hello"), Context())
    assert res["statusCode"] == 200
    assert res["body"]["echo"] == "hello"
