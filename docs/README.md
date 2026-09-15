# Teste Técnico — Analista de Desenvolvimento de Sistemas

Solução completa para o teste técnico: cotações logísticas internacionais
(SQL, pipeline Python, cliente de API de câmbio e dashboard HTML).

## Estrutura do repositório

```
/sql/          query_1.sql, query_2.sql, query_3.sql
/python/       ingestao_cotacoes.py, currency_client.py, test_currency_client.py
/dashboard/    index.html, style.css, app.js, server.py
/docs/         README.md, JUSTIFICATIVA.md, resposta_desafio_integrador.txt
/Arquivos/     arquivos originais fornecidos no enunciado (não alterados)
cotacoes.db    banco de trabalho (cópia de Arquivos/cotacoes.db) usado pelo
               pipeline e pelo dashboard
```

## Pré-requisitos

- Python 3.10+
- pip

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Módulo 1 — SQL

As queries foram desenvolvidas e testadas contra `cotacoes.db` (SQLite):

```bash
sqlite3 cotacoes.db < sql/query_1.sql   # Ranking de vendedores
sqlite3 cotacoes.db < sql/query_2.sql   # Conversão de clientes
sqlite3 cotacoes.db < sql/query_3.sql   # Cria a view vw_cotacoes_normalizadas
sqlite3 cotacoes.db "SELECT * FROM vw_cotacoes_normalizadas LIMIT 10;"
```

> `query_2.sql` está correta e retorna vazio contra o dataset de exemplo: nenhum
> cliente no conjunto de 200 registros combina >= 10 cotações com < 20% de
> aprovação (o menor índice do dataset é ~22,7%, do cliente Samsung).

## Módulo 2 — Ingestão (Python)

`ingestao_cotacoes.py` monitora um diretório, identifica arquivos `.csv`/`.json`,
normaliza os dois formatos de fornecedor para o schema de `cotacoes` e insere de
forma idempotente (por `codigo`).

```bash
python python/ingestao_cotacoes.py --dir /caminho/para/arquivos --db cotacoes.db
```

Parâmetros:

- `--dir` (obrigatório): diretório com os arquivos `.csv`/`.json` a ingerir.
- `--db`: caminho do banco SQLite (default: `cotacoes.db` na raiz do repo).
- `--processados-dir`: destino dos arquivos processados (default: `<dir>/processados`).
- `--no-move`: não move os arquivos após o processamento.
- `--log-dir`: diretório dos logs rotativos (default: `python/logs`).

Diferenciais implementados: logging estruturado com rotação (5 MB, 3 backups),
movimentação de arquivos processados com timestamp, e uso exclusivo de
`argparse`/`pathlib` (sem caminhos absolutos fixos), agendável via cron ou
Task Scheduler sem alteração de código, por exemplo:

```
# cron (Linux/macOS) — todo dia às 06:00
0 6 * * * /caminho/.venv/bin/python /caminho/python/ingestao_cotacoes.py --dir /rede/cotacoes
```

## Módulo 3 — Cliente de API de câmbio

`currency_client.py` expõe `get_rate(moeda_origem: str) -> float`, consumindo
(de forma simulada, já que o endpoint do enunciado é fictício) uma API REST de
câmbio para BRL.

Diferenciais implementados:

- Retry exponencial (até 3 tentativas, backoff 1s/2s/4s) para timeout, erro de
  conexão e status 5xx; erros 4xx não são reprocessados.
- Cache local em SQLite (`python/rate_cache.db`) com janela de validade de 1 hora.
- Suíte de testes unitários (`pytest` + `responses`) cobrindo sucesso, cache
  válido/expirado, retry em erro 500, esgotamento de tentativas e erro 4xx.

```bash
pytest python/test_currency_client.py -v
```

## Módulo 4 — Dashboard

Backend Flask servindo os arquivos estáticos e três endpoints JSON
(`/api/summary`, `/api/cotacoes` e `/api/forecast`) que leem diretamente do SQLite.

```bash
python dashboard/server.py --db cotacoes.db --port 5000
# acesse http://127.0.0.1:5000
```

Funcionalidades: card de total de cotações; ranking Top 10 vendedores por
cotações aprovadas; volume mensal com alternância entre aprovadas/reprovadas/
estudo; distribuição percentual de status em rosca; volume por lane; filtros
por lane, vendedor e período; tabela paginada com os campos solicitados.
Ver decisões arquiteturais em `JUSTIFICATIVA.md`.

### Diferencial: projeção de demanda (não solicitado no enunciado)

Adicionei um gráfico extra ("Projeção de demanda — próximos meses") para ir
além do pedido e explorar o pilar de "raciocínio analítico" citado na
introdução do teste, mostrando como o dado histórico já coletado pode
embasar planejamento (ex.: dimensionamento de equipe/capacidade).

**Dado cruzado**: o endpoint `/api/forecast` agrupa a coluna `criacao` da
tabela `cotacoes` por dia (`COUNT(*) GROUP BY date(criacao)`), aplicando os
mesmos filtros de lane/vendedor/período já usados no resto do dashboard — ou
seja, é volume diário de cotações (todas, independente de status), não um
valor monetário.

**Método**: Suavização Exponencial Simples (SES, α = 0,3) sobre essa série
diária, projetada para os 3 meses seguintes ao último dia com dado. Descartei
regressão linear extrapolada: com ~10 dias de histórico e horizonte de 90
dias, a extrapolação de tendência diverge (testei e cheguei a projeções de
até 18x o volume real, um erro clássico de forecasting). SES é a recomendação
padrão para séries curtas sem tendência/sazonalidade estatisticamente
confirmável, e converge para uma estimativa estável.

**Limitações expostas na própria UI** (rodapé do gráfico): o mês "real"
reflete só os dias presentes no arquivo de exemplo (não o mês inteiro, o que
o torna não diretamente comparável aos meses projetados); com menos de 3
dias de histórico no filtro aplicado, o gráfico exibe um estado vazio em vez
de arriscar uma projeção sem base estatística.

## Módulo 5 — Desafio integrador

Resposta dissertativa em `docs/resposta_desafio_integrador.txt`.

## Observações gerais

- `cotacoes.db` na raiz é a cópia de trabalho de `Arquivos/cotacoes.db`; os
  arquivos originais do enunciado permanecem intactos em `/Arquivos`.
- Todos os scripts usam caminhos relativos ao próprio arquivo (via
  `pathlib(__file__)`), portanto funcionam a partir de qualquer diretório de
  execução, em Windows, Linux ou macOS.
