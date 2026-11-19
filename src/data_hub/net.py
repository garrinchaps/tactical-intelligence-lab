"""
Camada única de rede do projeto.

* Usa **httpx** quando instalado (cliente reaproveitado, HTTP/1.1 keep-alive) e cai para **requests**
  (já presente) quando não estiver — nenhuma dependência nova obrigatória.
* Tempo-limite padrão de 15 s por operação (conectar / ler um bloco), não pelo download inteiro.
* Repetição com espera exponencial (1 s, 2 s, 4 s… teto 30 s) em erros de rede, 429 e 5xx; respeita Retry-After.
* Mensagens de erro e logs passam por `redact()`: chaves (inclusive as do Google), tokens, `Bearer …` e `?key=`
  nunca aparecem.
* `fetch_many()` baixa várias URLs com concorrência baixa e limitada (assíncrono com httpx; sequencial sem ele).
"""

from __future__ import annotations

import json as _json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

DEFAULT_TIMEOUT = 15.0
RETRY_STATUS = {429, 500, 502, 503, 504}
LOG_FILE = Path("data/sync_log.txt")
GOOGLE_KEY_PREFIX = "AI" "za"          # escrito separado de propósito: o literal não aparece no repositório
_SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|BILLING)", re.I)
_PATTERNS = [
    (re.compile(GOOGLE_KEY_PREFIX + r"[0-9A-Za-z_\-]{20,}"), "***"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "Bearer ***"),
    (re.compile(r"(?i)((?:api[_-]?key|apikey|key|token|access_token|x-apisports-key|x-rapidapi-key|x-auth-token)"
                r"[\"']?\s*[=:]\s*[\"']?)[^&\s\"',}]+"), r"\1***"),
]


def redact(text: Any) -> str:
    """Remove qualquer credencial conhecida de um texto (valores do ambiente + padrões comuns)."""
    s = str(text)
    for name, val in os.environ.items():
        if val and len(val) >= 6 and _SECRET_ENV.search(name) and val in s:
            s = s.replace(val, "***")
    for pat, rep in _PATTERNS:
        s = pat.sub(rep, s)
    return s


def log(source: str, message: str, path: Optional[Path] = None) -> None:
    """Linha de log sem segredos (data/sync_log.txt, fora do Git)."""
    path = path or LOG_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [{source}] {redact(message)}\n")
    except Exception:
        pass


class NetError(RuntimeError):
    """Falha de rede depois de todas as tentativas (mensagem já sem segredos)."""


class HTTPStatusError(NetError):
    def __init__(self, status_code: int, url: str):
        super().__init__(f"HTTP {status_code} em {redact(url)}")
        self.status_code = status_code


@dataclass
class Response:
    status_code: int
    content: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    url: str = ""

    @property
    def text(self) -> str:
        for enc in ("utf-8", "latin-1"):
            try:
                return self.content.decode(enc)
            except UnicodeDecodeError:
                continue
        return self.content.decode("utf-8", "replace")

    def json(self) -> Any:
        return _json.loads(self.content.decode("utf-8-sig"))

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise HTTPStatusError(self.status_code, self.url)


# ------------------------------------------------------------------ transporte
def _httpx():
    try:
        import httpx  # type: ignore

        return httpx
    except Exception:
        return None


_client = None


def backend() -> str:
    return "httpx" if _httpx() is not None else "requests"


def ascii_headers(headers: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """
    Cabeçalhos HTTP só aceitam ASCII (o httpx recusa "acadêmico" com "'ascii' codec can't encode"). Acentos viram a
    letra sem acento e o que sobrar fora do ASCII é removido — o valor continua legível e a requisição sai.
    """
    import unicodedata

    out: Dict[str, str] = {}
    for k, v in (headers or {}).items():
        txt = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode("ascii")
        out[str(k)] = txt
    return out


def _blocked(url: str) -> None:
    try:
        from src.data_hub.activity import network_blocked

        if network_blocked(url):
            raise NetError("modo congelado (apresentação): sem buscas na internet — usando só o que já está na base")
    except NetError:
        raise
    except Exception:
        pass


def _send(url: str, params, headers, timeout: float) -> Response:
    _blocked(url)
    headers = ascii_headers(headers)
    global _client
    hx = _httpx()
    if hx is not None:
        if _client is None:
            _client = hx.Client(follow_redirects=True, timeout=timeout)
        r = _client.get(url, params=params, headers=headers, timeout=timeout)
        return Response(r.status_code, r.content, dict(r.headers), str(r.url))
    import requests

    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    return Response(r.status_code, r.content, dict(r.headers), r.url)


def _network_errors() -> tuple:
    errs: List[type] = [OSError, TimeoutError]
    hx = _httpx()
    if hx is not None:
        errs.append(hx.HTTPError)
    try:
        import requests

        errs.append(requests.RequestException)
    except Exception:
        pass
    return tuple(errs)


def _unreachable(exc: Exception) -> bool:
    txt = f"{type(exc).__name__} {exc}".lower()
    return any(k in txt for k in ("connecterror", "connectionerror", "name or service", "getaddrinfo", "refused",
                                  "proxyerror", "nodename"))


def _retry_after(resp: Response) -> Optional[float]:
    v = (resp.headers or {}).get("Retry-After") or (resp.headers or {}).get("retry-after")
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def get(url: str, params: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT, retries: int = 3, backoff: float = 1.0, source: str = "rede",
        sleep=time.sleep) -> Response:
    """GET com repetição exponencial. 4xx (exceto 429) volta na hora; erros de rede viram NetError sem segredos."""
    last: Optional[str] = None
    resp: Optional[Response] = None
    for attempt in range(max(1, retries)):
        try:
            resp = _send(url, params, headers or {}, timeout)
            if resp.status_code not in RETRY_STATUS:
                return resp
            last = f"HTTP {resp.status_code}"
            wait = _retry_after(resp)
        except _network_errors() as exc:
            last, wait = f"{type(exc).__name__}: {exc}", None
            if attempt >= 1 and _unreachable(exc):
                break                     # sem rota / DNS / recusada: 2 tentativas bastam
        if attempt < retries - 1:
            delay = min(wait if wait is not None else backoff * (2 ** attempt), 30.0)
            log(source, f"tentativa {attempt + 1} falhou ({last}); nova em {delay:.0f}s")
            sleep(delay)
    if resp is not None:
        return resp                       # devolve o último 429/5xx para o chamador decidir
    raise NetError(redact(f"Falha de rede em {url}: {last}"))


def fetch_many(urls: Iterable[str], headers: Optional[Dict[str, str]] = None, max_concurrency: int = 2,
               timeout: float = DEFAULT_TIMEOUT, retries: int = 3) -> Dict[str, Any]:
    """Várias URLs com no máx. `max_concurrency` simultâneas. Devolve {url: Response | NetError}."""
    urls = list(dict.fromkeys(urls))
    hx = _httpx()
    out: Dict[str, Any] = {}
    if hx is None or max_concurrency <= 1 or len(urls) <= 1:
        for u in urls:
            try:
                out[u] = get(u, headers=headers, timeout=timeout, retries=retries)
            except NetError as exc:
                out[u] = exc
        return out
    import asyncio

    async def run():
        sem = asyncio.Semaphore(max_concurrency)
        async with hx.AsyncClient(follow_redirects=True, timeout=timeout) as cl:
            async def one(u):
                async with sem:
                    last = None
                    for attempt in range(retries):
                        try:
                            r = await cl.get(u, headers=ascii_headers(headers))
                            if r.status_code not in RETRY_STATUS or attempt == retries - 1:
                                return u, Response(r.status_code, r.content, dict(r.headers), str(r.url))
                            last = f"HTTP {r.status_code}"
                        except hx.HTTPError as exc:
                            last = f"{type(exc).__name__}: {exc}"
                        await asyncio.sleep(min(2 ** attempt, 30))
                    return u, NetError(redact(f"Falha de rede em {u}: {last}"))
            return await asyncio.gather(*(one(u) for u in urls))

    for u, r in asyncio.run(run()):
        out[u] = r
    return out


def download(url: str, dest, expected_size: Optional[int] = None, headers: Optional[Dict[str, str]] = None,
             timeout: float = 60.0, progress=None, source: str = "download", chunk: int = 1 << 20) -> "Path":
    """
    Baixa um arquivo grande direto para o disco (sem carregar na memória), em `dest.part` e renomeia no fim.
    Retoma do ponto onde parou (Range) se o servidor permitir; pula se o arquivo já existe com o tamanho esperado.
    """
    _blocked(url)
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and (expected_size is None or dest.stat().st_size == expected_size):
        return dest
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    hdr = ascii_headers(headers)
    if have:
        hdr["Range"] = f"bytes={have}-"
    say = progress or (lambda m: None)
    hx = _httpx()
    last_pct = -10
    try:
        if hx is not None:
            with hx.stream("GET", url, headers=hdr, timeout=timeout, follow_redirects=True) as r:
                if r.status_code == 200 and have:
                    have = 0                            # servidor ignorou o Range: recomeça
                if r.status_code >= 400:
                    raise HTTPStatusError(r.status_code, url)
                total = (int(r.headers.get("content-length", 0)) + have) or expected_size
                with open(part, "ab" if have else "wb") as f:
                    for b in r.iter_bytes(chunk):
                        f.write(b)
                        have += len(b)
                        if total:
                            pct = int(100 * have / total)
                            if pct >= last_pct + 10:
                                last_pct = pct
                                say(f"    {dest.name}: {pct}% de {total / 1e6:.0f} MB")
        else:
            import requests

            with requests.get(url, headers=hdr, timeout=timeout, stream=True) as r:
                if r.status_code == 200 and have:
                    have = 0
                if r.status_code >= 400:
                    raise HTTPStatusError(r.status_code, url)
                total = (int(r.headers.get("content-length", 0)) + have) or expected_size
                with open(part, "ab" if have else "wb") as f:
                    for b in r.iter_content(chunk):
                        f.write(b)
                        have += len(b)
                        if total:
                            pct = int(100 * have / total)
                            if pct >= last_pct + 10:
                                last_pct = pct
                                say(f"    {dest.name}: {pct}% de {total / 1e6:.0f} MB")
    except _network_errors() as exc:
        raise NetError(redact(f"Download interrompido ({dest.name}): {exc}. Rode de novo para continuar de onde parou."))
    if expected_size and part.stat().st_size != expected_size:
        raise NetError(f"Download incompleto de {dest.name} ({part.stat().st_size} de {expected_size} bytes). "
                       "Rode de novo para continuar.")
    part.replace(dest)
    return dest


def github_release_assets(repo: str, tag: Optional[str] = None, prefix: str = "") -> List[Dict[str, Any]]:
    """Arquivos de uma release do GitHub (API pública, sem conta). tag=None → a release mais nova com arquivos."""
    url = f"https://api.github.com/repos/{repo}/releases" + (f"/tags/{tag}" if tag else "")
    r = get(url, headers={"Accept": "application/vnd.github+json"}, source="github")
    r.raise_for_status()
    data = r.json()
    rels = [data] if isinstance(data, dict) else data
    for rel in rels:
        if prefix and not str(rel.get("tag_name", "")).startswith(prefix):
            continue
        assets = [{"name": a["name"], "url": a["browser_download_url"], "size": int(a.get("size") or 0)}
                  for a in rel.get("assets", [])]
        if assets:
            return [{**a, "tag": rel.get("tag_name")} for a in assets]
    return []
