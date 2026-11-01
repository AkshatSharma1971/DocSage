"""DocSage look & feel: dark violet theme, logo and brand header. No Streamlit import."""
import base64
from pathlib import Path

LOGO_FILE = Path(__file__).resolve().parent.parent / "assets" / "logo.png"

CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@400;500&display=swap');
:root{--bg:#0a0a10;--card:#11111a;--line:#27203f;--ink:#f4f4f8;--mute:#9a98ad;--pur:#8b5cf6;--pur2:#a78bfa}
.stApp{font-family:'Inter',system-ui,sans-serif;background:radial-gradient(1100px 520px at 90% -10%,rgba(139,92,246,.20),transparent),radial-gradient(800px 400px at -5% 110%,rgba(109,40,217,.12),transparent),var(--bg)}
header[data-testid="stHeader"]{background:transparent}
section[data-testid="stSidebar"]{background:#0d0d15;border-right:1px solid var(--line)}
.block-container{padding-top:2.2rem;max-width:1180px}
.brand{display:flex;align-items:center;gap:22px;border-left:2px solid var(--pur);padding-left:22px;margin:0 0 28px}
.brand img.logo{height:96px;width:auto;filter:drop-shadow(0 0 22px rgba(139,92,246,.45))}
.brand .word{font-size:3rem;font-weight:800;letter-spacing:.22em;line-height:1;background:linear-gradient(90deg,#a78bfa,#6d28d9);-webkit-background-clip:text;background-clip:text;color:transparent}
[data-testid="stMetric"]{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 18px}
[data-testid="stMetricLabel"] p{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.72rem;letter-spacing:.12em;text-transform:uppercase;color:var(--mute)}
[data-testid="stMetricValue"]{font-weight:800}
[data-testid="stExpander"]{background:var(--card);border:1px solid var(--line)!important;border-radius:14px}
[data-testid="stExpander"] summary:hover{color:var(--pur2)}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:12px;overflow:hidden}
.stButton>button[kind="primary"]{background:linear-gradient(90deg,#8b5cf6,#6d28d9);border:0;color:#fff;font-weight:600;border-radius:10px}
.stButton>button[kind="primary"]:hover{filter:brightness(1.12);box-shadow:0 0 18px rgba(139,92,246,.45)}
[data-testid="stAlert"]{border-radius:12px;border:1px solid var(--line)}
code{color:var(--pur2)!important}
@media (max-width:760px){.brand .word{font-size:1.8rem}.brand img.logo{height:64px}}
</style>"""

# Built-in logo: document + AI chip + circuit lines + folder, violet gradient.
LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 130">'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#c4b5fd"/><stop offset="1" stop-color="#6d28d9"/></linearGradient></defs>'
    '<rect x="14" y="6" width="62" height="98" rx="7" fill="none" stroke="url(#g)" stroke-width="3"/>'
    '<circle cx="45" cy="22" r="7" fill="none" stroke="url(#g)" stroke-width="2.5"/>'
    '<circle cx="45" cy="22" r="2.4" fill="#a78bfa"/>'
    '<g stroke="url(#g)" stroke-width="2" fill="none" stroke-linecap="round">'
    '<path d="M45 29v15M45 70v13M32 50H20M32 57H22M32 64H20M58 50h12M58 57h10M58 64h12"/></g>'
    '<g fill="#a78bfa"><circle cx="20" cy="50" r="2"/><circle cx="22" cy="57" r="2"/><circle cx="20" cy="64" r="2"/>'
    '<circle cx="70" cy="50" r="2"/><circle cx="68" cy="57" r="2"/><circle cx="70" cy="64" r="2"/>'
    '<circle cx="45" cy="83" r="2"/></g>'
    '<rect x="32" y="44" width="26" height="26" rx="4" fill="#181326" stroke="url(#g)" stroke-width="2.5"/>'
    '<text x="45" y="62" text-anchor="middle" font-family="monospace" font-weight="bold" font-size="13" fill="#c4b5fd">AI</text>'
    '<text x="58" y="97" text-anchor="middle" font-family="monospace" font-size="9" fill="#a78bfa">&lt;/&gt;</text>'
    '<path d="M8 106h28l6 8h50v16H8z" fill="url(#g)" opacity=".9"/></svg>'
)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def header() -> str:
    """Logo + DOCSAGE. If assets/logo.png exists it replaces the built-in logo and wordmark."""
    if LOGO_FILE.exists():
        return (f"<div class='brand'><img class='logo' style='height:110px' "
                f"src='data:image/png;base64,{_b64(LOGO_FILE.read_bytes())}'/></div>")
    return (f"<div class='brand'><img class='logo' src='data:image/svg+xml;base64,{_b64(LOGO_SVG.encode())}'/>"
            "<div class='word'>DOCSAGE</div></div>")
