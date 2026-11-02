const elements = Object.fromEntries(
  [
    "scope",
    "refresh",
    "document-id",
    "open",
    "new",
    "documents",
    "next",
    "document-json",
    "save",
    "delete",
    "selector",
    "find",
    "index-section",
    "index-json",
    "create-index",
    "status",
  ].map((id) => [id, document.getElementById(id)]),
);

const state = { database: "", mode: "", current: null, cursor: null };

function status(message) {
  elements.status.textContent = message;
}

function databasePath(suffix) {
  return `/${state.database}/${suffix}`;
}

function documentPath(id) {
  if (
    !id ||
    id.length > 256 ||
    id.startsWith("_") ||
    /[\\/\x00-\x1f]/.test(id)
  ) {
    throw new Error(
      "Enter a document ID without a slash, control character or leading underscore.",
    );
  }
  return databasePath(encodeURIComponent(id));
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(
      result.reason || result.detail || `Request failed (${response.status})`,
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

async function openDocument(id) {
  const document = await request(documentPath(id));
  state.current = document;
  elements["document-id"].value = id;
  elements["document-json"].value = JSON.stringify(document, null, 2);
  elements.delete.disabled = state.mode !== "read-write";
  status(`Opened ${id}`);
}

async function listDocuments(cursor = null) {
  const query = new URLSearchParams({ limit: "51" });
  if (cursor !== null) {
    query.set("startkey", JSON.stringify(cursor));
    query.set("skip", "1");
  }
  const result = await request(databasePath(`_all_docs?${query}`));
  const rows = result.rows.slice(0, 50);
  elements.documents.replaceChildren();
  for (const row of rows) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = row.id;
    button.addEventListener(
      "click",
      () => void run(() => openDocument(row.id)),
    );
    item.append(button);
    elements.documents.append(item);
  }
  state.cursor = result.rows.length > 50 ? rows.at(-1).id : null;
  elements.next.hidden = state.cursor === null;
  status(`Showing ${rows.length} document IDs`);
}

async function saveDocument() {
  const id = elements["document-id"].value.trim();
  const path = documentPath(id);
  const document = JSON.parse(elements["document-json"].value);
  if (!document || Array.isArray(document) || typeof document !== "object") {
    throw new Error("The document must be a JSON object.");
  }
  if (document._id !== undefined && document._id !== id) {
    throw new Error("The document _id must match the selected ID.");
  }
  document._id = id;
  const saved = await request(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(document),
  });
  await openDocument(id);
  status(`Saved ${id} at revision ${saved.rev}`);
}

async function deleteDocument() {
  if (!state.current?._rev) {
    throw new Error("Open a saved document before deleting it.");
  }
  const id = state.current._id;
  if (!window.confirm(`Delete document ${id}?`)) return;
  const query = new URLSearchParams({ rev: state.current._rev });
  await request(`${documentPath(id)}?${query}`, { method: "DELETE" });
  state.current = null;
  elements["document-id"].value = "";
  elements["document-json"].value = "{}";
  elements.delete.disabled = true;
  await listDocuments();
  status(`Deleted ${id}`);
}

async function findDocuments() {
  const selector = JSON.parse(elements.selector.value);
  if (!selector || Array.isArray(selector) || typeof selector !== "object") {
    throw new Error("The selector must be a JSON object.");
  }
  const result = await request(databasePath("_find"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selector, limit: 50 }),
  });
  elements.documents.replaceChildren();
  for (const found of result.docs) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = found._id;
    button.addEventListener(
      "click",
      () => void run(() => openDocument(found._id)),
    );
    item.append(button);
    elements.documents.append(item);
  }
  elements.next.hidden = true;
  status(`Found ${result.docs.length} documents`);
}

async function createIndex() {
  const definition = JSON.parse(elements["index-json"].value);
  const result = await request(databasePath("_index"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(definition),
  });
  status(`Index ${result.name} ${result.result}`);
}

async function initialize() {
  const config = await request("/__platform/couchdb/config");
  state.database = config.database;
  state.mode = config.mode;
  elements.scope.textContent = `${config.database} · ${config.mode} · active human lease`;
  const writer = config.mode === "read-write";
  elements.save.disabled = !writer;
  elements.delete.disabled = true;
  elements["document-json"].readOnly = !writer;
  elements["index-section"].hidden = !writer;
  await listDocuments();
}

elements.refresh.addEventListener(
  "click",
  () => void run(() => listDocuments()),
);
elements.next.addEventListener(
  "click",
  () => void run(() => listDocuments(state.cursor)),
);
elements.open.addEventListener(
  "click",
  () => void run(() => openDocument(elements["document-id"].value.trim())),
);
elements.new.addEventListener("click", () => {
  state.current = null;
  elements["document-id"].value = "";
  elements["document-json"].value = "{}";
  elements.delete.disabled = true;
  elements["document-id"].focus();
  status("Enter a new document ID and JSON object.");
});
elements.save.addEventListener("click", () => void run(saveDocument));
elements.delete.addEventListener("click", () => void run(deleteDocument));
elements.find.addEventListener("click", () => void run(findDocuments));
elements["create-index"].addEventListener("click", () => void run(createIndex));
void run(initialize);
