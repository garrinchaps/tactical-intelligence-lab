# Testes e paridade

## Comandos reproduzíveis

```powershell
$env:PYTHONPATH = "src"
.\venv\Scripts\python.exe -m pytest -q .\tests
```

O escopo explícito evita a colisão histórica com a cópia aninhada `tactical-intelligence-lab/tests`.

## Baseline da auditoria

Em 2026-11-17: 342 testes coletados; 339 passaram, 2 falharam e 1 foi ignorado. As falhas foram reproduzidas, corrigidas e devem ser revalidadas na suíte completa.

## Paridade exigida

- Contagens e chaves de tabelas exportadas.
- Profundidade de partidas: todas, eventos, estatísticas e apenas placar.
- Ratings, força de adversário, planner e relatórios.
- Proveniência e guardrail numérico.
- Respostas para dados ausentes sem invenção.
- Contratos HTTP e permissões.

Resultados conhecidos devem ser snapshots/fixtures versionados. Diferenças deliberadas precisam de justificativa neste documento e no status.
