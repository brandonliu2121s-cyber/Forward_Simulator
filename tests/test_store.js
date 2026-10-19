// Tests for dashboard/store.js against an in-memory fake of Supabase auth + PostgREST (no network).  node tests/test_store.js
const assert = require('assert');
const Store = require('../dashboard/store.js');

const BASE = 'https://abcdefghij.supabase.co', KEY = 'sb_publishable_test';
const UID = '11111111-2222-4333-8444-555555555555';
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
const jwt = (o) => `${b64({ alg: 'HS256' })}.${b64(o)}.sig`;
let clock = 1_700_000_000_000;

function fake({ rejectFirstToken = false } = {}) {
  const db = { runs: [], calls: [], otps: [], tokenGen: 0, expireNext: false, uid: UID };
  const tokens = () => { db.tokenGen++; return { access_token: jwt({ sub: db.uid, email: 'me@example.com', exp: Math.floor(clock / 1000) + 3600 }), refresh_token: 'r' + db.tokenGen, expires_in: 3600 }; };
  let first = rejectFirstToken;
  const res = (status, body) => ({ ok: status < 400, status, text: async () => (body === undefined ? '' : JSON.stringify(body)) });
  const fn = async (url, init) => {
    const u = new URL(url), path = u.pathname, method = init.method, h = init.headers, body = init.body ? JSON.parse(init.body) : undefined;
    db.calls.push({ method, path, search: u.search, h, body });
    assert.strictEqual(h.apikey, KEY);
    if (path === '/auth/v1/otp') { db.otps.push({ ...body, redirect: u.searchParams.get('redirect_to') }); return res(200, {}); }
    if (path === '/auth/v1/logout') return res(204);
    if (path === '/auth/v1/token') { if (body.refresh_token === 'bad') return res(400, { error_description: 'Invalid Refresh Token' }); return res(200, tokens()); }
    if (path.startsWith('/rest/v1/runs')) {
      if (h.Authorization === 'Bearer ' + KEY) return res(401, { message: 'JWT required' });       // the publishable key alone never reads runs
      if (first) { first = false; return res(401, { message: 'JWT expired' }); }
      const mine = db.runs.filter((r) => r.owner === db.uid);
      const id = u.searchParams.get('id');
      if (method === 'GET') return res(200, (id ? mine.filter((r) => 'eq.' + r.id === id) : mine).map((r) => ({ ...r })));
      if (method === 'POST') { const r = { id: '99999999-0000-4000-8000-' + String(db.runs.length).padStart(12, '0'), owner: db.uid, created_at: new Date(clock).toISOString(), ...body }; db.runs.unshift(r); return res(201, [r]); }
      if (method === 'DELETE') { const gone = mine.filter((r) => 'eq.' + r.id === id); db.runs = db.runs.filter((r) => !gone.includes(r)); return res(200, gone); }
    }
    return res(404, { message: 'no route' });
  };
  return { db, fn };
}
const mem = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k), m }; };
const make = (f, storage, extra) => Store.create({ url: BASE, key: KEY }, Object.assign({ fetch: f.fn, storage, now: () => clock }, extra));
const hash = (f) => { const t = f.db; return '#' + new URLSearchParams({ access_token: jwt({ sub: UID, email: 'me@example.com', exp: Math.floor(clock / 1000) + 3600 }), refresh_token: 'rt', expires_in: '3600', token_type: 'bearer', type: 'magiclink' }).toString(); };
let n = 0; const t = async (name, fn) => { await fn(); n++; console.log('PASS  ' + name); };

(async () => {
  await t('no config, a bad URL, or a secret-looking host leaves the page static', () => {
    assert.strictEqual(Store.create(null).enabled, false);
    assert.strictEqual(Store.create({ url: 'http://evil.example.com', key: KEY }, { fetch: fake().fn }).enabled, false);
    assert.strictEqual(Store.create({ url: URL, key: '' }, { fetch: fake().fn }).enabled, false);
    assert.strictEqual(Store.create({ url: BASE, key: KEY }, { fetch: null, storage: null }).enabled === true, typeof fetch === 'function');
    assert.strictEqual(Store.goodUrl('http://localhost:54321'), true);
  });

  await t('magic link: validates the email, posts the otp request with the redirect', async () => {
    const f = fake(), s = make(f, mem());
    await assert.rejects(() => s.signInWithEmail('nope'), /valid email/);
    await s.signInWithEmail(' me@example.com ', 'https://me.github.io/forward/');
    assert.deepStrictEqual(f.db.otps, [{ email: 'me@example.com', create_user: true, redirect: 'https://me.github.io/forward/' }]);
  });

  await t('redirect hash signs in, persists, and is ignored when absent', () => {
    const f = fake(), st = mem(), s = make(f, st);
    assert.strictEqual(s.consumeRedirect('#desk'), null);
    assert.deepStrictEqual(s.consumeRedirect(hash(f)), { ok: true });
    assert.strictEqual(s.user().email, 'me@example.com'); assert.strictEqual(s.user().id, UID);
    const s2 = make(f, st); assert.strictEqual(s2.user().id, UID);                    // survives a reload
  });

  await t('an auth error in the redirect is reported, not thrown', () => {
    const s = make(fake(), mem());
    const r = s.consumeRedirect('#error=access_denied&error_description=Email+link+is+invalid+or+has+expired');
    assert.deepStrictEqual(r, { ok: false, error: 'Email link is invalid or has expired' }); assert.strictEqual(s.user(), null);
  });

  await t('signed-out reads are refused locally; the publishable key never reaches the runs table as a user', async () => {
    const f = fake(), s = make(f, mem());
    await assert.rejects(() => s.list(), /sign in/i);
    assert.strictEqual(f.db.calls.length, 0);
  });

  await t('save, list (newest first), get, delete round trip', async () => {
    const f = fake(), s = make(f, mem()); s.consumeRedirect(hash(f));
    const a = await s.save({ name: '  Base case  ', instrument: 'USD/SGD', session: { format: 'forward-desk-session' }, summary: { pnl: -1928.13 } });
    assert.strictEqual(a.name, 'Base case');
    await s.save({ name: 'Wide spread', instrument: 'EUR/USD', session: { x: 1 } });
    const list = await s.list(); assert.deepStrictEqual(list.map((r) => r.name), ['Wide spread', 'Base case']);
    assert.ok(/order=created_at\.desc/.test(f.db.calls.find((c) => c.method === 'GET').search));
    assert.strictEqual((await s.get(a.id)).session.format, 'forward-desk-session');
    await s.remove(a.id); assert.strictEqual((await s.list()).length, 1);
    await assert.rejects(() => s.remove(a.id), /no longer exists/);
    await assert.rejects(() => s.get(a.id), /no longer exists/);
  });

  await t('inputs are validated before any request is made', async () => {
    const f = fake(), s = make(f, mem()); s.consumeRedirect(hash(f)); const before = f.db.calls.length;
    await assert.rejects(() => s.save({ name: '   ', instrument: 'x', session: {} }), /name/i);
    await assert.rejects(() => s.get('1; drop table runs'), /valid run id/);
    await assert.rejects(() => s.remove('../../x'), /valid run id/);
    assert.strictEqual(f.db.calls.length, before);
  });

  await t('another user cannot see or delete these rows (the fake mimics row-level security)', async () => {
    const f = fake(), s = make(f, mem()); s.consumeRedirect(hash(f));
    const a = await s.save({ name: 'Mine', instrument: 'USD/SGD', session: {} });
    f.db.uid = '22222222-2222-4222-8222-222222222222';
    const s2 = make(f, mem()); s2.consumeRedirect(hash(f)); 
    assert.deepStrictEqual(await s2.list(), []);
    await assert.rejects(() => s2.get(a.id), /no longer exists/);
    await assert.rejects(() => s2.remove(a.id), /no longer exists/);
  });

  await t('an expiring token is refreshed before the call; a rejected token is refreshed once and retried', async () => {
    const f = fake(), s = make(f, mem()); s.consumeRedirect(hash(f));
    clock += 3600 * 1000 - 30 * 1000;                                               // 30 s left
    await s.list(); assert.ok(f.db.calls.some((c) => c.path === '/auth/v1/token'));
    const g = fake({ rejectFirstToken: true }), s3 = make(g, mem()); s3.consumeRedirect(hash(g));
    await s3.list(); assert.strictEqual(g.db.calls.filter((c) => c.path === '/auth/v1/token').length, 1);
  });

  await t('a dead refresh token signs the user out with a clear message', async () => {
    const f = fake(), st = mem(), s = make(f, st); s.consumeRedirect('#' + new URLSearchParams({ access_token: jwt({ sub: UID, email: 'e@x.co', exp: 1 }), refresh_token: 'bad', expires_in: '1' }));
    clock += 10 * 3600 * 1000;
    await assert.rejects(() => s.list(), /sign in again/i);
    assert.strictEqual(s.user(), null); assert.strictEqual(st.getItem('forward-desk-auth'), null);
  });

  await t('sign out clears the stored session even if the network call fails', async () => {
    const f = fake(), st = mem(), s = make(f, st); s.consumeRedirect(hash(f));
    const down = Store.create({ url: BASE, key: KEY }, { fetch: async () => { throw new TypeError('offline'); }, storage: st, now: () => clock });
    assert.ok(down.user()); await down.signOut(); assert.strictEqual(down.user(), null); assert.strictEqual(st.getItem('forward-desk-auth'), null);
  });

  await t('network failures and server errors become readable messages', async () => {
    const f = fake(), s = Store.create({ url: BASE, key: KEY }, { fetch: async () => { throw new TypeError('offline'); }, storage: mem(), now: () => clock });
    await assert.rejects(() => s.signInWithEmail('me@example.com'), /Could not reach the database/);
    const bad = Store.create({ url: BASE, key: KEY }, { fetch: async () => ({ ok: false, status: 500, text: async () => '<html>oops</html>' }), storage: mem(), now: () => clock });
    await assert.rejects(() => bad.signInWithEmail('me@example.com'), /refused the request \(500\)/);
  });

  await t('works with no localStorage (private mode)', async () => {
    const f = fake(), s = make(f, null); s.consumeRedirect(hash(f)); assert.strictEqual((await s.list()).length, 0);
  });

  console.log(`${n} store checks passed`);
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
