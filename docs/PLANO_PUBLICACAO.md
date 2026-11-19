# Plano de publicação 100% GRATUITO — Tactical Intelligence Lab no ar para a apresentação

19/11/2026 · Substitui o plano anterior (VPS paga). Meta: **custo zero** neste mês, link público para o professor na
próxima semana, **idêntico ao app** (o mesmo `app.py`, a mesma base inteira, sem perder dado nem funcionalidade).

---

## 0. Resumo de uma página

| tema | decisão | por quê |
|---|---|---|
| Onde roda | **no próprio PC do Matheus** (já tem a base inteira, 300 mil partidas) | é o único lugar grátis com disco e memória para a base completa |
| Como vira link público | **Cloudflare Quick Tunnel** (`cloudflared`) — sem conta, sem cartão, HTTPS automático | grátis, sem abrir porta no roteador, link `https://….trycloudflare.com` em ~10 s |
| Idêntico ao app? | **sim** — é o mesmo app, com os mesmos dados, só que acessível pela internet | nada a reescrever, nada a copiar |
| Quem entra | **senha de apresentação** pedida pelo script (fica só na memória da janela) | uso acadêmico com convidados = caminho de licença mais seguro (seção 6) |
| O que o visitante pode fazer | navegar, buscar, perguntar ao Assistente, abrir jogos, comparar, escalação, Scout, rankings | tudo de leitura e análise |
| O que o visitante NÃO pode | sincronizar fontes, treinar redes, recalcular rankings, refazer réguas | protege o PC e a base (aparece "🔒 desligada na versão de apresentação") |
| Atualização automática | **desligada só enquanto o link estiver no ar** (o script define `AUTO_SYNC=0` naquela janela) | o app fica leve para quem visita; o `.env` não é tocado |
| Reserva se algo falhar | vídeo de 3–5 min da demonstração gravado antes (Win + Alt + R, grátis no Windows) | internet ou PC podem falhar no dia; o vídeo não |
| Custo | **R$ 0,00** | nenhum serviço pago, nenhum cartão cadastrado |

**O que foi descartado e por quê (conferido hoje):**
- **Hugging Face Spaces**: desde 29/09/2026, contas grátis têm cota 0 de "CPU Basic" para apps Docker/Gradio — criar
  um Space para o nosso app pede plano pago (só páginas estáticas continuam grátis). Fonte: PR oficial
  huggingface/huggingface_hub#5037 (lançado na versão 2.1.0, 01/10/2026).
- **Streamlit Community Cloud**: grátis, mas com 1–2,7 GB de memória, dorme após ~12 h sem uso e só 1 app privado — a
  base inteira não cabe. Serve no futuro para uma "versão vitrine" reduzida (seção 7).
- **Oracle Cloud Always Free / Google Cloud**: exigem cartão de crédito no cadastro (risco de cobrança) — fora do
  "nem um centavo".
- **VPS (Hetzner etc.)**: paga.

---

## 1. Como funciona (desenho)

```
 Professor (celular/notebook)
        │  https://palavras-aleatorias.trycloudflare.com   ← link grátis, HTTPS
        ▼
 Cloudflare (rede deles, grátis)
        │  túnel criptografado que SAI do PC (não abre porta no roteador, não mexe no firewall)
        ▼
 PC do Matheus ── cloudflared ──► Streamlit (app.py, porta 8501) ──► database/tactical_lab.db (base inteira)
                                   │
                                   └─ porta de entrada (src/ui/gate.py): visitante → senha; PC (localhost) → direto
```

- O Matheus continua usando `http://localhost:8501` normalmente, **sem senha e com todos os botões**.
- Qualquer acesso que chega pelo túnel é "visitante" (o app reconhece os cabeçalhos da Cloudflare, mesmo que o
  endereço pareça local).
- O link existe **só enquanto a janela do script estiver aberta**; fechou, acabou. O endereço muda a cada vez.

---

## 2. Passo a passo — preparação (fazer 2–3 dias antes)

**Passo 1 — instalar o túnel grátis (uma vez só).**
```bash
winget install --id Cloudflare.cloudflared
```
Feche e abra o terminal depois (para o Windows achar o programa).

**Passo 2 — atualizar o código.**
```bash
git pull
```

**Passo 3 — deixar a base pronta e rápida (com o app FECHADO).**
```bash
python -m src.tools.criar_indices
```
```bash
python -m src.scout.evaluation
```
(Os rankings agora calculam em segundos; antes travavam na classificação de função.)

**Passo 4 — conferência automática.**
```bash
python -m src.tools.apresentacao
```
Mostra ✅/⚠️/❌ para: banco, índices, rankings, índice de busca, fotografia do Scout, régua dos confrontos, cloudflared,
porta livre, espaço em disco e versão do código. Resolva os ❌ (os ⚠️ funcionam, só ficam mais lentos).

**Passo 4.5 — Scout completo (Série B/C e sul-americanas).**
```bash
python -m src.scout.snapshot
```

**Passo 5 — ensaio geral (recomendado).**
```bash
.\scripts\apresentar.ps1
```
Digite uma senha de teste, abra o link no **celular com 4G** (fora do Wi-Fi de casa — é o teste real), entre com a
senha e percorra o roteiro da seção 4. Isso também "aquece" os caches em disco: no dia, as telas já abrem rápido.
Aperte Enter na janela do script para desligar.

Se o Windows recusar o script ("execução de scripts desabilitada"), rode uma vez só nesta janela:
```bash
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Passo 6 — gravar o vídeo de reserva.** Com o app aberto, `Win + Alt + R` (Xbox Game Bar, já vem no Windows) grava a
tela; `Win + Alt + R` de novo para parar. O vídeo vai para `Vídeos\Capturas`. 3–5 minutos seguindo o roteiro.

---

## 3. Passo a passo — no dia da apresentação

1. PC na tomada, de preferência **no cabo de rede**; feche downloads/jogos.
2. Configurações do Windows › Energia: **"Suspender: Nunca"** enquanto apresenta (PC dormindo derruba o link).
3. Feche o app se estiver aberto (o script avisa se a porta estiver ocupada).
4. Rode:
   ```bash
   .\scripts\apresentar.ps1
   ```
5. Digite a senha dos visitantes (não aparece na tela).
6. O script mostra o **LINK PÚBLICO** e já copia: cole no WhatsApp/e-mail do professor junto com a senha.
7. Deixe a janela aberta durante toda a apresentação. Ao terminar, **Enter** → desliga link e app.

Se precisar de outra porta: `.\scripts\apresentar.ps1 -Porta 8502`. Se quiser manter a atualização automática ligada
(não recomendado durante a apresentação): `-ComAtualizacao`.

---

## 4. Roteiro sugerido para mostrar ao professor (10–15 min)

1. **Busca** → um time brasileiro → página do clube (estilo, formações com padrões, histórico).
2. **Jogo com lances** (final da Copa 2022) → linha do tempo, xT, redes de passe, mapa de perigo da rede neural.
3. **Assistente** → "quem mais criou perigo?" / "como anular o principal criador?" (respostas com números conferidos,
   nada inventado; lacuna aparece como lacuna).
4. **Escalação** → Próximo jogo: provável dos dois times, confrontos FORÇAR/PROTEGER/EVITAR, índice fuzzy.
5. **Rankings** → avaliações separadas (desempenho, temporada, regularidade, contra fortes, revelação) e a ficha
   explicável de um jogador.
6. **Bastidores › A matéria aplicada** → fuzzy (Mamdani × Sugeno), redes neurais (forward pass, gradiente, curva),
   algoritmo genético (torneio, mutação, convergência) — cada questão com "Onde está no app".

---

## 5. Segurança e cuidados

- A senha **nunca** vai para o `.env`, arquivo, log ou tela: o script a guarda só na memória da janela e apaga ao sair.
  A comparação é por hash com `hmac.compare_digest`; 5 erros seguidos deixam cada nova tentativa mais lenta.
- O `.env` **não é aberto nem alterado**; o script só define variáveis daquela janela (`TIL_SENHA`, `AUTO_SYNC=0`), que
  o app respeita porque o `.env` não sobrescreve o que já está definido.
- Visitante não dispara ações pesadas nem gravações de manutenção (sincronizar, treinar, recalcular, refazer réguas,
  zerar medições, gravar catálogo).
- O túnel **sai** do PC: nenhuma porta é aberta no roteador e o firewall não precisa de exceção.
- Recarregar a página (F5) abre uma sessão nova do Streamlit → a senha é pedida de novo (normal). Navegar pelo app não
  pede de novo.
- Limites do túnel grátis (documentação da Cloudflare): até 200 pedidos simultâneos, sem garantia de disponibilidade,
  feito para testes/demonstrações — de sobra para uma turma, não para "produção".
- Desligue o link quando não estiver apresentando (o PC fica exposto só enquanto a janela está aberta, e só com senha).

---

## 6. Licenças — por que "convidados com senha" é o caminho certo agora

| fonte | situação |
|---|---|
| StatsBomb Open Data, Wyscout aberto, OpenPlay, openfootball, football-data.co.uk, Wikidata | abertos com crédito — já creditados |
| **FotMob** (JSON público) | "uso pessoal e não comercial" — mostrar a um professor numa apresentação acadêmica, com senha, é uso pessoal/acadêmico; publicar aberto para qualquer um, não |
| **ESPN** (feed público) | termos restritivos para reutilização pública — mesma lógica |
| Transfermarkt (dcaribou) | base derivada pública; valores são do Transfermarkt — citar a fonte |

Por isso o link tem senha e só vive durante a apresentação. Abrir para o público geral exigiria mostrar só métricas
derivadas (notas, rankings, análises) ou contratar dados — decisão para depois.

---

## 6.5 Velocidade no celular (rodada 19)

- **Modo congelado** (o script liga `TIL_CONGELADO=1`): dados parados, nenhuma busca na internet durante a
  apresentação e o cache vai para o DISCO sem expirar — tudo que for aberto no ENSAIO abre na hora no dia, mesmo depois
  de fechar e abrir o app (desde que nenhuma sincronização rode entre o ensaio e a apresentação).
- **Pré-aquecimento ao ligar**: catálogo, Scout, Rankings, índice de jogadores e os últimos 8 jogos / 6 times abertos
  são calculados em segundo plano, com uma tela de carregamento (campinho animado + passos). Resultado em
  `data/warmup_status.json` e em Bastidores › ⏱️ Velocidade.
- **Cobertura de carregamento** em qualquer troca de tela (só aparece se passar de 0,35 s).
- **Compressão da conexão** ligada (menos dados no 4G) e o visitante fica lembrado por 12 h no aparelho (a tela do
  celular apagar não pede a senha de novo).
- **Limite honesto:** análise NUNCA aberta antes (um time novo, um jogo novo) ainda leva o tempo do cálculo no PC
  (segundos). Por isso o ensaio importa: abra no PC, antes, exatamente o que vai mostrar.

## 6.6 "E sem o meu PC ligado, 24 h, de graça?"

Resposta honesta: **com a base inteira (11,4 GB) e tudo funcionando igual, não existe opção grátis sem cartão hoje.**
O que existe:

| opção | custo | como fica | o que você perde |
|---|---|---|---|
| **A. Versão vitrine no Streamlit Community Cloud** (recomendada para depois da apresentação) | R$ 0, sem cartão | link fixo 24 h; o PC publica uma "fotografia" reduzida da base (competições escolhidas, < 1 GB) quando você quiser | base menor; dorme após ~12 h sem visita (acorda em ~30–60 s); treino e edição continuam só no PC |
| B. Notebook velho / mini PC em casa como servidor | só a luz (~R$ 5–15/mês) | idêntico ao app, 24 h | exige uma máquina dedicada ligada |
| C. Oracle Cloud "Always Free" (4 núcleos, 24 GB, 200 GB) | R$ 0 se ficar no plano grátis | idêntico, 24 h | **pede cartão no cadastro** (risco de cobrança por engano) |

Você **continua editando, treinando a IA e atualizando tudo no PC** em qualquer opção: o PC é o "laboratório"; o link
público só mostra. Na opção A, depois de treinar/atualizar, um comando no PC publica a fotografia nova.

## 7. Depois deste mês (opcional, ainda grátis quando possível)

1. **Link fixo grátis com Tailscale Funnel** (conta grátis do plano Personal, uso não comercial): o endereço
   `https://<nome-do-pc>.<rede>.ts.net` não muda entre execuções. Exige instalar o Tailscale e liberar o "Funnel" na
   política da conta — conferir na documentação deles antes; a porta de entrada do app já trata esse acesso como visitante.
2. **Versão vitrine 24 h no Streamlit Community Cloud** (grátis): um "pacote de demonstração" com poucas competições
   (ex.: Copa 2022 com lances + Brasileirão atual com estatísticas), banco reduzido (< 1 GB) baixado na inicialização,
   `TIL_MODO_PUBLICO=1` (todos são visitantes, atualização desligada) e `TIL_SENHA` nos "Secrets" do Streamlit. Não é
   idêntico (base menor) e dorme sem uso — por isso não é o plano da apresentação.
3. **Servidor 24 h idêntico** (pago, só se um dia fizer sentido): o desenho da versão anterior deste documento — VPS com
   SQLite WAL + Litestream, worker como serviço, Caddy/Cloudflare — continua válido como referência.

---

## 8. O que já está pronto no código (rodada 18)

| peça | arquivo |
|---|---|
| Porta de entrada (senha para visitante, PC entra direto, cabeçalhos de túnel = visitante) | `src/ui/gate.py`, chamada em `app.py` |
| Botões pesados bloqueados para visitante | `neural.py`, `catalog.py`, `rankings.py` (`visitor_blocked`) |
| Modo público (todos visitantes, sem atualização automática) | `TIL_MODO_PUBLICO=1` (`gate.public_mode`, `autosync.enabled`) |
| Conferência antes de apresentar | `python -m src.tools.apresentacao` |
| Liga app + túnel, mostra e copia o link, desliga com Enter | `scripts/apresentar.ps1` |
| Rankings sem travar na base grande | `src/scout/evaluation.py` (`_strict_pct` + `_classify`) |
