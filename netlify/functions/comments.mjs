// Public comments backend for the FDCA dashboard (OUTPUT/index.html).
// GET  -> the whole comment store: { companies: {name: [comment]}, categories: {slug: [comment]} }
// POST -> { target: "company"|"category", key, text } appends one comment.
// Storage is a single Netlify Blob (store "comments", key "store") — no
// external service or API key needed; Netlify Blobs is native to the site.
import { getStore } from "@netlify/blobs";

const MAX_LEN = 500;
const EMPTY_STORE = { companies: {}, categories: {} };

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export default async (req) => {
  const store = getStore("comments");

  if (req.method === "GET") {
    const data = (await store.get("store", { type: "json" })) || EMPTY_STORE;
    return json(data);
  }

  if (req.method === "POST") {
    let body;
    try {
      body = await req.json();
    } catch {
      return json({ error: "invalid JSON body" }, 400);
    }
    const { target, key, text } = body || {};
    if (target !== "company" && target !== "category") {
      return json({ error: "target must be 'company' or 'category'" }, 400);
    }
    if (typeof key !== "string" || !key.trim()) {
      return json({ error: "key is required" }, 400);
    }
    const clean = typeof text === "string" ? text.trim() : "";
    if (!clean) return json({ error: "text is required" }, 400);
    if (clean.length > MAX_LEN) {
      return json({ error: `text must be ${MAX_LEN} characters or fewer` }, 400);
    }

    const bucket = target === "company" ? "companies" : "categories";
    const comment = { id: crypto.randomUUID(), text: clean, ts: Date.now() };

    // Simple get-then-set, no distributed lock. This is an internal member
    // directory, not a high-traffic public forum — a lost update from two
    // simultaneous posts to the SAME company/category is an acceptable,
    // rare risk here, not worth the added complexity.
    const data = (await store.get("store", { type: "json" })) || {
      companies: {},
      categories: {},
    };
    if (!data[bucket][key]) data[bucket][key] = [];
    data[bucket][key].push(comment);
    await store.setJSON("store", data);

    return json({ comment, list: data[bucket][key] }, 201);
  }

  return json({ error: "method not allowed" }, 405);
};
