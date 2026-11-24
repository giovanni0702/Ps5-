"""Scansione G3: nessun indirizzo email, valore di secret, token Telegram o stringa lunga sospetta nel repository."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
TELEGRAM_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
LONG_RE = re.compile(r"\b[A-Za-z0-9]{32,}\b")
SECRET_NAMES = ["NTFY_TOPIC", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "SMTP_HOST", "SMTP_PORT",
                "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]
# NOME = "valore" / NOME: valore letterale (non riferimenti come ${{ secrets.NOME }} o os.environ)
ASSIGN_RE = re.compile(r"\b(" + "|".join(SECRET_NAMES) + r")\b\s*[:=]\s*['\"]?([^\s'\"$]{3,})")
ALLOWED_ASSIGN = re.compile(r"^(\$\{\{|os\.|env|None|\"\"|''|<|\.\.\.|\(|str|stringa)", re.I)
SKIP_SUFFIX = {".png", ".jpg", ".ico", ".pyc"}


def repo_files():
    try:
        out = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    except Exception:
        out = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [ROOT / f for f in out if Path(f).suffix not in SKIP_SUFFIX and (ROOT / f).is_file()]


def scan():
    problems = []
    for f in repo_files():
        if f.name == "test_segreti.py":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for rx, what in ((EMAIL_RE, "email"), (TELEGRAM_RE, "token telegram"), (LONG_RE, "stringa lunga")):
            for m in rx.finditer(text):
                problems.append(f"{f.relative_to(ROOT)}: {what} '{m.group(0)[:12]}…'")
        for m in ASSIGN_RE.finditer(text):
            if not ALLOWED_ASSIGN.match(m.group(2)):
                problems.append(f"{f.relative_to(ROOT)}: valore assegnato a {m.group(1)}")
    return problems


def test_nessun_segreto_nel_repository():
    assert scan() == []
