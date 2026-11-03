const ids = [
  "scope",
  "refresh",
  "diagram",
  "vertices",
  "edges",
  "next-vertices",
  "next-edges",
  "kind",
  "object-id",
  "open",
  "delete",
  "detail",
  "schema-kind",
  "load-schema",
  "schema-detail",
  "create-section",
  "create-kind",
  "create-json",
  "create",
  "status",
];
const elements = Object.fromEntries(
  ids.map((id) => [id, document.getElementById(id)]),
);
const state = {
  graph: "",
  mode: "",
  vertices: [],
  edges: [],
  vertexPage: null,
  edgePage: null,
  selected: null,
};
const svg = "http://www.w3.org/2000/svg";

function status(message) {
  elements.status.textContent = message;
}
function graphPath(suffix) {
  return `/graphs/${state.graph}/${suffix}`;
}

function objectPath(kind, id) {
  if (!id || id.length > 512 || /[\\/\x00-\x1f]/.test(id)) {
    throw new Error("Enter an ID without a slash or control character.");
  }
  return graphPath(`graph/${kind}/${encodeURIComponent(id)}`);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      result.message || result.detail || `Request failed (${response.status})`,
    );
  }
  return result;
}

async function run(task) {
  try {
    status("Working…");
    await task();
  } catch (error) {
    status(error instanceof Error ? error.message : "Request failed");
  }
}

function svgElement(name, attributes) {
  const node = document.createElementNS(svg, name);
  for (const [key, value] of Object.entries(attributes))
    node.setAttribute(key, String(value));
  return node;
}

function renderDiagram() {
  const edges = state.edges;
  const vertices = new Map(
    state.vertices.map((vertex) => [String(vertex.id), vertex]),
  );
  // Edge pages can reference vertices outside the current vertex page. Draw
  // those endpoints too so a paged preview still shows each relationship.
  for (const edge of edges) {
    for (const endpoint of [edge.outV, edge.inV]) {
      if (endpoint !== undefined && !vertices.has(String(endpoint))) {
        vertices.set(String(endpoint), { id: endpoint });
      }
    }
  }
  const positions = new Map();
  [...vertices.values()].forEach((vertex, index) => {
    const angle = (2 * Math.PI * index) / Math.max(vertices.size, 1);
    positions.set(String(vertex.id), {
      x: 400 + 300 * Math.cos(angle),
      y: 220 + 160 * Math.sin(angle),
    });
  });
  const drawing = document.createDocumentFragment();
  for (const edge of edges) {
    const start = positions.get(String(edge.outV));
    const end = positions.get(String(edge.inV));
    if (!start || !end) continue;
    const line = svgElement("line", {
      x1: start.x,
      y1: start.y,
      x2: end.x,
      y2: end.y,
      stroke: "#718096",
      "stroke-width": 2,
    });
    drawing.append(line);
  }
  for (const vertex of vertices.values()) {
    const point = positions.get(String(vertex.id));
    const group = svgElement("g", {
      tabindex: 0,
      role: "button",
      "aria-label": `Open vertex ${vertex.id}`,
    });
    group.append(
      svgElement("circle", {
        cx: point.x,
        cy: point.y,
        r: 17,
        fill: "#3478b5",
      }),
    );
    const label = svgElement("text", {
      x: point.x,
      y: point.y + 34,
      "text-anchor": "middle",
      fill: "currentColor",
    });
    label.textContent = String(vertex.label || vertex.id).slice(0, 24);
    group.append(label);
    group.addEventListener(
      "click",
      () => void run(() => openObject("vertices", String(vertex.id))),
    );
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        void run(() => openObject("vertices", String(vertex.id)));
      }
    });
    drawing.append(group);
  }
  elements.diagram.replaceChildren(drawing);
}

function renderList(kind, items) {
  const list = elements[kind];
  list.replaceChildren();
  for (const item of items) {
    const entry = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = `${item.label || kind.slice(0, -1)} · ${item.id}`;
    button.addEventListener(
      "click",
      () => void run(() => openObject(kind, String(item.id))),
    );
    entry.append(button);
    list.append(entry);
  }
}

async function loadPage(kind, cursor = null) {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("page", cursor);
  const result = await request(graphPath(`graph/${kind}?${query}`));
  const items = result[kind];
  if (!Array.isArray(items))
    throw new Error(`HugeGraph returned no ${kind} list.`);
  state[kind] = items;
  state[kind === "vertices" ? "vertexPage" : "edgePage"] = result.page || null;
  elements[`next-${kind}`].hidden = !result.page;
  renderList(kind, items);
  renderDiagram();
  status(`Showing ${items.length} ${kind}.`);
}

async function openObject(kind, id) {
  const item = await request(objectPath(kind, id));
  state.selected = { kind, id };
  elements.kind.value = kind;
  elements["object-id"].value = id;
  elements.detail.textContent = JSON.stringify(item, null, 2);
  elements.delete.hidden = state.mode !== "read-write";
  status(`Opened ${kind.slice(0, -1)} ${id}.`);
}

async function deleteSelected() {
  if (
    !state.selected ||
    !window.confirm(
      `Delete ${state.selected.kind.slice(0, -1)} ${state.selected.id}?`,
    )
  )
    return;
  const { kind, id } = state.selected;
  await request(objectPath(kind, id), { method: "DELETE" });
  state.selected = null;
  elements.detail.textContent = "Deleted.";
  elements.delete.hidden = true;
  await loadPage(kind);
  status(`Deleted ${id}.`);
}

async function loadSchema() {
  const kind = elements["schema-kind"].value;
  const result = await request(graphPath(`schema/${kind}`));
  elements["schema-detail"].textContent = JSON.stringify(result, null, 2);
  status(`Loaded ${kind}.`);
}

async function createObject() {
  const value = JSON.parse(elements["create-json"].value);
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error("Enter a JSON object.");
  }
  const collection = elements["create-kind"].value;
  const result = await request(graphPath(collection), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  });
  elements.detail.textContent = JSON.stringify(result, null, 2);
  if (collection.startsWith("graph/")) await loadPage(collection.split("/")[1]);
  else await loadSchema();
  status("Created graph object.");
}

elements.refresh.addEventListener(
  "click",
  () =>
    void run(async () => {
      await loadPage("vertices");
      await loadPage("edges");
    }),
);
for (const kind of ["vertices", "edges"]) {
  elements[`next-${kind}`].addEventListener(
    "click",
    () =>
      void run(() =>
        loadPage(kind, state[kind === "vertices" ? "vertexPage" : "edgePage"]),
      ),
  );
}
elements.open.addEventListener(
  "click",
  () =>
    void run(() =>
      openObject(elements.kind.value, elements["object-id"].value.trim()),
    ),
);
elements.delete.addEventListener("click", () => void run(deleteSelected));
elements["load-schema"].addEventListener("click", () => void run(loadSchema));
elements.create.addEventListener("click", () => void run(createObject));

void run(async () => {
  const config = await request("/__platform/hugegraph/config");
  state.graph = config.graph;
  state.mode = config.mode;
  elements.scope.textContent = `${config.graph} · ${config.mode} lease`;
  elements["create-section"].hidden = config.mode !== "read-write";
  await loadPage("vertices");
  await loadPage("edges");
});
