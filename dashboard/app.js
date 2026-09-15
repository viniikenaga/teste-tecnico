(() => {
  "use strict";

  const state = {
    page: 1,
    perPage: 15,
    statusToggle: "aprovadas",
  };

  const charts = {};

  function themeColor(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function currentFilters() {
    return {
      lane: document.getElementById("filtro-lane").value,
      vendedor: document.getElementById("filtro-vendedor").value,
      data_inicio: document.getElementById("filtro-data-inicio").value,
      data_fim: document.getElementById("filtro-data-fim").value,
    };
  }

  function buildQuery(params) {
    const usp = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value) usp.set(key, value);
    });
    return usp.toString();
  }

  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Falha ao consultar ${url}: HTTP ${response.status}`);
    }
    return response.json();
  }

  function baseChartOptions(extra = {}) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 200 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: themeColor("--surface-1"),
          titleColor: themeColor("--text-primary"),
          bodyColor: themeColor("--text-primary"),
          borderColor: themeColor("--border"),
          borderWidth: 1,
          padding: 10,
        },
      },
      ...extra,
    };
  }

  function gridConfig() {
    return {
      color: themeColor("--gridline"),
      drawTicks: false,
    };
  }

  function tickConfig() {
    return { color: themeColor("--text-muted"), font: { size: 11 } };
  }

  function setEmptyState(canvasId, emptyId, isEmpty) {
    document.getElementById(canvasId).hidden = isEmpty;
    document.getElementById(emptyId).hidden = !isEmpty;
  }

  // ---- Top vendedores (barra horizontal, série única) ----
  function renderTopVendedores(rows) {
    setEmptyState("chart-top-vendedores", "empty-top-vendedores", rows.length === 0);
    if (rows.length === 0) return;

    const labels = rows.map((r) => r.vendedor);
    const data = rows.map((r) => r.aprovadas);

    if (charts.topVendedores) charts.topVendedores.destroy();
    const ctx = document.getElementById("chart-top-vendedores");
    charts.topVendedores = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Cotações aprovadas",
          data,
          backgroundColor: themeColor("--series-1"),
          borderRadius: 4,
          borderSkipped: false,
          maxBarThickness: 22,
        }],
      },
      options: baseChartOptions({
        indexAxis: "y",
        scales: {
          x: { beginAtZero: true, grid: gridConfig(), ticks: tickConfig() },
          y: { grid: { display: false }, ticks: tickConfig() },
        },
      }),
    });
  }

  // ---- Volume mensal (barra, série única, com toggle de status) ----
  const MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

  function renderVolumeMensal(rows) {
    setEmptyState("chart-volume-mensal", "empty-volume-mensal", rows.length === 0);
    if (rows.length === 0) return;

    const porMes = new Map(rows.map((r) => [r.mes, r.quantidade]));
    const labels = MESES;
    const data = MESES.map((_, i) => porMes.get(i + 1) || 0);

    if (charts.volumeMensal) charts.volumeMensal.destroy();
    const ctx = document.getElementById("chart-volume-mensal");
    charts.volumeMensal = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Cotações",
          data,
          backgroundColor: themeColor("--series-1"),
          borderRadius: 4,
          borderSkipped: false,
          maxBarThickness: 24,
        }],
      },
      options: baseChartOptions({
        scales: {
          y: { beginAtZero: true, grid: gridConfig(), ticks: tickConfig() },
          x: { grid: { display: false }, ticks: tickConfig() },
        },
      }),
    });
  }

  // ---- Distribuição de status (rosca) ----
  const STATUS_LABELS = {
    APROVADO: "Aprovado",
    REJEITADO: "Reprovado",
    ESTUDO: "Estudo",
    "SEGUNDA OPCAO": "Segunda opção",
  };
  const STATUS_ORDER = ["APROVADO", "REJEITADO", "ESTUDO", "SEGUNDA OPCAO"];
  const STATUS_COLOR_VARS = ["--series-1", "--series-2", "--series-3", "--series-4"];

  function renderStatusLegend(labels, data, colors, total) {
    const legend = document.getElementById("status-legend");
    legend.replaceChildren();

    labels.forEach((label, i) => {
      const value = data[i];
      const pct = ((value / total) * 100).toFixed(1);

      const li = document.createElement("li");

      const dot = document.createElement("span");
      dot.className = "legend-dot";
      dot.style.backgroundColor = colors[i];
      li.appendChild(dot);

      const text = document.createElement("span");
      text.textContent = `${label}: ${value} (${pct}%)`;
      li.appendChild(text);

      legend.appendChild(li);
    });
  }

  function renderStatusDistribution(rows) {
    const total = rows.reduce((acc, r) => acc + r.quantidade, 0);
    setEmptyState("chart-status", "empty-status", total === 0);
    document.getElementById("status-legend").hidden = total === 0;
    if (total === 0) return;

    const byStatus = new Map(rows.map((r) => [r.status, r.quantidade]));
    const labels = STATUS_ORDER.map((s) => STATUS_LABELS[s]);
    const data = STATUS_ORDER.map((s) => byStatus.get(s) || 0);
    const colors = STATUS_COLOR_VARS.map(themeColor);

    renderStatusLegend(labels, data, colors, total);

    if (charts.status) charts.status.destroy();
    const ctx = document.getElementById("chart-status");
    charts.status = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels,
        datasets: [{
          data,
          backgroundColor: colors,
          borderColor: themeColor("--surface-1"),
          borderWidth: 2,
        }],
      },
      options: baseChartOptions({
        cutout: "62%",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: themeColor("--surface-1"),
            titleColor: themeColor("--text-primary"),
            bodyColor: themeColor("--text-primary"),
            borderColor: themeColor("--border"),
            borderWidth: 1,
            padding: 10,
            callbacks: {
              label(item) {
                const value = item.raw;
                const currentTotal = item.chart.data.datasets[0].data.reduce((acc, v) => acc + v, 0) || 1;
                const pct = ((value / currentTotal) * 100).toFixed(1);
                return `${item.label}: ${value} (${pct}%)`;
              },
            },
          },
        },
      }),
    });
  }

  // ---- Volume por lane (barra, série única) ----
  function renderLaneDistribution(rows) {
    setEmptyState("chart-lane", "empty-lane", rows.length === 0);
    if (rows.length === 0) return;

    const labels = rows.map((r) => r.lane);
    const data = rows.map((r) => r.quantidade);

    if (charts.lane) charts.lane.destroy();
    const ctx = document.getElementById("chart-lane");
    charts.lane = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Cotações",
          data,
          backgroundColor: themeColor("--series-1"),
          borderRadius: 4,
          borderSkipped: false,
          maxBarThickness: 24,
        }],
      },
      options: baseChartOptions({
        scales: {
          y: { beginAtZero: true, grid: gridConfig(), ticks: tickConfig() },
          x: { grid: { display: false }, ticks: tickConfig() },
        },
      }),
    });
  }

  async function loadSummary() {
    const params = { ...currentFilters(), status_toggle: state.statusToggle };
    const query = buildQuery(params);
    const data = await fetchJSON(`/api/summary?${query}`);

    document.getElementById("stat-total").textContent = data.total_cotacoes.toLocaleString("pt-BR");
    renderTopVendedores(data.top_vendedores);
    renderVolumeMensal(data.volume_mensal);
    renderStatusDistribution(data.status_distribution);
    renderLaneDistribution(data.lane_distribution);
  }

  // ---- Projeção de demanda (SES sobre o histórico diário) ----
  function renderForecast(forecast) {
    const caption = document.getElementById("forecast-caption");

    if (!forecast.suficiente) {
      setEmptyState("chart-forecast", "empty-forecast", true);
      caption.textContent = "";
      return;
    }
    setEmptyState("chart-forecast", "empty-forecast", false);

    const labels = forecast.meses.map((m) => m.label);
    const real = forecast.meses.map((m) => (m.tipo === "real" ? m.quantidade : null));
    const projecao = forecast.meses.map((m) => (m.tipo === "projecao" ? m.quantidade : null));
    const mesesReais = forecast.meses.filter((m) => m.tipo === "real").length;

    caption.textContent =
      `Método: suavização exponencial simples (α = 0,3) sobre ${forecast.pontos_historico} dia(s) ` +
      `com cotações registradas — média projetada de ${forecast.media_diaria_projetada} cotações/dia. ` +
      (mesesReais === 1
        ? "O mês \"Real\" reflete apenas os dias com dados no período filtrado, não necessariamente o mês inteiro, " +
          "por isso pode não ser diretamente comparável aos meses projetados (mês cheio). "
        : "") +
      "Estimativa ilustrativa para apoiar planejamento, não uma previsão operacional definitiva.";

    if (charts.forecast) charts.forecast.destroy();
    const ctx = document.getElementById("chart-forecast");
    charts.forecast = new Chart(ctx, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Real",
            data: real,
            backgroundColor: themeColor("--series-1"),
            borderRadius: 4,
            borderSkipped: false,
            maxBarThickness: 40,
          },
          {
            label: "Projeção",
            data: projecao,
            backgroundColor: themeColor("--series-1-wash"),
            borderColor: themeColor("--series-1"),
            borderWidth: 1.5,
            borderDash: [5, 4],
            borderRadius: 4,
            borderSkipped: false,
            maxBarThickness: 40,
          },
        ],
      },
      options: baseChartOptions({
        scales: {
          y: { beginAtZero: true, grid: gridConfig(), ticks: tickConfig() },
          x: { grid: { display: false }, ticks: tickConfig() },
        },
      }),
    });
  }

  async function loadForecast() {
    const params = currentFilters();
    const query = buildQuery(params);
    const data = await fetchJSON(`/api/forecast?${query}`);
    renderForecast(data);
  }

  function formatDate(isoDate) {
    if (!isoDate) return "";
    const [y, m, d] = isoDate.split("-");
    return `${d}/${m}/${y}`;
  }

  async function loadCotacoes() {
    const params = { ...currentFilters(), page: state.page, per_page: state.perPage };
    const query = buildQuery(params);
    const data = await fetchJSON(`/api/cotacoes?${query}`);

    const tbody = document.getElementById("tabela-cotacoes-body");
    tbody.replaceChildren();

    if (data.items.length === 0) {
      const tr = document.createElement("tr");
      tr.className = "table-empty-row";
      const td = document.createElement("td");
      td.colSpan = 9;
      td.textContent = "Nenhuma cotação encontrada para os filtros selecionados.";
      tr.appendChild(td);
      tbody.appendChild(tr);
    }

    data.items.forEach((item) => {
      const tr = document.createElement("tr");
      const cells = [
        item.codigo, item.cliente, formatDate(item.criacao), item.status,
        item.modal, item.paisorigem, item.paisdestino, item.vendedor, item.lane,
      ];
      cells.forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value ?? "";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    state.page = data.page;
    document.getElementById("table-summary").textContent = `${data.total.toLocaleString("pt-BR")} registro(s)`;
    document.getElementById("pagination-info").textContent = `Página ${data.page} de ${data.total_pages}`;
    document.getElementById("btn-prev").disabled = data.page <= 1;
    document.getElementById("btn-next").disabled = data.page >= data.total_pages;
  }

  async function refreshAll() {
    state.page = 1;
    await Promise.all([loadSummary(), loadForecast(), loadCotacoes()]);
  }

  function populateSelect(select, values) {
    const current = select.value;
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.appendChild(option);
    });
    if (values.includes(current)) select.value = current;
  }

  async function loadFiltroOptions() {
    const data = await fetchJSON("/api/filtros");
    populateSelect(document.getElementById("filtro-lane"), data.lanes);
    populateSelect(document.getElementById("filtro-vendedor"), data.vendedores);
  }

  function wireEvents() {
    document.getElementById("btn-aplicar").addEventListener("click", refreshAll);

    document.getElementById("btn-limpar").addEventListener("click", () => {
      document.getElementById("filtro-lane").value = "";
      document.getElementById("filtro-vendedor").value = "";
      document.getElementById("filtro-data-inicio").value = "";
      document.getElementById("filtro-data-fim").value = "";
      refreshAll();
    });

    document.querySelectorAll(".toggle-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".toggle-btn").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.statusToggle = btn.dataset.status;
        loadSummary();
      });
    });

    document.getElementById("btn-prev").addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        loadCotacoes();
      }
    });

    document.getElementById("btn-next").addEventListener("click", () => {
      state.page += 1;
      loadCotacoes();
    });

    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      loadSummary();
      loadForecast();
    });
  }

  async function init() {
    wireEvents();
    await loadFiltroOptions();
    await refreshAll();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
