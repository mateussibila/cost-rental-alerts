# Cost Rental Alerts — resumo e backlog

## Resumo do projeto

Alertas diários de **cost rental** na Irlanda. O sistema faz scrape de três fontes, guarda tudo num SQLite, detecta novidades e envia **WhatsApp** (CallMeBot) para revisão antes de publicar na Community Announcements.

| Peça | Ficheiro / destino |
|---|---|
| Scrape diário | `run_daily.py` → affordablehomes.ie, lda.ie, tuathhousing.ie |
| Base de dados | `listings.db` (~202 schemes, `category = rent`) |
| Export CSV | `export_csv.py` → `listings-export.csv` |
| Alertas | `diff.py` + `notify.py` → CallMeBot |
| Automação | GitHub Actions `.github/workflows/daily-scrape.yml` (07:00 UTC) |

**Colunas CSV hoje:** `nome`, `location` (derivada), `endereco` (Google Maps), `preco`, `quantidade`, `beds`, `is_open`, `income_min`, `income_max`, `listed_at`, `open_on`, `close_on`, `source`, `link`.

**Comportamento WhatsApp:**
- **1.ª execução com envio:** mensagem curta de bootstrap (“base criada, amanhã só novidades”).
- **Dias seguintes:** só **novidades** — abriu hoje, mudou para open, ou abre nos próximos 14 dias. Sem news → `✅ No updates today.`
- **Dedupe:** mesmo scheme em várias fontes → uma entrada (prioridade: affordablehomes > lda > tuath).

**Mensagem futura (planeado):** link hub (teu site) no topo; por listing, link curto Maps (`?q=lat,lng` ou `endereco`) + link Apply.

---

# Future improvements

Backlog de melhorias.

---

## 1. Metragem por opção de imóvel

**Objetivo:** extrair a área (m²) de cada opção/planta disponível num empreendimento.

**Contexto:** muitos schemes têm 4–5 configurações diferentes (ex. 1-bed vs 2-bed, tipologias distintas). Hoje guardamos `beds` e `quantity` agregados; falta detalhe por unidade.

**Possível abordagem:**
- Parsear a página de detalhe do affordablehomes (e LDA, se estruturado) em busca de tabelas ou blocos por tipologia
- Modelar como sub-registos ou JSON no DB, ex.:
  ```json
  [
    { "beds": 1, "area_sqm": 52, "price": 1150 },
    { "beds": 2, "area_sqm": 68, "price": 1250 }
  ]
  ```
- Incluir no CSV / planilha master como linhas expandidas ou coluna estruturada

**Desafios:** layout pode variar entre schemes; alguns só mencionam área no PDF/brochure, não no HTML.

---

## 2. Localização exata e link Maps

**Estado:** parcial — coluna `endereco` no DB/CSV; AH `Location` + LDA maps link + Tuath normalizado.

**Falta:**
- `latitude`, `longitude` no DB (AH: `data-center` em `#map` na secção Location Map)
- `maps_url` — `https://maps.google.com/?q=lat,lng` ou fallback `?q={endereco}`
- Link Maps na mensagem WhatsApp (linha `📍` antes do Apply)
- Hub site como primeiro link da mensagem (preview + entrada única)

---

## 3. Planilha master para utilizadores

**Objetivo:** disponibilizar aos utilizadores uma versão pública (ou semi-pública) dos dados — espelho do database, similar ao `listings-export.csv`.

**Conteúdo base (aba "Master"):**
- Cópia fiel do DB: `nome`, `preco`, `quantidade`, `beds`, `listed_at`, `open_on`, `close_on`, `source`, `link`
- Futuro: metragem, endereço, coordenadas (itens 1 e 2)
- Atualização automática após cada scrape diário

**Aba interativa — "Distance to":**
- Dropdown com destinos pré-definidos, ex.:
  - Dublin City Centre
  - Heuston Station
  - Connolly Station
  - Dublin Airport
  - (outros pontos de referência)
- Ao selecionar destino, calcular e mostrar distância/tempo estimado por carro ou transporte público
- Requer coordenadas do item 2 + API de routing (Google Distance Matrix, OSRM, etc.)

**Formato possível:**
- Google Sheets (Apps Script + export CSV do repo)
- Excel online
- Página web simples com filtros + export CSV (evolução natural do projeto)

**Notas:**
- Planilha master ≠ notificações WhatsApp — é consulta e comparação
- Considerar lag de atualização (1×/dia) e disclaimer de dados não oficiais

---

## 4. Site hub + mapa interativo — **alta prioridade**

**Objetivo:** site público como entrada principal (link no topo das mensagens WhatsApp) + mapa com todos os empreendimentos filtráveis.

**Porquê alta prioridade:** localização é critério decisivo; WhatsApp só alerta — o site é onde a pessoa explora e compara.

### Homepage — 3 boxes no topo

Três caixas clicáveis, sempre visíveis acima do fold. Cada uma leva à **mesma página de listagem** (`/listings` ou `/schemes`), mas com **filtro de status pré-aplicado** via query string:

| Box | Label UI | Filtro | Critério sugerido (DB) |
|---|---|---|---|
| 1 | **Apply now** | `status=open` | `status = 'open'` |
| 2 | **Opening soon** | `status=soon` | `applications_open_at` nos próximos 14 dias e ainda não open |
| 3 | **Recently closed** | `status=closed` | `status = 'closed'` e `applications_close_at` nos últimos 30 dias (ou `status_changed_at` recente) |

**URLs exemplo:**
- `/listings?filter=open`
- `/listings?filter=soon`
- `/listings?filter=closed`

A página de listagem mostra **todos** os schemes (tabela + mapa opcional), com o filtro activo e possibilidade de mudar/remover filtros (preço, beds, county, etc.). Os boxes da homepage podem mostrar **contagem** actualizada (ex. “Apply now · 5”).

**Homepage — resto:** link WhatsApp / como funciona; última actualização do scrape; disclaimer dados não oficiais.

### Página de listagem + mapa

**Funcionalidades:**
- **Mapa:** pins para cada scheme open (coordenadas do item 2)
- **Popup no pin:** nome, preço, beds, quantidade, link, datas open/close
- **Filtros / toggles:**
  - Preço (min–max ou faixas)
  - Quartos (1, 2, 3, 1–3, etc.)
  - Região / county / raio a partir de um ponto
  - Status: open only (default), opening soon, etc.
- Mapa actualiza ao mudar filtros — só mostra pins que passam nos critérios
- Lista lateral sincronizada com o mapa (opcional)

**Stack possível:**
- Frontend estático (GitHub Pages / Cloudflare Pages) + JSON exportado do DB após cada scrape
- Google Maps JavaScript API (Maps + markers; eventualmente Places)
- Alternativa open-source: Leaflet + OpenStreetMap (sem custo de API)

**Dependências:** item 2 (coordenadas) é **bloqueante** para mapa preciso; item 1 (m²) é nice-to-have no popup.

**MVP sugerido:**
1. Homepage com 3 boxes → `/listings?filter=…`
2. Export `listings.json` após cada scrape (todos os status + lat/lng + `maps_url`)
3. Listagem com filtros URL-sync (open / soon / closed + preço, beds, county)
4. Mapa com pins que reflectem filtros activos

---

## 5. Gráfico histórico de preço por m² por região

**Objetivo:** visualizar evolução do preço por metro quadrado ao longo do tempo, agregado por região.

**Contexto:** com histórico no DB (múltiplas rondas do mesmo nome, ex. Airton Plaza) e metragem por tipologia (item 1), é possível calcular €/m² e tendências regionais.

**Métrica:**
```
preco_por_m2 = price_from / area_sqm
```
- Uma entrada por tipologia quando houver várias plantas
- Região: county, Dublin postal district, ou cluster geográfico

**Visualização:**
- Linha temporal por região (ex. Dublin, Wicklow, Wexford)
- Box plot ou barras para comparar regiões no mesmo período
- Opcional: filtro por beds (1-bed vs 2-bed têm €/m² diferentes)

**Dados necessários:**
- Histórico de preços já parcialmente no DB (`listed_at`, múltiplos slugs por scheme)
- Metragem (item 1) — sem m², o gráfico não é possível
- Região normalizada (derivada de `location` ou geocoding do item 2)

**Onde viver:** secção do webapp (item 4) ou dashboard separado; pode partilhar a mesma API/JSON.

**Desafios:**
- Schemes antigos podem não ter m² no HTML
- Mesmo empreendimento, rondas com tipologias diferentes — agregar com cuidado
- Definir "região" de forma consistente (county vs neighbourhood)

---

## 6. Rendimento mínimo e máximo — **feito (LDA)**

**Estado:** `income_min` / `income_max` no DB e CSV; parse da tabela de elegibilidade LDA.

**Falta (opcional):**
- Extrair income em affordablehomes e Tuath
- `income_region` (Dublin vs resto) quando limites diferem
- Filtro “my income: €X” no webapp (item 4)

---

## Prioridades sugeridas

| Prioridade | Item | Razão |
|---|---|---|
| **Alta** | 2 (resto) → 4 | `maps_url` + lat/lng + site (3 boxes + listagem filtrável) |
| Média | WhatsApp + site | Hub no topo da msg; Maps + Apply por listing |
| Média | 1 → 5 | m² desbloqueia €/m² e gráficos regionais |
| Média | 3 | Planilha master — baixo esforço, complementa mapa |
| Baixa | 5 | Gráfico histórico — requer volume de dados + m² |

---

*Última atualização: 2026-06-06*
