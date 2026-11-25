# Deploy Tactical Intelligence Lab na Oracle Cloud (Ubuntu + Docker)

Este guia instala o projeto em uma VM Oracle Cloud usando Docker Compose, mantendo SQLite e arquivos gerados em volumes persistentes. O deploy não inclui migração de banco local automaticamente.

## Arquitetura

- VM Ubuntu ARM64 (Ampere A1) dentro dos limites Always Free elegíveis.
- Docker Engine + Docker Compose.
- Streamlit exposto na porta 8501.
- Persistência local da VM para `database/`, `data/processed/`, `data/lake/` e `backups/`.
- Reinício automático do contêiner em reboot.

## 1. Criar a VM na Oracle Cloud

1. Crie uma conta Oracle Cloud e abra Compute > Instances > Create instance.
2. Escolha Ubuntu Server ARM64 (a imagem Ubuntu disponível mais recente).
3. Selecione VM.Standard.A1.Flex; para a configuração Always Free, mantenha o total da tenancy dentro dos limites elegíveis (até 2 OCPUs e 12 GB RAM).
4. Escolha boot volume suficiente para o código, dependências e dados. Recomendo 50 GB ou mais se houver disponibilidade gratuita na sua tenancy.
5. Configure uma chave SSH e salve a chave privada com segurança.
6. Na VCN/Security List ou Network Security Group da VM, adicione uma regra de entrada TCP 8501 (temporária para teste; restrinja a origem ao seu IP quando possível). Também permita TCP 22 apenas do seu IP.

**A Oracle exige disponibilidade de capacidade para provisionar Ampere A1; Always Free não garante que haverá capacidade no momento.** Confira limites e custos antes de criar recursos.

## 2. Conectar por SSH

No Windows PowerShell, usando a chave e o IP público da VM:

```powershell
ssh -i "C:\caminho\sua-chave.key" ubuntu@IP_PUBLICO
```

## 3. Verificar a instalação

O cloud-init já pode instalar Docker, clonar o repositório e iniciar o contêiner. Verifique:

```bash
sudo cloud-init status --wait
cd /opt/tactical-intelligence-lab
sudo docker compose ps
sudo docker compose logs --tail=100 -f
```

Se a instalação automática não ocorreu, execute:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable --now docker
git clone https://github.com/garrinchaps/tactical-intelligence-lab.git /opt/tactical-intelligence-lab
cd /opt/tactical-intelligence-lab
cp .env.example .env
sudo docker compose up -d --build
```

## 4. Configurar chaves (opcional)

Edite o arquivo .env na VM:

```bash
cd /opt/tactical-intelligence-lab
nano .env
```

Preencha apenas as chaves que você possui. Não compartilhe o arquivo e não faça commit dele.

- `GEMINI_API_KEY`: habilita o redator generativo Gemini.
- `API_FOOTBALL_KEY`: acesso ao provedor API-Football, sujeito à cota e ao plano.
- `FOOTBALL_DATA_TOKEN`: token do football-data.org.

A sincronização automática pode consumir cotas e recursos. Para começar com cautela, use `AUTO_SYNC=0`, valide o sistema e depois habilite. O sincronizador de fontes pesadas deve ser acionado manualmente.

Depois de alterar o .env:

```bash
sudo docker compose up -d
sudo docker compose logs --tail=100 -f
```

## 5. Acessar

No navegador:

```
http://IP_PUBLICO:8501
```

Se não abrir, confira a regra de ingresso TCP 8501 na VCN/NSG e também o firewall do Ubuntu (se estiver ativo).

## 6. Atualizar o código

```bash
cd /opt/tactical-intelligence-lab
git pull --ff-only
sudo docker compose up -d --build
```

## 7. Backup básico

Faça cópia antes de atualizar. O banco SQLite usa WAL; para backup consistente, use o comando SQLite `. backup` ou copie o banco com a aplicação parada.

Parar e copiar:

```bash
sudo docker compose stop
tar -czf backup-til-$(date +%Y%m%d-%H%M).tar.gz database data/processed data/lake
sudo docker compose start
```

Não deixe backups grandes indefinidamente no disco. Copie backups importantes para armazenamento externo.

## 8. Segurança e limites

- A configuração inicial publica Streamlit diretamente na porta 8501, sem autenticação. **Não use para dados privados nem compartilhe amplamente até configurar proxy HTTPS e autenticação.**
- Restrinja SSH e, se possível, 8501 por IP.
- Nunca commite .env, tokens, chaves SSH, banco de dados ou dados privados.
- A VM Always Free pode sofrer limitações de capacidade, performance e política de recuperação de instâncias inativas.
- O deploy remoto não copia seu banco SQLite do computador. Se quiser transferir seu histórico local, faça backup e migração separados após validar a instância.
- Modelos pequenos do projeto são empacotados no repositório; inferência generativa depende de chave de API e rede. O desempenho de modelos não é garantido na VM gratuita ARM.

## 9. Diagnóstico

```bash
sudo docker compose ps
sudo docker compose logs --tail=200
free -h
df -h
```

Para reiniciar:

```bash
sudo docker compose restart
```

Para desligar:

```bash
sudo docker compose down
```

Para iniciar:

```bash
sudo docker compose up -d
```
