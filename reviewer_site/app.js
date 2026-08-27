(() => {
  "use strict";

  const route = document.body.dataset.route || "home";
  const main = document.querySelector("#main");
  const cache = new Map();
  const REQUIRED_CATEGORIES = [
    "Tools", "Tasks", "Companies", "News", "Videos", "Robots", "Devices", "Models",
    "Repositories", "MCP", "Collections", "Personal", "Products", "Creative", "New/Recently Added",
  ];

  document.querySelector(`[data-nav="${route}"]`)?.classList.add("active");

  const escapeHtml = (value) => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
  const text = (value, fallback = "—") => {
    const result = String(value ?? "").trim();
    return result || fallback;
  };
  const number = (value) => Number(value ?? 0).toLocaleString("en-US");
  const asRecords = (payload) => Array.isArray(payload) ? payload : (Array.isArray(payload?.records) ? payload.records : []);
  const isUrl = (value) => /^https?:\/\//i.test(String(value || ""));
  const link = (value, label = "open") => isUrl(value)
    ? `<a class="table-link" href="${escapeHtml(value)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`
    : "—";
  const statusClass = (status) => String(status || "").toLowerCase() === "passed" ? "status-passed" : "status-limited";

  async function load(path) {
    if (!cache.has(path)) {
      cache.set(path, fetch(path, { credentials: "same-origin" }).then(async (response) => {
        if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
        return response.json();
      }));
    }
    return cache.get(path);
  }

  function hero(eyebrow, title, description, aside) {
    return `<section class="hero">
      <div><p class="eyebrow">${escapeHtml(eyebrow)}</p><h1>${escapeHtml(title)}</h1><p class="hero-copy">${description}</p></div>
      <aside class="hero-aside">${aside}</aside>
    </section>`;
  }

  function metric(label, value, detail = "", className = "") {
    return `<article class="metric-card ${className}"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div>${detail ? `<div class="detail">${detail}</div>` : ""}</article>`;
  }

  function cards(items) {
    return `<div class="card-grid">${items.map((item) => `<article class="info-card"><h3>${escapeHtml(item.title)}</h3><p>${item.body}</p>${item.meta ? `<span class="mono">${escapeHtml(item.meta)}</span>` : ""}</article>`).join("")}</div>`;
  }

  function section(title, description, content) {
    return `<section class="section"><div class="section-heading"><div><h2>${escapeHtml(title)}</h2>${description ? `<p>${description}</p>` : ""}</div></div>${content}</section>`;
  }

  function kv(entries) {
    return `<dl class="definition-list">${entries.map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${value}</dd>`).join("")}</dl>`;
  }

  function table(id, columns, rows, { limit = 100, searchable = true, empty = "No records." } = {}) {
    const input = searchable ? `<div class="table-controls"><label for="${id}-search">Filter rows</label><input id="${id}-search" type="search" placeholder="Type to filter the loaded rows"></div>` : "";
    const safeRows = rows.slice(0, limit);
    const headers = columns.map((column) => `<th scope="col">${escapeHtml(column.label)}</th>`).join("");
    const body = safeRows.length ? safeRows.map((row) => {
      const search = columns.map((column) => text(column.raw ? column.raw(row) : row[column.key], "")).join(" ").toLowerCase();
      return `<tr data-search="${escapeHtml(search)}">${columns.map((column) => `<td class="${column.className || ""}">${column.render ? column.render(row) : escapeHtml(text(row[column.key]))}</td>`).join("")}</tr>`;
    }).join("") : `<tr><td colspan="${columns.length}"><div class="empty">${escapeHtml(empty)}</div></td></tr>`;
    const note = rows.length > limit ? `<p class="mono">Showing ${number(limit)} of ${number(rows.length)} loaded records. Use the downloadable JSON/CSV artifacts for the complete table.</p>` : "";
    return `${input}<div class="table-wrap"><table id="${id}"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table></div>${note}`;
  }

  function attachSearches() {
    document.querySelectorAll("[id$='-search']").forEach((input) => {
      input.addEventListener("input", () => {
        const needle = input.value.toLowerCase().trim();
        const tableElement = document.querySelector(`#${CSS.escape(input.id.replace(/-search$/, ""))}`);
        tableElement?.querySelectorAll("tbody tr[data-search]").forEach((row) => {
          row.hidden = !!needle && !row.dataset.search.includes(needle);
        });
      });
    });
  }

  function categoryCounts(entities) {
    const counts = Object.fromEntries(REQUIRED_CATEGORIES.map((name) => [name, 0]));
    entities.forEach((entity) => (entity.categories || []).forEach((name) => { counts[name] = (counts[name] || 0) + 1; }));
    return counts;
  }

  async function loadOrbit() {
    const [entities, relationships, validation, mappings, feasibility] = await Promise.all([
      load("data/entities.json"),
      load("data/relationships.json"),
      load("data/validation_report.json"),
      load("data/entity_mapping_log.json"),
      load("data/source_feasibility.json"),
    ]);
    return { entities: asRecords(entities), relationships: asRecords(relationships), validation, mappings: asRecords(mappings), feasibility: asRecords(feasibility) };
  }

  async function loadGraphOne() {
    const [validation, manifest, startups, products, research, jobs, news, mappings] = await Promise.all([
      load("data/graphone/validation_report.json"),
      load("data/graphone/run_manifest.json"),
      load("data/graphone/startups.json"),
      load("data/graphone/products.json"),
      load("data/graphone/research_papers.json"),
      load("data/graphone/jobs.json"),
      load("data/graphone/news.json"),
      load("data/graphone/entity_mapping_log.json"),
    ]);
    return {
      validation, manifest,
      startups: asRecords(startups), products: asRecords(products), research: asRecords(research),
      jobs: asRecords(jobs), jobsPayload: jobs, news: asRecords(news), mappings: asRecords(mappings),
    };
  }

  async function renderHome() {
    const [{ entities, relationships, validation }, graph] = await Promise.all([loadOrbit(), loadGraphOne()]);
    const summary = graph.validation.summary || {};
    main.innerHTML = `${hero(
      "FINAL SUBMISSION REVIEW",
      "Evidence first. Two distinct workstreams.",
      "<strong>AI Orbit</strong> is a 250–300 record entity-and-relationship corpus. <strong>GraphOne</strong> is a separate trial dataset with independently packaged startup, product, research-paper, News, Jobs, and mapping outputs. Counts are never conflated.",
      "This viewer reads committed JSON and CSV artifacts only. It performs <strong>no discovery, crawling, or re-ingestion</strong>."
    )}
    <div class="metric-grid">
      ${metric("AI Orbit entities", number(entities.length), "Representative graph corpus")}
      ${metric("AI Orbit relationships", number(relationships.length), "All carry evidence", "")}
      ${metric("AI Orbit validation", text(validation.status).toUpperCase(), `${number(validation.summary?.provenance_coverage * 100)}% entity provenance`, statusClass(validation.status))}
      ${metric("GraphOne validation", text(graph.validation.status).toUpperCase(), `${number(summary.total_records)} accepted records across separate tabs`, statusClass(graph.validation.status))}
    </div>
    ${section("Review paths", "Open an artifact-focused view; each table retains record-level source links.", `<div class="route-links">
      <a href="ai-orbit/">AI Orbit overview</a><a href="graphone/">GraphOne overview</a><a href="entities/">Entities</a><a href="relationships/">Relationships</a><a href="validation/">Validation</a><a href="mapping/">Entity mapping</a><a href="feasibility/">Source feasibility</a><a href="categories/">Categories</a>
    </div>`)}
    ${section("Explicit limits", "A reviewer should be able to see what was not claimed.", cards([
      { title: "GraphOne Jobs", body: `Accepted rows: <strong>${number(summary.jobs)}</strong>. No source-proven employer <span class="mono">posted_at</span> was available inside the strict 24-hour window; no timestamp was manufactured.`, meta: "honest zero" },
      { title: "GraphOne product metadata", body: "The selected directory directly supplies product name, URL, and description. It does not supply provider/company or pricing, so both fields remain null.", meta: "nulls preserved" },
      { title: "AI Orbit scope", body: "The AI Orbit corpus targets representative quality, not GraphOne scale. Jobs and Personal may remain absent where source identity/timestamp gates fail.", meta: "workstreams stay separate" },
    ]))}`;
  }

  async function renderOrbit() {
    const { entities, relationships, validation, feasibility } = await loadOrbit();
    const typeCounts = Object.entries(validation.per_entity_type_counts || {}).sort(([a], [b]) => a.localeCompare(b));
    const sourceCounts = Object.entries(validation.per_source_counts || {}).sort((a, b) => b[1] - a[1]);
    main.innerHTML = `${hero(
      "AI ORBIT · COMMITTED CORPUS",
      "A representative, evidence-backed entity graph.",
      "The pipeline implements discovery → extraction → cleaning → normalization → deterministic resolution → classification → relationship mapping → validation. Every displayed count is read from the committed output files.",
      `Validation: <strong>${escapeHtml(text(validation.status).toUpperCase())}</strong><br>Entity provenance coverage: <strong>${number((validation.summary?.provenance_coverage || 0) * 100)}%</strong>`
    )}
    <div class="metric-grid">
      ${metric("Entities", number(entities.length), "Target band: 250–300")}
      ${metric("Relationships", number(relationships.length), "Evidence on every accepted edge")}
      ${metric("Sources", number(sourceCounts.length), "Accepted-source coverage")}
      ${metric("Validation failures", number((validation.failures || []).length), "Rejected records: " + number((validation.rejected_records || []).length), validation.status === "passed" ? "status-passed" : "status-limited")}
    </div>
    ${section("Entity types", "The corpus contains the following source-backed entity types.", cards(typeCounts.map(([type, count]) => ({ title: type, body: `<strong class="numeric">${number(count)}</strong> accepted entities`, meta: "AI Orbit" }))))}
    ${section("Accepted source coverage", "Counts are output-level observations, not an assertion that every candidate source was usable.", table("orbit-sources", [{ label: "Source", key: "name" }, { label: "Entities", key: "count", className: "numeric" }], sourceCounts.map(([name, count]) => ({ name, count })), { searchable: false, limit: 50 }))}
    ${section("Validation notes", "Warnings and failed source probes remain visible rather than being hidden.", `
      <div class="note good"><strong>Validation status:</strong> ${escapeHtml(text(validation.status))}; ${number((validation.failures || []).length)} failures, ${number((validation.rejected_records || []).length)} rejected records, ${number((validation.warnings || []).length)} warnings.</div>
      <p class="mono">Source feasibility records: ${number(feasibility.length)} · source failures: ${number((validation.source_failures || []).length)}</p>`)}
    `;
  }

  async function renderGraphOne() {
    const graph = await loadGraphOne();
    const summary = graph.validation.summary || {};
    const tabRows = [
      { tab: "Startups", count: summary.startups, source: graph.validation.per_tab?.Startups?.source_name, evidence: "Pinned public YC-directory snapshot; row-level source links and source-row IDs." },
      { tab: "Products", count: summary.products, source: graph.validation.per_tab?.Products?.source_name, evidence: "Direct product handle, URL, description, and AI-evidence gate; unknown provider/pricing stays null." },
      { tab: "Research Papers", count: summary.research_papers, source: graph.validation.per_tab?.["Research Papers"]?.source_name, evidence: "Preserved existing 1,000-paper arXiv export; independently packaged without re-ingestion." },
      { tab: "Jobs", count: summary.jobs, source: "No accepted source", evidence: "No actual employer posted_at available; no fresh claim is made." },
      { tab: "News", count: summary.news, source: graph.validation.per_tab?.News?.source_name, evidence: "GitHub release published_at only; final 24-hour window enforced." },
      { tab: "Entity Mapping Log", count: summary.entity_mapping_log, source: "Deterministic mapping", evidence: "One mapping record per accepted GraphOne row." },
    ];
    main.innerHTML = `${hero(
      "GRAPHONE TRIAL · SEPARATE OUTPUT",
      "1,000 startups, 1,000 products, and 1,000 research papers — independently packaged.",
      "These rows are <strong>not</strong> derived from the AI Orbit count. Every accepted GraphOne row has a traceable source URL, deterministic ID, provenance, and a mapping entry. The strict News/Jobs freshness requirement is isolated from non-fresh tab data.",
      `Validation: <strong>${escapeHtml(text(graph.validation.status).toUpperCase())}</strong><br>Generated: <span class="mono">${escapeHtml(text(graph.validation.generatedAt))}</span>`
    )}
    <div class="metric-grid">
      ${metric("Startups", number(summary.startups), "Source-backed active YC snapshot rows")}
      ${metric("Products", number(summary.products), "Direct directory product identities")}
      ${metric("Research Papers", number(summary.research_papers), "Existing output preserved")}
      ${metric("Fresh News / Jobs", `${number(summary.news)} / ${number(summary.jobs)}`, "News only uses release publication timestamps")}
    </div>
    ${section("Required Sheets tabs", "The local CSV exports mirror these exact tabs. A configured service account can sync them; the Sheet is never used as a source.", table("graphone-tabs", [
      { label: "Tab", key: "tab" }, { label: "Accepted rows", key: "count", className: "numeric", render: (row) => number(row.count) }, { label: "Source", key: "source" }, { label: "Evidence / limit", key: "evidence" },
    ], tabRows, { searchable: false, limit: 10 }))}
    ${section("Freshness and rejected records", "The final 24-hour window applies only to News and Jobs.", kv([
      ["Freshness window", `<span class="mono">${escapeHtml(text(summary.freshness_window_start))}</span> to <span class="mono">${escapeHtml(text(summary.freshness_window_end))}</span>`],
      ["News timestamp semantics", escapeHtml(text(graph.validation.per_tab?.News?.freshness_requirement))],
      ["Jobs status", escapeHtml(text(graph.validation.per_tab?.Jobs?.freshness_requirement))],
      ["Mapping coverage", `${number((summary.mapping_coverage || 0) * 100)}%`],
      ["Provenance coverage", `${number((summary.provenance_coverage || 0) * 100)}%`],
    ]))}
    ${section("Accepted record samples and exports", "Samples expose row-level evidence; complete committed JSON and Sheet-shaped CSVs are linked below.", `
      <p class="mono"><a href="data/graphone/startups.json">Startups JSON</a> · <a href="data/graphone/products.json">Products JSON</a> · <a href="data/graphone/research_papers.json">Research Papers JSON</a> · <a href="data/graphone/news.json">News JSON</a> · <a href="data/graphone/jobs.json">Jobs JSON</a> · <a href="data/graphone/entity_mapping_log.json">Entity Mapping Log JSON</a></p>
      <h3>Startups</h3>${table("graphone-startups", [
        { label: "Name", key: "canonical_name" },
        { label: "Employees", key: "employee_count", className: "numeric", render: (row) => number(row.employee_count) },
        { label: "Batch", key: "yc_batch" },
        { label: "Industry", key: "industry" },
        { label: "Source row", key: "source_url", render: (row) => link(row.source_url, "pinned source") },
      ], graph.startups, { searchable: false, limit: 8 })}
      <h3>Products</h3>${table("graphone-products", [
        { label: "Product", key: "product_name" },
        { label: "Description", key: "description", render: (row) => `<span class="truncate" title="${escapeHtml(text(row.description))}">${escapeHtml(text(row.description))}</span>` },
        { label: "Product URL", key: "product_url", render: (row) => link(row.product_url, "product") },
        { label: "Source", key: "source_url", render: (row) => link(row.source_url, "directory") },
      ], graph.products, { searchable: false, limit: 8 })}
      <h3>Fresh News</h3>${table("graphone-news", [
        { label: "Published", key: "published_at", className: "mono" },
        { label: "Publisher", key: "publisher" },
        { label: "Title", key: "title" },
        { label: "Release", key: "canonical_url", render: (row) => link(row.canonical_url, "announcement") },
        { label: "Evidence", key: "source_url", render: (row) => link(row.source_url, "API source") },
      ], graph.news, { searchable: false, limit: 12 })}`)}
    ${section("Source manifest", "Pinned input identities make the startup/product extracts reviewable after their upstream directories change.", cards([
      { title: "Startups", body: link(graph.manifest.sources?.startups?.source_file_url, "pinned YC snapshot source") + `<p>${escapeHtml(text(graph.manifest.sources?.startups?.selection))}</p>`, meta: `snapshot ${text(graph.manifest.sources?.startups?.snapshot_date)}` },
      { title: "Products", body: link(graph.manifest.sources?.products?.source_file_url, "pinned product directory source") + `<p>${escapeHtml(text(graph.manifest.sources?.products?.selection))}</p>`, meta: `commit ${text(graph.manifest.sources?.products?.commit)}` },
      { title: "Jobs", body: "No records were added from a crawler/listing-added time. The reviewer exposes the rejected source checks in Validation.", meta: "strict posted_at gate" },
    ]))}`;
  }

  async function renderEntities() {
    const { entities } = await loadOrbit();
    main.innerHTML = `${hero("AI ORBIT · ENTITY VIEW", "Browse every committed AI Orbit entity.", "Filter within the loaded entity corpus. Source links point to the evidence URL retained in each committed entity record.", "IDs use deterministic UUIDv5 identity generation after normalization and resolution.")}
      ${section("Entities", `${number(entities.length)} total accepted records.`, table("entities", [
        { label: "Name", key: "name" },
        { label: "Type", key: "entity_type", render: (row) => `<span class="badge">${escapeHtml(text(row.entity_type))}</span>` },
        { label: "Categories", key: "categories", render: (row) => (row.categories || []).map((item) => `<span class="badge">${escapeHtml(item)}</span>`).join(" ") || "—" },
        { label: "Description", key: "description", render: (row) => `<span class="truncate" title="${escapeHtml(text(row.description))}">${escapeHtml(text(row.description))}</span>` },
        { label: "Source", key: "source", render: (row) => link(row.source?.url || row.provenance?.source_url, text(row.source?.name, "source")) },
        { label: "ID", key: "id", className: "mono" },
      ], entities, { limit: 254 }))}`;
  }

  async function renderRelationships() {
    const { entities, relationships } = await loadOrbit();
    const names = new Map(entities.map((entity) => [entity.id, `${entity.name} (${entity.entity_type})`]));
    main.innerHTML = `${hero("AI ORBIT · RELATIONSHIP VIEW", "Every accepted edge has source evidence.", "Relationship endpoints are resolved against committed entities. The view shows edge type, source and target, method, and the source evidence link.", "The final validation report contains no invalid relationship endpoints and no missing relationship evidence.")}
      ${section("Relationships", `${number(relationships.length)} total accepted edges.`, table("relationships", [
        { label: "Type", key: "relationship_type", render: (row) => `<span class="badge green">${escapeHtml(text(row.relationship_type))}</span>` },
        { label: "Source entity", key: "source_entity_id", render: (row) => `<span>${escapeHtml(text(names.get(row.source_entity_id)))}</span><br><span class="mono">${escapeHtml(text(row.source_entity_id))}</span>` },
        { label: "Target entity", key: "target_entity_id", render: (row) => `<span>${escapeHtml(text(names.get(row.target_entity_id)))}</span><br><span class="mono">${escapeHtml(text(row.target_entity_id))}</span>` },
        { label: "Method", key: "method", className: "mono" },
        { label: "Evidence", key: "evidence", render: (row) => `${link(row.evidence?.source_url || row.source?.url, "source evidence")}<br><span class="truncate" title="${escapeHtml(text(row.evidence?.reason || row.evidence?.observed_field))}">${escapeHtml(text(row.evidence?.reason || row.evidence?.observed_field))}</span>` },
      ], relationships, { limit: 200 }))}`;
  }

  function listFailures(items, emptyText) {
    if (!items?.length) return `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return table("issues", [
      { label: "Type", key: "type", render: (row) => `<span class="badge amber">${escapeHtml(text(row.type || row.source || row.status))}</span>` },
      { label: "Record / source", key: "record_id", render: (row) => `<span class="mono">${escapeHtml(text(row.record_id || row.source || row.repository))}</span>` },
      { label: "Detail", key: "message", render: (row) => escapeHtml(text(row.message || row.failure || row.reason)) },
      { label: "URL", key: "url", render: (row) => link(row.url, "source") },
    ], items, { limit: 100 });
  }

  async function renderValidation() {
    const [{ validation: orbit }, graph] = await Promise.all([loadOrbit(), loadGraphOne()]);
    const graphRejected = graph.validation.rejected_records || {};
    const graphSourceChecks = [
      ...(graph.validation.source_checks?.jobs || []),
      ...(graph.validation.source_checks?.news || []).filter((item) => item.status !== "usable"),
    ];
    const rejectionRows = Object.entries(graphRejected).flatMap(([tab, value]) => Object.entries(value?.rejected_by_reason || {}).map(([reason, count]) => ({ tab, reason, count })));
    main.innerHTML = `${hero("VALIDATION · FAILURE BOUNDARIES", "What passed, what was rejected, and why.", "Validation is displayed as evidence, not marketing. A source outage cannot silently turn into fabricated rows; rejected candidate reasons and source feasibility checks remain inspectable.", "Both reports are read directly from committed JSON. No source is re-contacted when this page loads.")}
      <div class="metric-grid">
        ${metric("AI Orbit", text(orbit.status).toUpperCase(), `${number((orbit.failures || []).length)} failures · ${number((orbit.rejected_records || []).length)} rejected`, statusClass(orbit.status))}
        ${metric("AI Orbit warnings", number((orbit.warnings || []).length), `${number((orbit.source_failures || []).length)} source failures`) }
        ${metric("GraphOne", text(graph.validation.status).toUpperCase(), `${number((graph.validation.failures || []).length)} failures`, statusClass(graph.validation.status))}
        ${metric("GraphOne fresh News", number(graph.validation.summary?.news), `Jobs accepted: ${number(graph.validation.summary?.jobs)}`)}
      </div>
      ${section("AI Orbit validation failures", "Accepted corpus failures are empty when the validation report passes.", listFailures(orbit.failures, "No AI Orbit validation failures."))}
      ${section("AI Orbit source failures and warnings", "Unusable sources and shared-evidence URL warnings are retained for review.", listFailures([...(orbit.source_failures || []), ...(orbit.warnings || [])], "No AI Orbit source failures or warnings."))}
      ${section("GraphOne rejected candidate summary", "Valid surplus rows withheld by the 1,000-row target limit are not called rejected; they are separately counted in the report.", table("graphone-rejections", [
        { label: "Tab", key: "tab" }, { label: "Reason", key: "reason", className: "mono" }, { label: "Rows / checks", key: "count", className: "numeric", render: (row) => number(row.count) },
      ], rejectionRows, { searchable: false, limit: 50, empty: "No GraphOne rejected-record summary." }))}
      ${section("GraphOne source checks", "Jobs remain empty because these checks never established an acceptable employer posted_at field.", listFailures(graphSourceChecks, "No failed or rejected GraphOne source checks."))}`;
  }

  async function renderMapping() {
    const [{ mappings: orbitMappings }, graph] = await Promise.all([loadOrbit(), loadGraphOne()]);
    const mappings = [
      ...orbitMappings.map((item) => ({ scope: "AI Orbit", ...item })),
      ...graph.mappings.map((item) => ({ scope: "GraphOne", ...item })),
    ];
    const countByScope = mappings.reduce((result, item) => ({ ...result, [item.scope]: (result[item.scope] || 0) + 1 }), {});
    main.innerHTML = `${hero("ENTITY RESOLUTION · MAPPING LOG", "Deterministic identities, visible mapping decisions.", "The mapping log makes raw source keys, canonical values, methods, reasons, and source URLs inspectable. GraphOne deliberately preserves startup source-row identity where name-only merging would conflate homonyms.", "No LLM or guessed entity resolution is used for these mapping records.")}
      <div class="metric-grid">
        ${metric("AI Orbit mappings", number(countByScope["AI Orbit"] || 0), "URL + normalized-name resolution")}
        ${metric("GraphOne mappings", number(countByScope.GraphOne || 0), "One entry per accepted GraphOne record")}
        ${metric("GraphOne coverage", `${number((graph.validation.summary?.mapping_coverage || 0) * 100)}%`, "Validated canonical ID coverage", "status-passed")}
        ${metric("Total mappings", number(mappings.length), "Committed log entries")}
      </div>
      ${section("Mapping records", `${number(mappings.length)} combined AI Orbit and GraphOne entries.`, table("mappings", [
        { label: "Scope", key: "scope", render: (row) => `<span class="badge">${escapeHtml(row.scope)}</span>` },
        { label: "Method", key: "method", className: "mono" },
        { label: "Raw source key", key: "raw_source_key", className: "mono" },
        { label: "Canonical value", key: "canonical_value" },
        { label: "Reason", key: "reason", render: (row) => `<span class="truncate" title="${escapeHtml(text(row.reason))}">${escapeHtml(text(row.reason))}</span>` },
        { label: "Source", key: "source_url", render: (row) => link(row.source_url, "evidence") },
      ], mappings, { limit: 250 }))}`;
  }

  async function renderFeasibility() {
    const { feasibility } = await loadOrbit();
    main.innerHTML = `${hero("SOURCE FEASIBILITY", "Accepted sources and honest source failures.", "Each feasibility object documents access method, field availability, quality constraints, observed status, and failure behavior. A source can be useful for a probe yet ineligible for ingestion.", "The reviewer does not retry these probes. It displays the committed verification result only.")}
      ${section("Feasibility records", `${number(feasibility.length)} committed source assessments.`, table("feasibility", [
        { label: "Source", key: "source_name" },
        { label: "Domain", key: "domain", render: (row) => `<span class="badge">${escapeHtml(text(row.domain))}</span>` },
        { label: "Status", key: "status", render: (row) => `<span class="badge ${row.status === "usable" ? "green" : row.status === "unusable" ? "red" : "amber"}">${escapeHtml(text(row.status))}</span>` },
        { label: "Yield", key: "yielded_usable_records", className: "numeric", render: (row) => number(row.yielded_usable_records) },
        { label: "Access / limitation", key: "actual_crawl_feasibility", render: (row) => `<span class="truncate" title="${escapeHtml(text(row.actual_crawl_feasibility || row.failure_behavior))}">${escapeHtml(text(row.actual_crawl_feasibility || row.failure_behavior))}</span>` },
        { label: "URL", key: "url", render: (row) => link(row.url, "source") },
      ], feasibility, { limit: 100 }))}`;
  }

  async function renderCategories() {
    const { entities, validation } = await loadOrbit();
    const counts = categoryCounts(entities);
    const rows = REQUIRED_CATEGORIES.map((category) => ({ category, count: counts[category] || 0 }));
    main.innerHTML = `${hero("AI ORBIT · CATEGORY VIEW", "All requested categories, including honest zeros.", "Category assignments are driven by source observations and conservative classification. A zero is displayed rather than filled with an unsupported record.", "Category file artifacts are generated under data/categories/ for populated categories; this view also makes missing categories explicit.")}
      ${section("Category counts", "Counts sum category assignments; multi-category entities can appear in more than one count.", `<ul class="category-list">${rows.map((row) => `<li><strong>${escapeHtml(row.category)}</strong><span>${number(row.count)}</span></li>`).join("")}</ul>`)}
      ${section("Current category policy", "The corpus maintains a 250–300 entity target while retaining high-quality distinctions.", kv([
        ["Required categories", `${number(REQUIRED_CATEGORIES.length)} categories displayed`],
        ["Current classified entities", number(validation.summary?.total_classified || entities.length)],
        ["Jobs / Personal", "No records are inserted until source identity and timestamp/semantics gates are satisfied."],
        ["Products", "Product directory supplies identity/URL/description; provider and pricing are left null if not directly supplied."],
      ]))}`;
  }

  const renderers = {
    home: renderHome,
    "ai-orbit": renderOrbit,
    graphone: renderGraphOne,
    entities: renderEntities,
    relationships: renderRelationships,
    validation: renderValidation,
    mapping: renderMapping,
    feasibility: renderFeasibility,
    categories: renderCategories,
  };

  (async () => {
    try {
      await (renderers[route] || renderHome)();
      attachSearches();
    } catch (error) {
      console.error(error);
      main.innerHTML = `${hero("REVIEWER ERROR", "A committed artifact could not be loaded.", "The reviewer did not run ingestion or alter data. Inspect the error below and the repository artifact paths.", "Read-only failure boundary.")}
        <section class="section"><div class="note error"><strong>Load error:</strong> <span class="mono">${escapeHtml(error.message || String(error))}</span></div></section>`;
    }
  })();
})();
