import httpx
import pytest

from conftest import web_client
from llm_dashboard.agent.tools import MAX_FETCH_BYTES, MAX_FILE_BYTES, ToolBox, html_to_text


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    return root


def test_read_file_returns_text(workspace):
    (workspace / "a.txt").write_text("hello")
    assert ToolBox(workspace).run("read_file", {"path": "a.txt"}) == "hello"


def test_read_file_truncates_large_files(workspace):
    (workspace / "big.txt").write_text("x" * (MAX_FILE_BYTES + 10))
    out = ToolBox(workspace).run("read_file", {"path": "big.txt"})
    assert out.endswith("[truncated]") and len(out) < MAX_FILE_BYTES + 50


@pytest.mark.parametrize("path", ["../x", "/etc/passwd", "sub/../../x", "a\0b"])
def test_read_file_rejects_escapes(workspace, path):
    assert ToolBox(workspace).run("read_file", {"path": path}).startswith("error:")


def test_read_file_rejects_symlink_escape(workspace, tmp_path):
    (tmp_path / "outside.txt").write_text("secret")
    (workspace / "link.txt").symlink_to(tmp_path / "outside.txt")
    assert ToolBox(workspace).run("read_file", {"path": "link.txt"}) == (
        "error: path is outside the workspace"
    )


def test_read_file_rejects_binary_and_directories(workspace):
    (workspace / "bin").write_bytes(b"\x00\x01\x02")
    (workspace / "dir").mkdir()
    box = ToolBox(workspace)
    assert "binary" in box.run("read_file", {"path": "bin"})
    assert box.run("read_file", {"path": "dir"}) == "error: file not found"


@pytest.mark.parametrize("arguments", [{}, {"path": 3}, {"path": ""}, None])
def test_bad_arguments_and_unknown_tools_are_reported(workspace, arguments):
    box = ToolBox(workspace)
    assert box.run("read_file", arguments).startswith("error:")
    assert box.run("delete_everything", {}) == "error: unknown tool 'delete_everything'"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "file:///etc/passwd",
        "ftp://example.com/",
        "http://user:pw@example.com/",
        "not a url",
    ],
)
def test_fetch_blocks_unsafe_urls(workspace, url):
    def never(request):
        raise AssertionError("request must not be sent")

    assert ToolBox(workspace, web_client(never)).run("fetch_page", {"url": url}).startswith("error:")


def test_fetch_blocks_redirect_to_private_address(workspace, public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        raise AssertionError("private host must not be contacted")

    out = ToolBox(workspace, web_client(handler)).run("fetch_page", {"url": "https://example.com/"})
    assert out == "error: refusing to fetch a non-public address"


def test_fetch_follows_safe_redirects_but_not_forever(workspace, public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(301, headers={"location": "/end"})
        if request.url.path == "/end":
            return httpx.Response(200, text="done", headers={"content-type": "text/plain"})
        return httpx.Response(302, headers={"location": request.url.path + "x"})

    box = ToolBox(workspace, web_client(handler))
    assert box.run("fetch_page", {"url": "https://example.com/start"}) == "done"
    assert box.run("fetch_page", {"url": "https://example.com/loop"}) == "error: too many redirects"


def test_fetch_caps_body_and_rejects_binary(workspace, public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/big":
            return httpx.Response(200, content=b"a" * (MAX_FETCH_BYTES * 2),
                                  headers={"content-type": "text/plain"})
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    box = ToolBox(workspace, web_client(handler))
    assert len(box.run("fetch_page", {"url": "https://example.com/big"})) == MAX_FETCH_BYTES
    assert "unsupported content type" in box.run("fetch_page", {"url": "https://example.com/img"})


def test_fetch_reports_http_and_network_errors(workspace, public_dns):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/missing":
            return httpx.Response(404)
        raise httpx.ConnectError("boom")

    box = ToolBox(workspace, web_client(handler))
    assert box.run("fetch_page", {"url": "https://example.com/missing"}) == "error: HTTP 404"
    assert box.run("fetch_page", {"url": "https://example.com/x"}) == "error: request failed (ConnectError)"


def test_html_to_text_strips_markup_scripts_and_styles():
    html = "<style>p{}</style><h1>Title</h1><p>Some   <b>bold</b> text</p><script>x()</script>"
    assert html_to_text(html) == "Title Some bold text"
