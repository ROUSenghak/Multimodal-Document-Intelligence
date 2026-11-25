"""End-to-end: the local web UI on an ephemeral port, offline (placeholder reader, no model call)."""

import hashlib
import http.client
import json
import re
import socket
import threading
import time
from urllib.parse import urlencode

import pymupdf
import pytest

from visualdoc.app import B1App, OfflineB1Reader
from visualdoc.web import TOKEN_HEADER, make_server, parse_multipart

HOSTILE = '<script>alert("q")</script> & <b>'


def make_pdf(path, first_page_text):
    document = pymupdf.open()
    for text in (first_page_text, "Employees work in seven countries. " * 8, "The board met four times this year. " * 8):
        document.new_page().insert_textbox((50, 50, 560, 740), text, fontsize=11)
    document.save(path)
    document.close()
    return path


@pytest.fixture
def served(tmp_path):
    """(server, app, document): a running server with one registered PDF whose text would inject HTML if unescaped."""
    app = B1App(data_dir=tmp_path / "data", max_upload_bytes=100_000)
    pdf = make_pdf(tmp_path / "report.pdf", "<img src=x onerror=alert(1)> Revenue grew to 495 million dollars. " * 6)
    document = app.open_document(pdf)
    server = make_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, app, document
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def request(server, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=30)
    connection.request(method, path, body=body, headers={"Host": f"127.0.0.1:{server.port}", **(headers or {})})
    response = connection.getresponse()
    data = response.read()
    connection.close()
    return response.status, dict(response.getheaders()), data


def form_post(server, path, fields):
    return request(server, "POST", path, urlencode(fields).encode(),
                   {"Content-Type": "application/x-www-form-urlencoded"})


def multipart(fields, boundary="----visualdoc-test-boundary"):
    parts = []
    for name, (filename, data) in fields.items():
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        parts.append(f"--{boundary}\r\nContent-Disposition: {disposition}\r\n\r\n".encode() + data + b"\r\n")
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def test_server_binds_to_loopback_and_shows_the_offline_banner(served):
    server, app, _ = served
    assert server.server_address[0] == "127.0.0.1"
    status, headers, body = request(server, "GET", "/")
    page = body.decode()
    assert status == 200 and "OFFLINE PLACEHOLDER" in page and server.token in page
    assert "are real" not in page and "computed on them" in page  # offline checks are not presented as results
    assert "script-src" not in headers["Content-Security-Policy"] and "default-src 'none'" in headers["Content-Security-Policy"]
    assert "<script" not in page  # the UI runs without JavaScript


def test_api_ask_returns_the_b1_result_as_json(served):
    server, _, document = served
    payload = json.dumps({"doc": f"sha:{document.sha256}", "question": "How much did revenue grow?", "k": 2}).encode()
    status, headers, body = request(server, "POST", "/api/ask", payload,
                                    {"Content-Type": "application/json", TOKEN_HEADER: server.token})
    answer = json.loads(body)
    assert status == 200 and headers["Content-Type"] == "application/json"
    assert answer["offline_placeholder"] is True and answer["result"]["reply"]["answer"] == OfflineB1Reader.ANSWER
    assert answer["result"]["retriever"] == "bm25" and "no visual index" in answer["result"]["fallback_reason"]
    assert answer["result"]["supplied_pages"][0] == 1 and len(answer["result"]["supplied_pages"]) == 2
    # Without the token the same request is refused, and nothing is asked.
    status, _, body = request(server, "POST", "/api/ask", payload, {"Content-Type": "application/json"})
    assert status == 403 and json.loads(body)["error_type"] == "HTTPError"


def test_form_ask_renders_the_answer_with_every_text_escaped(served):
    server, _, document = served
    status, _, body = form_post(server, "/ask", {"token": server.token, "doc": f"sha:{document.sha256}",
                                                 "question": HOSTILE + " revenue?", "k": "4"})
    page = body.decode()
    assert status == 200
    assert "OFFLINE PLACEHOLDER: this is not a model answer" in page
    assert page.count("(computed on a placeholder reply)") == 2  # citation and grounding verdicts, greyed out
    assert '<div class="placeholder"><table>' in page
    assert "&lt;script&gt;alert(&quot;q&quot;)&lt;/script&gt; &amp; &lt;b&gt;" in page  # the question, escaped
    assert "&lt;img src=x onerror=alert(1)&gt;" in page  # the quote copied from the PDF, escaped
    assert "<script>" not in page and "<img src=x" not in page
    assert "BM25 over page text (fallback)" in page and "no visual index for this PDF" in page
    thumbnails = re.findall(r'<img src="(/page/[0-9a-f]{64}/\d+\.png)"', page)
    assert len(thumbnails) == 3  # k = 4 on a 3-page PDF
    status, headers, png = request(server, "GET", thumbnails[0])
    assert status == 200 and headers["Content-Type"] == "image/png" and png.startswith(b"\x89PNG\r\n\x1a\n")
    assert headers["Cross-Origin-Resource-Policy"] == "same-origin"


def test_requests_from_other_hosts_without_token_or_too_large_are_refused(served):
    server, app, document = served
    status, _, _ = request(server, "GET", "/", headers={"Host": "attacker.example"})
    assert status == 403  # a DNS name pointing at 127.0.0.1 is not accepted
    fields = {"token": server.token, "doc": f"sha:{document.sha256}", "question": "Q?"}
    status, _, _ = request(server, "POST", "/ask", urlencode(fields).encode(),
                           {"Host": f"attacker.example:{server.port}", "Content-Type": "application/x-www-form-urlencoded"})
    assert status == 403  # the Host check covers POST too, even with a valid token
    status, _, body = form_post(server, "/ask", {**fields, "token": "wrong"})
    assert status == 403 and "form token" in body.decode()
    status, _, body = form_post(server, "/ask", {**fields, "token": "jeton-é-ü"})  # non-ASCII: refused, not a 500
    assert status == 403 and "form token" in body.decode()
    for bad_k in ("2.9", "true", "-1", "abc"):
        status, _, body = form_post(server, "/ask", {**fields, "k": bad_k})
        assert status == 400 and "k must be" in body.decode(), bad_k
    for bad_k in (True, 2.9, "2.9"):
        payload = json.dumps({"doc": f"sha:{document.sha256}", "question": "Q?", "k": bad_k}).encode()
        status, _, body = request(server, "POST", "/api/ask", payload, {TOKEN_HEADER: server.token})
        assert status == 400 and "k must be" in json.loads(body)["error"], bad_k
    status, _, _ = request(server, "GET", f"/page/{document.sha256}/99.png")
    assert status == 404
    status, _, _ = request(server, "GET", f"/page/{'0' * 64}/1.png")
    assert status == 404
    status, _, body = form_post(server, "/ask", {"token": server.token, "doc": "lib:../../etc/passwd", "question": "Q?"})
    assert status == 404 and "unknown document" in body.decode()
    # The upload's token (in its URL) and its declared size are checked before the body is read
    # (the bodies sent here are small on purpose).
    upload_headers = {"Content-Type": "multipart/form-data; boundary=x", "Content-Length": "200000"}
    status, _, _ = request(server, "POST", "/upload?token=wrong", b"x", upload_headers)
    assert status == 403
    status, _, _ = request(server, "POST", f"/upload?token={server.token}", b"x", upload_headers)
    assert status == 413
    assert not app.run_log_path.exists()  # none of these reached the pipeline


def test_cost_refusal_is_shown_and_nothing_is_called(tmp_path):
    calls = []
    app = B1App(data_dir=tmp_path / "data", live=True, create=lambda **request: calls.append(request),
                per_request_ceiling_usd=0.000001)
    document = app.open_document(make_pdf(tmp_path / "r.pdf", "Revenue grew to 495 million dollars. " * 6))
    server = make_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, _, body = form_post(server, "/ask", {"token": server.token, "doc": f"sha:{document.sha256}", "question": "Revenue?"})
        page = body.decode()
        assert status == 400 and "refused before any model call" in page and "LIVE" in page
        assert calls == []
    finally:
        server.shutdown()
        server.server_close()


def test_a_failed_model_call_is_reported_and_counted_as_spent(tmp_path):
    def timeout(**request):
        raise TimeoutError("no response from the API")

    app = B1App(data_dir=tmp_path / "data", live=True, create=timeout)  # mocked API: no network
    document = app.open_document(make_pdf(tmp_path / "r.pdf", "Revenue grew to 495 million dollars. " * 6))
    server = make_server(app, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"doc": f"sha:{document.sha256}", "question": "Revenue?"}).encode()
        status, _, body = request(server, "POST", "/api/ask", payload, {TOKEN_HEADER: server.token})
        assert status == 502 and json.loads(body)["error_type"] == "TimeoutError"
        assert 0 < app.spent_usd < 0.001
    finally:
        server.shutdown()
        server.server_close()


def test_upload_registers_the_pdf_and_rejects_non_pdfs(served, tmp_path):
    server, app, _ = served
    pdf = make_pdf(tmp_path / "upload.pdf", "Carbon emissions fell by ten percent. " * 6).read_bytes()
    body, content_type = multipart({"file": ('Q3 <report>.pdf', pdf)})
    status, headers, _ = request(server, "POST", f"/upload?token={server.token}", body, {"Content-Type": content_type})
    sha = hashlib.sha256(pdf).hexdigest()
    assert status == 303 and headers["Location"] == f"/?doc=sha:{sha}"
    assert app.documents[sha].name == "Q3 <report>.pdf"
    page = request(server, "GET", headers["Location"])[2].decode()
    assert f'<option value="sha:{sha}" selected>Q3 &lt;report&gt;.pdf (uploaded)</option>' in page

    body, content_type = multipart({"file": ("notes.pdf", b"plain text")})
    status, _, page = request(server, "POST", f"/upload?token={server.token}", body, {"Content-Type": content_type})
    assert status == 400 and "not a PDF" in page.decode()


def test_an_idle_connection_does_not_block_the_server(tmp_path):
    app = B1App(data_dir=tmp_path / "data")
    server = make_server(app, port=0, request_timeout=0.5)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    idle = socket.create_connection(("127.0.0.1", server.port))  # connects and never sends a byte
    try:
        started = time.monotonic()
        status, _, _ = request(server, "GET", "/")
        assert status == 200 and time.monotonic() - started < 5  # served once the idle connection timed out
    finally:
        idle.close()
        server.shutdown()
        server.server_close()


def test_multipart_parsing_is_byte_exact_for_binary_files():
    data = bytes(range(256)) * 4 + b"\r\n\r\n--almost-a-boundary\r\n" + b"\n\r\x00"
    body, content_type = multipart({"token": (None, b"abc"), "file": ("x.pdf", data)})
    fields = parse_multipart(content_type, body)
    assert fields["token"] == (None, b"abc") and fields["file"] == ("x.pdf", data)
    with pytest.raises(ValueError):
        parse_multipart("application/json", body)
