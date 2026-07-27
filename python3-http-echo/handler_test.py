from .handler import handle

# Enable with the build_arg TEST_ENABLED=true on the CLI or in stack.yaml
# https://docs.openfaas.com/reference/yaml/#function-build-args-build-args


class Event:
    def __init__(self, method="GET", path="/", body=b"", headers=None, query=None):
        self.method = method
        self.path = path
        self.body = body
        self.headers = headers or {}
        self.query = query or {}


class Context:
    hostname = "test-host"


def test_reflects_the_request():
    res = handle(Event(query={"a": "1"}), Context())

    assert res["statusCode"] == 200
    assert res["body"]["method"] == "GET"
    assert res["body"]["query"] == {"a": "1"}
    assert res["body"]["hostname"] == "test-host"
    assert "echo" not in res["body"]


def test_echoes_a_body():
    event = Event(method="POST", body=b"hello", headers={"Content-Type": "text/plain"})
    res = handle(event, Context())

    assert res["statusCode"] == 200
    assert res["body"]["echo"] == "hello"
    assert res["body"]["bytes"] == 5
    assert res["body"]["content_type"] == "text/plain"


def test_ready_reports_a_status():
    res = handle(Event(path="/ready"), Context())

    assert res["statusCode"] in (200, 503)
    assert res["body"]["status"] in ("ready", "initializing")
