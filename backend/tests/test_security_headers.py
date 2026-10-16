from fastapi.responses import HTMLResponse

from app.main import app
from app.security_headers import CSP


def test_security_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert "content-security-policy" not in r.headers  # JSON: sin CSP

    @app.get("/__csp_probe", include_in_schema=False)
    def probe():
        return HTMLResponse("<p>x</p>")

    assert client.get("/__csp_probe").headers["content-security-policy"] == CSP
    assert "frame-ancestors 'none'" in CSP and "worker-src 'self' blob:" in CSP
