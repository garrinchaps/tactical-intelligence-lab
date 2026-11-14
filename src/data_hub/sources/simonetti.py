"""
Simonetti Stats (simonettistats.com.br) — coletor para pesquisa local.

O site é uma aplicação JavaScript: as tabelas são montadas no navegador a partir de arquivos de dados
(JSON/xlsx/CSV). Por isso o coletor trabalha em duas etapas:

1. **Arquivos de dados (principal).** Lê a página inicial e os scripts dela, procura referências a arquivos de
   dados e baixa só esses arquivos — poucas requisições por dia, em vez de varrer o site inteiro. Se a descoberta
   automática não achar, informe os endereços em SIMONETTI_DATA_URLS no .env (copie da aba Rede/Network das
   ferramentas do desenvolvedor do navegador, filtrando por "json" ou "xlsx").
2. **Tabelas HTML (reserva).** Varredura em largura, limitada, das páginas internas, extraindo qualquer tabela HTML
   (útil se o site passar a renderizar no servidor). Linhas deduplicadas por hash.

Conduta de coleta: respeita o robots.txt, identifica-se com um User-Agent do projeto, 1 requisição por vez com
intervalo (padrão 3 s), limite de páginas por execução, para ao receber 403/429. Os dados ficam no lake local
(data/lake/sm_*) e NÃO são versionados no GitHub (data/ está no .gitignore).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import pandas as pd

DOMAIN = "simonettistats.com.br"
BASE = f"https://{DOMAIN}"
USER_AGENT = "TacticalIntelligenceLab/1.0 (pesquisa academica CEFET-MG; coleta 1x/dia)"
CACHE = Path("data/raw/simonetti")
DATA_EXT = (".json", ".xlsx", ".xls", ".csv", ".csv.gz")
DATA_URL_RX = re.compile(r"""["'`]((?:https?://[^"'`\s]+|/[^"'`\s]*|[\w\-./]+)\.(?:json|xlsx|xls|csv)(?:\.gz)?(?:\?[^"'`\s]*)?)["'`]""",
                         re.I)
SKIP_DATA = re.compile(r"manifest\.json|package\.json|tsconfig|locales?/|i18n|sourcemap|\.map$", re.I)
LICENSE = ("Simonetti Stats — dados de provedores não identificados pelo site; coleta para pesquisa local, "
           "não redistribuir")


class BlockedByServer(RuntimeError):
    pass


class _Page(HTMLParser):
    """Leitor de HTML da biblioteca padrão: scripts, links e tabelas (sem BeautifulSoup/lxml)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts: List[str] = []
        self.links: List[str] = []
        self.tables: List[List[List[str]]] = []
        self._depth = 0
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "table":
            self._depth += 1
            if self._depth == 1:
                self.tables.append([])
        elif tag == "tr" and self._depth == 1:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row and self.tables:
                self.tables[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._depth:
            self._depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def parse_page(html: str) -> _Page:
    p = _Page()
    try:
        p.feed(html)
    except Exception:
        pass
    return p


class SimonettiCollector:
    source = "simonetti"
    enabled = True

    def __init__(self, delay_s: float = 3.0, max_pages: int = 40, cache_dir: Path = CACHE,
                 fetch: Optional[Callable[[str], Tuple[int, bytes, str]]] = None):
        self.delay_s = float(os.getenv("SIMONETTI_DELAY_S", delay_s))
        self.max_pages = int(os.getenv("SIMONETTI_MAX_PAGES", max_pages))
        self.cache = Path(cache_dir)
        self._fetch = fetch or self._http
        self._last = 0.0
        self._robots: Optional[RobotFileParser] = None
        self.log: List[str] = []

    # ------------------------------------------------------------------ rede
    def _http(self, url: str) -> Tuple[int, bytes, str]:
        import requests

        r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"}, timeout=30)
        return r.status_code, r.content, r.headers.get("Content-Type", "")

    def get(self, url: str) -> Tuple[bytes, str]:
        if not self.allowed(url):
            raise PermissionError(f"robots.txt não permite {url}")
        wait = self.delay_s - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        status, body, ctype = self._fetch(url)
        self._last = time.time()
        if status in (403, 429):
            raise BlockedByServer(f"o servidor respondeu {status} em {url}; coleta interrompida")
        if status != 200:
            raise RuntimeError(f"HTTP {status} em {url}")
        return body, ctype

    def allowed(self, url: str) -> bool:
        if self._robots is None:
            rp = RobotFileParser()
            try:
                status, body, _ = self._fetch(f"{BASE}/robots.txt")
                rp.parse(body.decode("utf-8", "ignore").splitlines() if status == 200 else [])
            except Exception:
                rp.parse([])
            self._robots = rp
        return self._robots.can_fetch(USER_AGENT, url)

    @staticmethod
    def same_site(url: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host in (DOMAIN, f"www.{DOMAIN}")

    # ------------------------------------------------------ 1) arquivos de dados
    def discover_data_urls(self) -> List[str]:
        """Página inicial + scripts dela → endereços de arquivos de dados (mesmo site ou arquivos brutos do GitHub)."""
        env = [u.strip() for u in os.getenv("SIMONETTI_DATA_URLS", "").split(",") if u.strip()]
        if env:
            return env
        html, _ = self.get(BASE + "/")
        page = parse_page(html.decode("utf-8", "ignore"))
        texts = [html.decode("utf-8", "ignore")]
        for src_attr in page.scripts[:12]:
            src = urljoin(BASE + "/", src_attr)
            if self.same_site(src):
                try:
                    texts.append(self.get(src)[0].decode("utf-8", "ignore"))
                except Exception as exc:
                    self.log.append(f"script {src}: {exc}")
        found: List[str] = []
        for t in texts:
            for m in DATA_URL_RX.finditer(t):
                u = m.group(1)
                if SKIP_DATA.search(u):
                    continue
                full = u if u.startswith("http") else urljoin(BASE + "/", u)
                host = urlparse(full).netloc.lower()
                if self.same_site(full) or host in ("raw.githubusercontent.com",) or host.endswith(".github.io"):
                    found.append(full.split("#")[0])
        return list(dict.fromkeys(found))

    def parse_data_file(self, url: str, body: bytes) -> Dict[str, pd.DataFrame]:
        """JSON (lista de registros, ou dicionário de listas) / xlsx (uma tabela por aba) / CSV → DataFrames."""
        name = re.sub(r"[^a-z0-9]+", "_", Path(urlparse(url).path).stem.lower()).strip("_") or "dados"
        low = url.lower().split("?")[0]
        if low.endswith(".json"):
            data = json.loads(body.decode("utf-8-sig"))
            return {f"{name}_{k}" if k else name: v for k, v in self._json_tables(data).items()}
        if low.endswith((".xlsx", ".xls")):
            sheets = pd.read_excel(io.BytesIO(body), sheet_name=None)
            return {f"{name}_{re.sub(r'[^a-z0-9]+', '_', str(s).lower())}": d for s, d in sheets.items() if not d.empty}
        comp = "gzip" if low.endswith(".gz") else None
        return {name: pd.read_csv(io.BytesIO(body), compression=comp, sep=None, engine="python")}

    @staticmethod
    def _json_tables(data: Any, prefix: str = "") -> Dict[str, pd.DataFrame]:
        out: Dict[str, pd.DataFrame] = {}
        if isinstance(data, list) and data and all(isinstance(x, dict) for x in data[:50]):
            out[prefix] = pd.json_normalize(data, sep="_")
        elif isinstance(data, dict):
            if data and all(isinstance(v, dict) for v in list(data.values())[:50]) and len(data) > 5:
                out[prefix] = pd.json_normalize([{"chave": k, **v} for k, v in data.items()], sep="_")
            else:
                for k, v in data.items():
                    out.update(SimonettiCollector._json_tables(v, f"{prefix}_{k}".strip("_")))
        return out

    # ------------------------------------------------------- 2) tabelas HTML
    def crawl_html_tables(self) -> pd.DataFrame:
        queue, seen, rows = deque([BASE + "/"]), set(), []
        while queue and len(seen) < self.max_pages:
            url = queue.popleft()
            if url in seen or not self.same_site(url):
                continue
            seen.add(url)
            try:
                body, ctype = self.get(url)
            except BlockedByServer:
                raise
            except Exception as exc:
                self.log.append(f"{url}: {exc}")
                continue
            if "html" not in ctype and not body.lstrip()[:1] == b"<":
                continue
            html = body.decode("utf-8", "ignore")
            tables = self._html_tables(html)
            for i, t in enumerate(tables):
                t.columns = [re.sub(r"\s+", "_", str(c).strip().lower()) for c in t.columns]
                for rec in t.to_dict("records"):
                    payload = json.dumps(rec, ensure_ascii=False, default=str)
                    rows.append({"row_hash": hashlib.sha256(f"{url}|{i}|{payload}".encode()).hexdigest(),
                                 "source_url": url, "table_index": i, "payload_json": payload})
            for href in parse_page(html).links:
                nxt = urljoin(url, href).split("#")[0]
                if self.same_site(nxt) and nxt not in seen and not re.search(r"\.(png|jpe?g|svg|pdf|zip)$", nxt, re.I):
                    queue.append(nxt)
        self.log.append(f"varredura HTML: {len(seen)} páginas, {len(rows)} linhas de tabela")
        return pd.DataFrame(rows)

    @staticmethod
    def _html_tables(html: str) -> List[pd.DataFrame]:
        """Tabelas HTML → DataFrames, só com a biblioteca padrão (1ª linha = cabeçalho)."""
        if "<table" not in html.lower():
            return []
        out = []
        for rows in parse_page(html).tables:
            if len(rows) >= 2:
                head = [h or f"col_{i}" for i, h in enumerate(rows[0])]
                body = [(r + [""] * len(head))[:len(head)] for r in rows[1:]]
                out.append(pd.DataFrame(body, columns=head))
        return out

    # ------------------------------------------------------------------ sync
    def sync(self, lake, progress: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
        say = progress or (lambda m: None)
        prov = dict(source="Simonetti Stats", connector="SimonettiCollector", license=LICENSE)
        out = {"arquivos": 0, "tabelas": 0, "linhas": 0, "linhas_html": 0}
        try:
            urls = self.discover_data_urls()
        except BlockedByServer:
            raise
        except Exception as exc:
            urls = []
            say(f"  simonetti: descoberta de arquivos falhou ({exc})")
        say(f"  simonetti: {len(urls)} arquivo(s) de dados encontrados")
        for u in urls:
            try:
                body, _ = self.get(u)
                self.cache.mkdir(parents=True, exist_ok=True)
                (self.cache / re.sub(r"[^A-Za-z0-9_.]+", "_", urlparse(u).path.strip("/"))).write_bytes(body)
                for name, df in self.parse_data_file(u, body).items():
                    df = df.copy()
                    df["arquivo_origem"] = u
                    lake.write(f"sm_{name}"[:60], df, **prov)
                    out["tabelas"] += 1
                    out["linhas"] += len(df)
                    say(f"  simonetti: {name} ({len(df)} linhas)")
                out["arquivos"] += 1
            except BlockedByServer:
                raise
            except Exception as exc:
                say(f"  simonetti: {u}: {exc}")
        if out["arquivos"] == 0:                              # reserva: tabelas HTML
            html_rows = self.crawl_html_tables()
            if not html_rows.empty:
                lake.upsert("sm_tabelas_html", html_rows, ["row_hash"], **prov)
                out["linhas_html"] = len(html_rows)
            say("  simonetti: nenhum arquivo de dados; " + self.log[-1] +
                ". Se ficar vazio, informe SIMONETTI_DATA_URLS no .env (veja docs/SIMONETTI.md).")
        out["updated"] = out["linhas"] + out["linhas_html"]
        return out


def player_team_columns(df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
    """Descobre as colunas de atleta e de clube numa tabela do Simonetti (nomes variam por arquivo)."""
    cols = {c.lower(): c for c in df.columns}
    p = next((cols[c] for c in cols if re.fullmatch(r"(jogador|atleta|nome|player|name|player_name)", c)), None)
    t = next((cols[c] for c in cols if re.fullmatch(r"(time|clube|equipe|team|club|squad)", c)), None)
    return p, t
