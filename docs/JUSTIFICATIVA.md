# Justificativa Técnica — Dashboard

Mantive o SQLite como fonte direta do dashboard (sem camada intermediária de cache/ETL): o volume atual (centenas de registros) não justifica complexidade adicional, e o schema relacional já atende bem às agregações por vendedor, status, mês e lane exigidas pelos gráficos.

Utilizei `/api/summary` para cards/gráficos e `/api/cotacoes` para a tabela paginada em vez de um único endpoint: a tabela pagina e os gráficos não, então unificá-los forçaria reprocessar as agregações a cada troca de página.

A agregação `GROUP BY`, `COUNT`, filtros é feita no backend via SQL, não no frontend, para trafegar apenas dados já resumidos e reaproveitar os mesmos filtros em ambos os endpoints.

Para suportar 100x o volume: migrar para Postgres com índices em `criacao`, `vendedor`, `status` e `lane`; trocar a paginação por offset por paginação keyset e cachear os agregados de `/api/summary`, já que os mesmos filtros se repetem entre usuários.
