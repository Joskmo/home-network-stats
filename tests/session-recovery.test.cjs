const { test } = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { createApi, HttpError } = require("../.build/http.cjs");

test("real HTTP: expiry/restart rotates cookies on GET; stale CSRF fails before save", () => {
  const result = spawnSync(
    process.env.PYTHON || "python3",
    [
      "-c",
      String.raw`
import http.client, json, tempfile, threading
from pathlib import Path
from wsgiref.simple_server import make_server, WSGIRequestHandler
from dashboard.auth import Auth
from dashboard.web import Application
class Quiet(WSGIRequestHandler):
    def log_message(self, *args): pass
class Trusted:
    def identity(self, env): return True
class Store:
    def __init__(self): self.saved = []
    def save(self, graph): self.saved.append(graph); return {'topology':graph}
with tempfile.TemporaryDirectory() as tmp:
    auth = Auth(Path(tmp)/'auth.json', 'fixture-password-only')
    store = Store()
    app = Application(auth, lambda: {'fixture':True}, topology=store, access=Trusted())
    server = make_server('127.0.0.1', 0, app, handler_class=Quiet)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    cookie = ''
    def request(path, payload=None):
        global cookie
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
        headers = {'Cookie':cookie, 'Origin':f'http://127.0.0.1:{server.server_port}'}
        if payload is not None: headers['Content-Type']='application/json'
        conn.request('POST' if payload is not None else 'GET', path,
                     json.dumps(payload) if payload is not None else None, headers)
        response = conn.getresponse()
        cookie = response.getheader('Set-Cookie').split(';')[0]
        data = json.loads(response.read()); status = response.status; conn.close()
        return status, data
    evidence = []
    for mode in ['expiry', 'restart']:
        _, initial = request('/api/session'); old_cookie = cookie
        if mode == 'expiry':
            for session in app.auth.sessions.values(): session['expires'] = 0
        else: app.auth = Auth(Path(tmp)/'auth.json')
        status, _ = request('/api/stats')
        assert status == 200 and cookie != old_cookie
        draft = {'revision':7, 'nodes':[], 'links':[]}
        count = len(store.saved)
        status, error = request('/api/topology', {'topology':draft, 'csrf':initial['csrf']})
        assert status == 403 and error['error'] == 'csrf_failed' and len(store.saved) == count
        _, fresh = request('/api/session')
        assert fresh['authenticated'] and fresh['csrf'] != initial['csrf']
        status, _ = request('/api/topology', {'topology':draft, 'csrf':fresh['csrf']})
        assert status == 200 and store.saved[-1] == draft
        evidence.append({'mode':mode, 'get':200, 'stale_post':403, 'code':error['error'], 'fresh_post':status})
    app.access = None
    _, anonymous = request('/api/session')
    assert not anonymous['authenticated']
    status, error = request('/api/topology', {'topology':draft, 'csrf':anonymous['csrf']})
    assert status == 401 and error['error'] == 'login_required'
    server.shutdown(); server.server_close(); thread.join()
    print(json.dumps(evidence))
`,
    ],
    { cwd: require("node:path").resolve(__dirname, ".."), encoding: "utf8" },
  );
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).length, 2);
});

test("app recovery replaces bridge session without dispatching draft-reloading events", () => {
  const vm = require("node:vm");
  const fs = require("node:fs");
  const { transformSync } = require("esbuild");
  let update;
  const events = [];
  const context = {
    require(id) {
      if (id === "./shared/dom")
        return { $: () => ({ setAttribute() {}, addEventListener() {} }) };
      if (id === "./shared/http")
        return {
          createApi(_session, _language, _translate, callback) {
            update = callback;
            return () => new Promise(() => {});
          },
        };
      if (id === "./app/i18n") return { words: { en: {} } };
      if (id === "./app/rendering") return { createStatsRenderer: () => ({}) };
      throw new Error(id);
    },
    localStorage: { getItem: () => null },
    navigator: { language: "en" },
    document: {
      documentElement: {},
      querySelectorAll: () => [],
      dispatchEvent: (event) => events.push(event.type),
    },
    window: {},
    Event,
    setInterval() {},
  };
  const source = fs.readFileSync(
    require("node:path").join(__dirname, "../frontend/app.ts"),
    "utf8",
  );
  vm.runInNewContext(
    transformSync(source, { loader: "ts", format: "cjs" }).code,
    context,
  );
  assert.equal(typeof update, "function");
  const before = [...events];
  const fresh = { csrf: "fresh", authenticated: false };
  update(fresh);
  assert.equal(context.window.dashboardBridge.session, fresh);
  assert.deepEqual(events, before);
});

test("only topology CSRF rejection is recoverable; retry and refresh failures propagate", async () => {
  const original = global.fetch;
  try {
    const network = new TypeError("network unavailable");
    for (const [path, outcomes, expected, count] of [
      [
        "/api/topology",
        [reply({ error: "topology_conflict" }, 409)],
        "topology_conflict",
        1,
      ],
      ["/api/topology", [network], network, 1],
      [
        "/api/topology",
        [reply({ error: "login_required" }, 401)],
        "login_required",
        1,
      ],
      ["/api/topology", [reply({ error: "forbidden" }, 403)], "forbidden", 1],
      ...[
        "/api/login",
        "/api/password",
        "/api/logout",
        "/api/recover",
        "/api/trusted",
      ].map((path) => [
        path,
        [reply({ error: "csrf_failed" }, 403)],
        "csrf_failed",
        1,
      ]),
      [
        "/api/topology",
        [reply({ error: "csrf_failed" }, 403), network],
        network,
        2,
      ],
      [
        "/api/topology",
        [
          reply({ error: "csrf_failed" }, 403),
          reply({ error: "temporarily_unavailable" }, 503),
        ],
        "temporarily_unavailable",
        2,
      ],
      ...["csrf_failed", "topology_conflict"].map((code) => [
        "/api/topology",
        [
          reply({ error: "csrf_failed" }, 403),
          reply({ authenticated: true, csrf: "fresh" }),
          reply({ error: code }, code === "csrf_failed" ? 403 : 409),
        ],
        code,
        3,
      ]),
      [
        "/api/topology",
        [
          reply({ error: "csrf_failed" }, 403),
          reply({ authenticated: true, csrf: "fresh" }),
          network,
        ],
        network,
        3,
      ],
    ]) {
      let calls = 0;
      global.fetch = async () => {
        const next = outcomes[calls++];
        assert.ok(next, "unexpected request/retry");
        if (next instanceof Error) throw next;
        return next;
      };
      const api = createApi(
        () => ({ csrf: "old" }),
        () => "en",
        (key) => key,
      );
      await assert.rejects(api(path, {}), (error) =>
        typeof expected === "string"
          ? error instanceof HttpError && error.code === expected
          : error === expected,
      );
      assert.equal(calls, count);
    }
  } finally {
    global.fetch = original;
  }
});

const reply = (data, status = 200) =>
  new Response(JSON.stringify(data), { status });

test("expired authorization returns typed actionable errors without retrying or touching draft", async () => {
  const original = global.fetch;
  try {
    for (const [fresh, code, status] of [
      [{ csrf: "fresh", authenticated: false }, "login_required", 401],
      [
        { csrf: "fresh", authenticated: true, must_change: true },
        "password_change_required",
        403,
      ],
      [{ authenticated: true }, "csrf_failed", 403],
    ]) {
      let session = { csrf: "old", authenticated: true };
      const calls = [];
      const draft = { revision: 7, nodes: [], links: [] };
      const before = structuredClone(draft);
      global.fetch = async (url) => {
        calls.push(url);
        return url === "/api/session"
          ? reply(fresh)
          : reply({ error: "csrf_failed" }, 403);
      };
      const api = createApi(
        () => session,
        () => "en",
        (key) => key,
        (value) => {
          session = value;
        },
      );
      await assert.rejects(
        api("/api/topology", { topology: draft }),
        (error) =>
          error instanceof HttpError &&
          error.code === code &&
          error.status === status,
      );
      assert.deepEqual(calls, ["/api/topology", "/api/session"]);
      assert.deepEqual(session, fresh);
      assert.deepEqual(draft, before);
    }
  } finally {
    global.fetch = original;
  }
});

test("topology CSRF recovery updates live session and retries the captured draft once", async () => {
  const original = global.fetch;
  try {
    for (const path of ["/api/topology", "/api/topology/preview"]) {
      let session = { csrf: "old", authenticated: true };
      const draft = { revision: 7, nodes: [{ id: "draft" }], links: [] };
      const snapshot = structuredClone(draft);
      const calls = [];
      global.fetch = async (url, options) => {
        calls.push({ url, options });
        if (calls.length === 1) return reply({ error: "csrf_failed" }, 403);
        if (url === "/api/session") {
          draft.nodes[0].id = "edited-while-refreshing";
          return reply({ csrf: "fresh", authenticated: true });
        }
        return reply({ topology: snapshot });
      };
      const api = createApi(
        () => session,
        () => "en",
        (key) => key,
        (fresh) => {
          session = fresh;
        },
      );
      assert.deepEqual(await api(path, { topology: draft }), {
        topology: snapshot,
      });
      assert.deepEqual(
        calls.map((call) => call.url),
        [path, "/api/session", path],
      );
      assert.equal(session.csrf, "fresh");
      assert.equal(calls[1].options.cache, "no-store");
      assert.deepEqual(JSON.parse(calls[2].options.body), {
        topology: snapshot,
        csrf: "fresh",
      });
      assert.equal(draft.nodes[0].id, "edited-while-refreshing");
    }
  } finally {
    global.fetch = original;
  }
});
