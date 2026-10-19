// Tests for dashboard/store.js (client of the local server) with an in-memory fake fetch.  node tests/test_store.js
const assert = require('assert');
const Store = require('../dashboard/store.js');

function fake() {
  const db = { runs: [], calls: [], down: false, healthOk: true };
  const res = (status, body) => ({ ok: status < 400, status, text: async () => (body === undefined ? '' : JSON.stringify(body)) });
  db.fn = async (path, init = {}) => {
    db.calls.push({ path, method: init.method || 'GET', body: init.body, headers: init.headers });
    if (db.down) throw new TypeError('connection refused');
    if (path === '/api/health') return db.healthOk ? res(200, { ok: true, version: 1 }) : res(404, { error: 'Not found.' });
    if (path === '/api/runs' && init.method === 'GET') return res(200, { runs: db.runs.map(({ session, ...r }) => r) });
    if (path === '/api/runs' && init.method === 'POST') { const b = JSON.parse(init.body); const r = { id: db.runs.length + 1, created_at: '2026-10-19T00:00:00Z', ...b }; db.runs.unshift(r); return res(201, { run: r }); }
    const m = path.match(/^\/api\/runs\/(\d+)$/);
    if (m) {
      const r = db.runs.find((x) => x.id === +m[1]);
      if (init.method === 'GET') return r ? res(200, { run: r }) : res(404, { error: 'That run no longer exists.' });
      if (init.method === 'DELETE') { if (!r) return res(404, { error: 'That run no longer exists.' }); db.runs = db.runs.filter((x) => x !== r); return res(200, { deleted: r.id }); }
    }
    return res(404, { error: 'Not found.' });
  };
  return db;
}
let n = 0; const t = async (name, fn) => { await fn(); n++; console.log('PASS  ' + name); };

(async () => {
  await t('stays disabled when opened as a file, and never touches the network', async () => {
    const f = fake();
    const s = Store.create({ fetch: f.fn, protocol: 'file:' });
    assert.strictEqual(s.enabled, false); assert.strictEqual(await s.probe(), false);
    assert.strictEqual(f.calls.length, 0);
  });

  await t('probe: true only when a Forward Desk server answers', async () => {
    const f = fake(), s = Store.create({ fetch: f.fn, protocol: 'http:' });
    assert.strictEqual(await s.probe(), true);
    f.healthOk = false; assert.strictEqual(await s.probe(), false);
    f.down = true; assert.strictEqual(await s.probe(), false);
  });

  await t('probe gives up when the server hangs', async () => {
    const s = Store.create({ fetch: (p, init) => new Promise((_, rej) => init.signal.addEventListener('abort', () => rej(new Error('aborted')))), protocol: 'http:', timeout: 30 });
    assert.strictEqual(await s.probe(), false);
  });

  await t('save, list (newest first), get, delete round trip', async () => {
    const f = fake(), s = Store.create({ fetch: f.fn, protocol: 'http:' });
    const a = await s.save({ name: '  Base case  ', instrument: 'USD/SGD', session: { format: 'forward-desk-session' }, summary: { pnl: -1928.13 } });
    assert.strictEqual(a.name, 'Base case');
    await s.save({ name: 'Wide spread', instrument: 'EUR/USD', session: { x: 1 } });
    assert.deepStrictEqual((await s.list()).map((r) => r.name), ['Wide spread', 'Base case']);
    assert.strictEqual((await s.get(a.id)).session.format, 'forward-desk-session');
    await s.remove(a.id); assert.strictEqual((await s.list()).length, 1);
    await assert.rejects(() => s.remove(a.id), /no longer exists/);
    await assert.rejects(() => s.get(a.id), /no longer exists/);
  });

  await t('POST sends JSON (so the server accepts it and cross-site forms cannot)', async () => {
    const f = fake(), s = Store.create({ fetch: f.fn, protocol: 'http:' });
    await s.save({ name: 'x', instrument: 'y', session: {} });
    const c = f.calls.find((x) => x.method === 'POST'); assert.strictEqual(c.headers['Content-Type'], 'application/json');
  });

  await t('inputs are validated before any request is made', async () => {
    const f = fake(), s = Store.create({ fetch: f.fn, protocol: 'http:' });
    await assert.rejects(() => s.save({ name: '   ', instrument: 'x', session: {} }), /name/i);
    await assert.rejects(() => s.get('1; drop table runs'), /valid run id/);
    await assert.rejects(() => s.remove('../../x'), /valid run id/);
    await assert.rejects(() => s.get('-1'), /valid run id/);
    assert.strictEqual(f.calls.length, 0);
  });

  await t('a stopped server gives a readable message; server errors show the server text, not raw HTML', async () => {
    const f = fake(), s = Store.create({ fetch: f.fn, protocol: 'http:' });
    f.down = true; await assert.rejects(() => s.list(), /Could not reach the local server/);
    const bad = Store.create({ fetch: async () => ({ ok: false, status: 500, text: async () => '<html>oops</html>' }), protocol: 'http:' });
    await assert.rejects(() => bad.list(), /refused the request \(500\)/);
    const msg = Store.create({ fetch: async () => ({ ok: false, status: 400, text: async () => JSON.stringify({ error: 'Name is required.' }) }), protocol: 'http:' });
    await assert.rejects(() => msg.save({ name: 'x', instrument: 'y', session: {} }), /Name is required/);
  });

  console.log(`${n} store checks passed`);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
