"""A minimal local web UI for the B1 application, with the standard library only.

    python -m visualdoc.app serve            # then open http://127.0.0.1:8765

Design choices, all for a single user on their own machine:

- ``http.server`` and server-rendered HTML forms: no framework, no JavaScript, no new
  dependency. Every piece of user or model text goes through ``html.escape``.
- The server binds to 127.0.0.1 only. It also checks the ``Host`` header (a web page
  cannot reach it through a DNS name pointing at 127.0.0.1) and requires a per-server
  random token on every POST (another site cannot submit the form and spend money in
  live mode).
- Request bodies are bounded before they are read (uploads: the app's limit); the upload's
  token travels in the form's URL so it is checked before the body is read.
- One request at a time (``HTTPServer`` is single-threaded), which keeps the session's
  spend ledger simple. Each connection gets a short socket timeout, so an idle or stalled
  client cannot block the server for longer than that.

Routes: ``GET /``, ``POST /ask`` (form), ``POST /upload`` (multipart form),
``GET /page/<sha256>/<n>.png`` (page thumbnails), ``POST /api/ask`` (JSON, for scripts and tests).
"""

import hmac
import html
import json
import re
import secrets
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .answering import LUNA_PROFILE, NOT_ANSWERABLE
from .app import MAX_K, AppAnswer, B1App, CostRefused, Document, PoolDocumentRefused
from .visual_index import SF_DATALESS

MAX_FORM_BYTES = 64 * 1024
REQUEST_TIMEOUT_S = 15  # an idle connection holds the single-threaded server at most this long
TOKEN_HEADER = "X-VisualDoc-Token"
SECURITY_HEADERS = {
    # No script may run; images and form posts only from this server.
    "Content-Security-Policy": "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; "
                               "form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

STYLE = """
body{font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;background:#f6f7f9;color:#1c2024}
main{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:8px 0 12px} h2{font-size:16px;margin:0 0 8px}
section{background:#fff;border:1px solid #dde1e6;border-radius:8px;padding:14px 16px;margin:12px 0}
.banner{padding:12px 16px;font-weight:700;border-radius:8px;margin:12px 0}
.offline{background:#fff3cd;border:2px solid #b8860b;color:#5c4400}
.live{background:#fde2e1;border:2px solid #b3261e;color:#5f1410}
.error{background:#fde2e1;border:1px solid #b3261e;color:#5f1410}
.answer{font-size:20px;font-weight:600;margin:4px 0 10px}
.muted{color:#5b6470;font-size:13px}
.ok{color:#17663a;font-weight:600} .bad{color:#b3261e;font-weight:600}
.placeholder{opacity:.5;filter:grayscale(1)} .note{font-style:italic;color:#5b6470;font-size:13px}
textarea{width:100%;box-sizing:border-box;font:inherit;min-height:64px}
select,input,button{font:inherit} label{display:block;margin:6px 0 2px;font-weight:600}
.pages{display:flex;flex-wrap:wrap;gap:10px}
figure{margin:0;border:2px solid #dde1e6;border-radius:6px;padding:4px;background:#fff;text-align:center}
figure.cited{border-color:#17663a} figure img{width:150px;display:block}
figcaption{font-size:12px}
table{border-collapse:collapse;width:100%} td,th{border-top:1px solid #e6e9ed;padding:5px 6px;text-align:left;vertical-align:top}
code{font-size:12px;word-break:break-all}
"""


def e(value: Any) -> str:
    """HTML-escape any value (model and user text included), quotes too."""
    return html.escape(str(value), quote=True)


def _answer_text(answer: Any) -> str:
    if isinstance(answer, list):
        return "; ".join(str(item) for item in answer)
    return str(answer)


def parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:
    """{field: (filename or None, bytes)} from a multipart/form-data body (byte-exact for binary files)."""
    match = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not (content_type or "").startswith("multipart/form-data") or not match:
        raise ValueError("expected a multipart/form-data upload")
    fields = {}
    for part in body.split(b"--" + match.group(1).encode("latin-1"))[1:]:
        if part.startswith(b"--"):  # the closing delimiter
            break
        head, separator, content = part.partition(b"\r\n\r\n")
        if not separator:
            raise ValueError("malformed multipart part")
        headers = head.decode("latin-1")
        name = re.search(r'(?:^|[;\s])name="([^"]*)"', headers)
        filename = re.search(r'filename="([^"]*)"', headers)
        if name:
            fields[name.group(1)] = (filename.group(1) if filename else None, content.removesuffix(b"\r\n"))
    return fields


# --- HTML ------------------------------------------------------------------------------------------------


def render_banner(app: B1App) -> str:
    if app.live:
        return (f'<div class="banner live">LIVE: each new question calls {e("gpt-6-luna")} (paid). '
                f"Session spend (upper bound): ${app.spent_usd:.6f} of ${app.session_ceiling_usd:.2f}.</div>")
    return ('<div class="banner offline">OFFLINE PLACEHOLDER: no model is called. The answer, its citations and '
            "its quotes are placeholders, not results, and so are the checks computed on them. Retrieval and page "
            "selection run as in B1.</div>")


def render_result(answer: AppAnswer) -> str:
    r = answer.result
    reply, grounding, citations = r.reply, r.grounding, r.citations
    doc_id = answer.document.sha256
    # Offline, the checks below run on a placeholder reply: they are greyed out and labelled as such.
    dim = ' class="placeholder"' if answer.offline else ""
    note = ' <span class="note">(computed on a placeholder reply)</span>' if answer.offline else ""
    parts = ['<section><h2>Answer</h2>']
    if answer.offline:
        parts.append('<p class="bad">OFFLINE PLACEHOLDER: this is not a model answer.</p>')
    if reply.error:
        parts.append(f'<p class="answer bad">No valid answer: {e(reply.error)}</p>')
    elif reply.answer == NOT_ANSWERABLE:
        parts.append(f'<p class="answer">{e(NOT_ANSWERABLE)}</p><p class="muted">The reader found no answer on the supplied pages.</p>')
    else:
        parts.append(f'<p class="answer">{e(_answer_text(reply.answer))}</p>')
    parts.append(f'<p><span{dim}>Cited pages: <b>{e(", ".join(map(str, reply.cited_pages)) or "none")}</b> &middot; citation check: '
                 + ('<span class="ok">valid</span>' if citations.ok else
                    f'<span class="bad">invalid (not supplied: {e(list(citations.invalid))}, missing: {e(citations.missing)})</span>')
                 + f"</span>{note}</p>")
    if answer.identity_warning:
        parts.append(f'<p class="bad">Model identity: {e(answer.identity_warning)}</p>')
    parts.append("</section>")

    # Evidence quotes and the grounding trust signal.
    parts.append(f'<section><h2>Evidence quotes{note}</h2><div{dim}><table><tr><th>Page</th><th>Quote</th><th>On the cited page?</th></tr>')
    for (page, score), item in zip(grounding.quote_scores, reply.evidence):
        found = score >= grounding.threshold
        parts.append(f"<tr><td>{e(page)}</td><td>{e(item.quote)}</td><td>"
                     + ('<span class="ok">found</span>' if found else '<span class="bad">not found</span>')
                     + f' <span class="muted">(match {score:.2f})</span></td></tr>')
    if not reply.evidence:
        parts.append('<tr><td colspan="3" class="muted">No quotes.</td></tr>')
    parts.append("</table>")
    numeric = {True: '<span class="ok">yes</span>', False: '<span class="bad">no</span>', None: "not applicable"}[grounding.numeric_support]
    supported = '<span class="ok">yes</span>' if grounding.quotes_supported else '<span class="bad">no</span>'
    parts.append(f"<p>Quotes supported: {supported}"
                 f" &middot; answer numbers on cited pages: {numeric}</p></div>"
                 '<p class="muted">This check compares quotes with the page text. It is a trust signal for you, '
                 "not a correctness check (in E8 it did not predict correct answers).</p></section>")

    # Pages and retrieval.
    retriever = ("ColQwen2 visual retrieval (MaxSim)" if r.retriever == "visual" else "BM25 over page text (fallback)")
    parts.append(f'<section><h2>Pages read by the model</h2><p>Retriever: <b>{e(retriever)}</b></p>')
    if r.fallback_reason:
        parts.append(f'<p class="bad">Visual retrieval unavailable: {e(r.fallback_reason)}</p>')
    parts.append(f'<p class="muted">BM25 top {len(answer.bm25_pages)} (logged beside): {e(answer.bm25_pages)}'
                 + (f" &middot; dropped by the context guard: {e(r.dropped_pages)}" if r.dropped_pages else "") + "</p>")
    parts.append('<div class="pages">')
    for page in r.supplied_pages:
        cited = page in reply.cited_pages
        flags = (" &middot; cited" if cited else "") + (" &middot; OCR page" if page in answer.ocr_supplied_pages else "")
        src = f"/page/{doc_id}/{page}.png"
        parts.append(f'<figure class="{"cited" if cited else ""}"><a href="{e(src)}"><img src="{e(src)}" alt="page {page}" '
                     f'loading="lazy"></a><figcaption>p. {page}{flags}</figcaption></figure>')
    parts.append("</div>")
    if answer.ocr_supplied_pages:
        parts.append('<p class="muted">OCR pages are image-only pages: processed best effort.</p>')
    parts.append("</section>")

    # Cost.
    observed = f" &middot; observed ${answer.observed_usd:.6f}" if answer.observed_usd is not None else ""
    parts.append(
        f"<section><h2>Cost and trace</h2><p>Tokens (upper bound): {r.estimated_prompt_tokens:,} prompt + "
        f"{LUNA_PROFILE.max_output_tokens} output &middot; cost upper bound ${r.cost_upper_usd:.6f}"
        f"{' (not spent: offline)' if answer.offline else ''}{observed}"
        f"{' &middot; reply from cache' if r.cache_hit else ''}</p>"
        f"<p>Session: ${answer.session_spent_usd:.6f} of ${answer.session_ceiling_usd:.2f} charged.</p>"
        f'<p class="muted">Served model: {e(reply.served_model)} &middot; fingerprint: {e(reply.system_fingerprint)} '
        f"&middot; request <code>{e(r.request_fingerprint[:16])}</code></p></section>"
    )
    return "".join(parts)


def render_page(app: B1App, token: str, *, selected: str = "", question: str = "", k: int | None = None,
                result_html: str = "", error: str = "") -> str:
    options = []
    for name, path in app.library().items():
        placeholder = bool(getattr(path.stat(), "st_flags", 0) & SF_DATALESS)
        label = name + ("  (iCloud placeholder: downloaded on first use)" if placeholder else "")
        options.append((f"lib:{name}", label))
    library_paths = {path.resolve() for path in app.library().values()}
    uploads = (app.data_dir / "uploads").resolve()
    for document in app.documents.values():
        if document.path not in library_paths:
            uploaded = " (uploaded)" if document.path.parent == uploads else ""
            options.append((f"sha:{document.sha256}", document.name + uploaded))
    select = "".join(f'<option value="{e(value)}"{" selected" if value == selected else ""}>{e(label)}</option>'
                     for value, label in options)
    k = app.k if k is None else k
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>VisualDoc B1</title><style>{STYLE}</style></head><body><main>
<h1>VisualDoc B1 &middot; cited answers from PDF pages</h1>
{render_banner(app)}
{f'<section class="error">{e(error)}</section>' if error else ""}
<section><h2>Ask</h2>
<form method="post" action="/ask">
<input type="hidden" name="token" value="{e(token)}">
<label for="doc">Document</label><select id="doc" name="doc" required>{select}</select>
<label for="question">Question</label><textarea id="question" name="question" maxlength="2000" required>{e(question)}</textarea>
<label for="k">Pages read (k)</label><input id="k" name="k" type="number" min="1" max="{MAX_K}" value="{e(k)}">
<span class="muted">B1 reads 4.</span>
<p><button type="submit">Ask</button></p></form></section>
{result_html}
<section><h2>Add a PDF</h2>
<form method="post" action="/upload?token={e(token)}" enctype="multipart/form-data">
<input type="file" name="file" accept=".pdf,application/pdf" required> <button type="submit">Upload</button>
<span class="muted">up to {app.max_upload_bytes // (1024 * 1024)} MB and {app.max_pages} pages; stored locally under data/cache/app/uploads</span>
</form></section>
<p class="muted">B1: ColQwen2 page retrieval, top k pages, one gpt-6-luna call with strict JSON (answer, cited pages, quotes).
Without a visual index the app uses BM25 and says so.</p>
</main></body></html>"""


# --- HTTP ------------------------------------------------------------------------------------------------


class VisualDocServer(HTTPServer):
    """HTTPServer bound to 127.0.0.1, holding the app and the per-server form token."""

    def __init__(self, app: B1App, port: int = 0, *, verbose: bool = False, request_timeout: float = REQUEST_TIMEOUT_S):
        super().__init__(("127.0.0.1", port), Handler)
        self.app, self.verbose, self.request_timeout = app, verbose, request_timeout
        self.token = secrets.token_urlsafe(24)

    @property
    def port(self) -> int:
        return self.server_address[1]


class HTTPError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server: VisualDocServer

    def setup(self):
        self.timeout = self.server.request_timeout  # StreamRequestHandler applies it to the socket
        super().setup()

    def log_message(self, format, *args):  # request lines only (never bodies); silent unless verbose
        if self.server.verbose:
            super().log_message(format, *args)

    # --- plumbing ---

    def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in {**SECURITY_HEADERS, **(extra or {})}.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: int, text: str) -> None:
        self._send(status, text.encode("utf-8"), "text/html; charset=utf-8")

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload, default=str).encode("utf-8"), "application/json")

    def _check_host(self) -> None:
        allowed = {f"127.0.0.1:{self.server.port}", f"localhost:{self.server.port}"}
        if self.headers.get("Host") not in allowed:
            raise HTTPError(403, "unexpected Host header: this server answers only to 127.0.0.1")

    def _read_body(self, limit: int) -> bytes:
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit():
            raise HTTPError(411, "a Content-Length header is required")
        if int(length) > limit:
            self.close_connection = True  # the body is not read
            raise HTTPError(413, f"the request body has {int(length):,} bytes; the limit is {limit:,}")
        return self.rfile.read(int(length))

    def _check_token(self, value: str | None) -> None:
        # Compared as bytes: compare_digest refuses non-ASCII str, which would otherwise become a 500.
        if not value or not hmac.compare_digest(value.encode("utf-8", "replace"), self.server.token.encode()):
            raise HTTPError(403, "missing or invalid form token; reload the page")

    @staticmethod
    def _parse_k(value: Any, default: int) -> int:
        """k from a form (digits only) or JSON (an integer, not a bool or float); range checked by the app."""
        if value is None or value == "":
            return default
        if isinstance(value, str) and re.fullmatch(r"[0-9]{1,2}", value):
            return int(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise ValueError(f"k must be a whole number of pages, not {value!r}")

    def _document(self, ident: str) -> Document:
        app = self.server.app
        if ident.startswith("lib:"):
            path = app.library().get(ident[4:])
            if path is None:
                raise HTTPError(404, "unknown document")
            return app.open_document(path)
        if ident.startswith("sha:") and ident[4:] in app.documents:
            return app.documents[ident[4:]]
        raise HTTPError(404, "unknown document")

    def _error_status(self, error: Exception) -> int:
        if isinstance(error, HTTPError):
            return error.status
        if isinstance(error, PoolDocumentRefused):
            return 403
        return 400

    # --- routes ---

    def do_GET(self):
        try:
            self._check_host()
            url = urlsplit(self.path)
            if url.path == "/":
                selected = parse_qs(url.query).get("doc", [""])[0]
                return self._html(200, render_page(self.server.app, self.server.token, selected=selected))
            match = re.fullmatch(r"/page/([0-9a-f]{64})/(\d{1,4})\.png", url.path)
            if match:
                document = self.server.app.documents.get(match.group(1))
                page = int(match.group(2))
                if document is None or not 1 <= page <= document.page_count:
                    raise HTTPError(404, "unknown page")
                return self._send(200, self.server.app.page_png(document, page), "image/png",
                                  {"Cross-Origin-Resource-Policy": "same-origin"})
            raise HTTPError(404, "not found")
        except Exception as error:  # noqa: BLE001 - every failure becomes an HTTP answer
            self._fail(error, as_json=False)

    def do_POST(self):
        url = urlsplit(self.path)
        try:
            self._check_host()
            if url.path == "/api/ask":
                self._check_token(self.headers.get(TOKEN_HEADER))
                payload = json.loads(self._read_body(MAX_FORM_BYTES) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("expected a JSON object")
                k = self._parse_k(payload.get("k"), self.server.app.k)
                answer = self.server.app.ask(self._document(str(payload.get("doc", ""))), str(payload.get("question", "")), k=k)
                return self._json(200, answer.to_dict())
            if url.path == "/ask":
                form = parse_qs(self._read_body(MAX_FORM_BYTES).decode("utf-8"), keep_blank_values=True)
                field = lambda name: form.get(name, [""])[0]
                self._check_token(field("token"))
                selected, question = field("doc"), field("question")
                k = self._parse_k(field("k"), self.server.app.k)
                try:
                    answer = self.server.app.ask(self._document(selected), question, k=k)
                except (ValueError, RuntimeError, PermissionError, FileNotFoundError, HTTPError) as error:
                    page = render_page(self.server.app, self.server.token, selected=selected, question=question, k=k, error=str(error))
                    return self._html(self._error_status(error), page)
                page = render_page(self.server.app, self.server.token, selected=selected, question=question, k=k,
                                   result_html=render_result(answer))
                return self._html(200, page)
            if url.path == "/upload":
                self._check_token(parse_qs(url.query).get("token", [""])[0])  # before the body is read
                body = self._read_body(self.server.app.max_upload_bytes + MAX_FORM_BYTES)
                fields = parse_multipart(self.headers.get("Content-Type", ""), body)
                filename, data = fields.get("file", (None, b""))
                document = self.server.app.save_upload(data, filename or "upload.pdf")
                self.send_response(303)
                self.send_header("Location", f"/?doc=sha:{document.sha256}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            raise HTTPError(404, "not found")
        except Exception as error:  # noqa: BLE001 - every failure becomes an HTTP answer
            self._fail(error, as_json=url.path.startswith("/api/"))

    def _fail(self, error: Exception, *, as_json: bool) -> None:
        expected = (HTTPError, ValueError, RuntimeError, PermissionError, FileNotFoundError, CostRefused)
        if isinstance(error, expected):
            status, message = self._error_status(error), str(error)
        elif isinstance(error, (TimeoutError, ConnectionError)) or type(error).__module__.startswith("openai"):
            status = 502  # live mode: the request was sent, so its upper bound is already in the session spend
            message = f"the model API call failed ({type(error).__name__}: {error}); its upper bound was counted as spent"
        else:  # a bug: details go to the terminal, not to the page
            traceback.print_exc(file=sys.stderr)
            status, message = 500, "internal error (see the server terminal)"
        if as_json:
            return self._json(status, {"error": message, "error_type": type(error).__name__})
        return self._html(status, render_page(self.server.app, self.server.token, error=message))


def make_server(app: B1App, port: int = 0, *, verbose: bool = False,
                request_timeout: float = REQUEST_TIMEOUT_S) -> VisualDocServer:
    """A server on 127.0.0.1 (port 0: any free port). Call ``serve_forever()`` on it, e.g. in a thread."""
    return VisualDocServer(app, port, verbose=verbose, request_timeout=request_timeout)


def serve_forever(app: B1App, port: int = 8765) -> None:
    server = make_server(app, port, verbose=True)
    print(f"VisualDoc B1 on http://127.0.0.1:{server.port}  ({app.mode} mode; Ctrl-C to stop)", file=sys.stderr)
    if not app.live:
        print("OFFLINE PLACEHOLDER mode: no model is called; answers are placeholders.", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
