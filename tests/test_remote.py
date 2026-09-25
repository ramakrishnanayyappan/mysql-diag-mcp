import unittest

from starlette.testclient import TestClient

from mysql_diag_mcp.remote import BearerTokenMiddleware, RequestLogMiddleware, parse_tokens


async def _dummy_app(scope, receive, send):
    identity = scope.get("state", {}).get("mcp_diag_identity", "-")
    body = f"identity={identity}".encode()
    await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"text/plain")]})
    await send({"type": "http.response.body", "body": body})


class ParseTokensTests(unittest.TestCase):
    def test_empty_string(self):
        self.assertEqual(parse_tokens(""), {})

    def test_labelled_tokens(self):
        self.assertEqual(parse_tokens("tok1:alice,tok2:bob"), {"tok1": "alice", "tok2": "bob"})

    def test_bare_tokens_get_generated_labels(self):
        self.assertEqual(parse_tokens("tok1,tok2"), {"tok1": "token-1", "tok2": "token-2"})

    def test_mixed_and_whitespace(self):
        self.assertEqual(parse_tokens(" tok1 : alice , tok2 "), {"tok1": "alice", "tok2": "token-2"})


class BearerTokenMiddlewareTests(unittest.TestCase):
    def setUp(self):
        app = BearerTokenMiddleware(_dummy_app, {"secret": "alice"})
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_missing_header_is_401(self):
        resp = self.client.get("/mcp")
        self.assertEqual(resp.status_code, 401)

    def test_wrong_token_is_401(self):
        resp = self.client.get("/mcp", headers={"Authorization": "Bearer nope"})
        self.assertEqual(resp.status_code, 401)

    def test_malformed_header_is_401(self):
        resp = self.client.get("/mcp", headers={"Authorization": "secret"})
        self.assertEqual(resp.status_code, 401)

    def test_correct_token_reaches_inner_app_with_identity(self):
        resp = self.client.get("/mcp", headers={"Authorization": "Bearer secret"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text, "identity=alice")


class RequestLogMiddlewareTests(unittest.TestCase):
    def test_passes_through_and_does_not_break_response(self):
        app = RequestLogMiddleware(_dummy_app)
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/mcp")
        self.assertEqual(resp.status_code, 200)


if __name__ == "__main__":
    unittest.main()
