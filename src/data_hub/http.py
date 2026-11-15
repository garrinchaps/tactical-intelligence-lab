"""
Cliente HTTP educado para todas as fontes externas.

* Cache em disco (data/raw/<fonte>/...) com validade configurável: nada é baixado duas vezes.
* Intervalo mínimo entre requisições por fonte (respeita limites por minuto).
* Repetição com espera exponencial em erros temporários (429, 5xx, rede); tempo-limite de 15 s.
* Transporte em src/data_hub/net.py (httpx se instalado, senão requests); erros e logs sem chaves.
* Controle de cota diária via DataHubDB (ex.: API-Football = 100/dia no plano grátis).
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from src.data_hub import net
from src.data_hub.db import DataHubDB


class QuotaExceeded(RuntimeError):
    """A cota diária configurada para a fonte acabou."""


class SourceUnavailable(RuntimeError):
    """A fonte não respondeu, não tem o recurso ou recusou a chave."""


class ClientRefused(SourceUnavailable):
    """A fonte recusou o pedido em si (HTTP 4xx, ex.: 400): repetir não adianta."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


NEGATIVE_CACHE_S = 7 * 24 * 3600      # recusa (4xx) lembrada por 7 dias: não insiste a cada execução


class PoliteHttpClient:
    _last_call: Dict[str, float] = {}

    def __init__(
        self,
        source: str,
        db: Optional[DataHubDB] = None,
        cache_dir: Path | str = "data/raw",
        min_interval_s: float = 1.0,
        daily_quota: Optional[int] = None,
        default_headers: Optional[Dict[str, str]] = None,
        timeout_s: float = net.DEFAULT_TIMEOUT,
        max_retries: int = 3,
    ) -> None:
        self.source = source
        self.db = db
        self.cache_dir = Path(cache_dir) / source
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval_s = min_interval_s
        self.daily_quota = daily_quota
        self.headers = {"User-Agent": "TacticalIntelligenceLab/1.0 (projeto academico)"}
        self.headers.update(default_headers or {})
        self.timeout_s = timeout_s
        self.max_retries = max_retries

    # ------------------------------------------------------------------ cache
    def _cache_path(self, url: str, params: Optional[Dict[str, Any]]) -> Path:
        key = url + "?" + json.dumps(params or {}, sort_keys=True)
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, path: Path, max_age_s: Optional[float]) -> Optional[Any]:
        if not path.exists():
            return None
        if max_age_s is not None and (time.time() - path.stat().st_mtime) > max_age_s:
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _neg_path(self, path: Path) -> Path:
        return path.with_suffix(".neg")

    def _negative(self, path: Path) -> Optional[int]:
        neg = self._neg_path(path)
        if not neg.exists() or (time.time() - neg.stat().st_mtime) > NEGATIVE_CACHE_S:
            return None
        try:
            return int(neg.read_text(encoding="utf-8").strip() or 400)
        except Exception:
            return 400

    # ---------------------------------------------------------------- request
    def quota_left(self) -> Optional[int]:
        if self.daily_quota is None or self.db is None:
            return None
        return max(self.daily_quota - self.db.api_usage_today(self.source), 0)

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        max_age_s: Optional[float] = None,
        use_cache: bool = True,
    ) -> Any:
        """
        `max_age_s=None` → cache permanente (dados históricos que não mudam).
        Use um valor (ex.: 6 h) para catálogos e jogos recentes.
        """
        path = self._cache_path(url, params)
        if use_cache:
            cached = self._read_cache(path, max_age_s)
            if cached is not None:
                return cached
            code = self._negative(path)
            if code is not None:
                raise ClientRefused(code, f"HTTP {code} em {self.source} (recusa já registrada; não repete por 7 dias)")

        left = self.quota_left()
        if left is not None and left <= 0:
            raise QuotaExceeded(
                f"Cota diária de {self.daily_quota} requisições da fonte '{self.source}' esgotada."
            )

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries):
            wait = self.min_interval_s - (time.time() - self._last_call.get(self.source, 0.0))
            if wait > 0:
                time.sleep(wait)
            try:
                resp = net.get(url, params=params, headers=self.headers, timeout=self.timeout_s, retries=1, source=self.source)
                PoliteHttpClient._last_call[self.source] = time.time()
                if self.db is not None and self.daily_quota is not None:
                    self.db.register_api_call(self.source)
                if resp.status_code == 404:
                    raise SourceUnavailable(f"Recurso não encontrado em {self.source}: {url}")
                if resp.status_code in (401, 403):
                    raise SourceUnavailable(
                        f"Acesso negado por {self.source} (HTTP {resp.status_code}). Verifique a chave/plano."
                    )
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise net.HTTPStatusError(resp.status_code, url)
                if 400 <= resp.status_code < 500:
                    # erro do pedido (ex.: 400 = intervalo/liga sem calendário): sem repetir, lembra a recusa
                    try:
                        self._neg_path(path).write_text(str(resp.status_code), encoding="utf-8")
                    except Exception:
                        pass
                    raise ClientRefused(resp.status_code, net.redact(f"HTTP {resp.status_code} em {url}"))
                resp.raise_for_status()
                data = resp.json()
                path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except SourceUnavailable:
                raise
            except (net.NetError, ValueError) as exc:
                last_err = exc
                if attempt < self.max_retries - 1:
                    delay = min(2 ** attempt, 30)
                    net.log(self.source, f"tentativa {attempt + 1} falhou ({exc}); nova em {delay}s")
                    time.sleep(delay)
        # rede falhou: usa cache vencido se existir
        stale = self._read_cache(path, None)
        if stale is not None:
            return stale
        raise SourceUnavailable(net.redact(f"Falha ao acessar {self.source}: {last_err}"))
