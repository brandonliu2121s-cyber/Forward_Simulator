/* Forward Desk persistence: saved runs in Supabase (Postgres), no library and no server of our own.
   - Auth: Supabase magic link (email one-time link). The session lives in localStorage; it is refreshed shortly before it expires.
   - Data: PostgREST over fetch. Row-level security (supabase/migrations/0001_init.sql) limits every row to its owner, so the
     public URL and publishable key in the page are safe to ship.
   - With no config the store reports { enabled: false } and the dashboard behaves as a plain static page. */
const Store = (() => {
  const KEY = 'forward-desk-auth';
  const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  class StoreError extends Error { constructor(msg, status) { super(msg); this.name = 'StoreError'; this.status = status || 0; } }

  function safeStorage() { try { const s = globalThis.localStorage; s.getItem('x'); return s; } catch (_) { return null; } }
  function b64json(part) {
    const bin = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '='));
    return JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, (c) => c.charCodeAt(0))));
  }
  const goodUrl = (u) => /^https:\/\/[a-z0-9-]+\.supabase\.(co|in)\/?$/i.test(u) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/?$/i.test(u);

  function create(cfg, deps) {
    deps = deps || {};
    const fetchFn = deps.fetch || (typeof fetch !== 'undefined' ? fetch.bind(globalThis) : null);
    const storage = 'storage' in deps ? deps.storage : safeStorage();
    const now = deps.now || (() => Date.now());
    if (!cfg || typeof cfg.url !== 'string' || typeof cfg.key !== 'string' || !cfg.key || !goodUrl(cfg.url) || !fetchFn) return { enabled: false };
    const base = cfg.url.replace(/\/+$/, '');
    let session = null;
    try { const raw = storage && storage.getItem(KEY); if (raw) session = JSON.parse(raw); } catch (_) { session = null; }
    if (!session || !session.access_token || !session.user) session = null;
    const persist = () => { try { if (storage) { if (session) storage.setItem(KEY, JSON.stringify(session)); else storage.removeItem(KEY); } } catch (_) { /* private mode */ } };

    async function raw(path, opt) {
      opt = opt || {};
      const headers = Object.assign({ apikey: cfg.key, Authorization: 'Bearer ' + (opt.token || cfg.key) }, opt.headers || {});
      if (opt.body !== undefined) headers['Content-Type'] = 'application/json';
      let res;
      try { res = await fetchFn(base + path, { method: opt.method || 'GET', headers, body: opt.body === undefined ? undefined : JSON.stringify(opt.body) }); }
      catch (_) { throw new StoreError('Could not reach the database. Check your connection and try again.'); }
      let data = null;
      try { const t = await res.text(); data = t ? JSON.parse(t) : null; } catch (_) { data = null; }
      if (!res.ok) {
        const m = data && (data.msg || data.message || data.error_description || data.error);
        throw new StoreError(typeof m === 'string' && m ? m.slice(0, 200) : 'The database refused the request (' + res.status + ').', res.status);
      }
      return data;
    }

    async function refresh() {
      if (!session || !session.refresh_token) throw new StoreError('Please sign in again.', 401);
      let d;
      try { d = await raw('/auth/v1/token?grant_type=refresh_token', { method: 'POST', body: { refresh_token: session.refresh_token } }); }
      catch (e) { if (e.status === 400 || e.status === 401) { session = null; persist(); throw new StoreError('Your sign-in expired. Please sign in again.', 401); } throw e; }
      session = fromTokens(d);
      persist();
    }
    function fromTokens(d) {
      let claims = {};
      try { claims = b64json(String(d.access_token).split('.')[1]); } catch (_) { throw new StoreError('Unexpected sign-in response.'); }
      if (!claims.sub) throw new StoreError('Unexpected sign-in response.');
      const exp = d.expires_at ? +d.expires_at : (claims.exp ? +claims.exp : Math.floor(now() / 1000) + (+d.expires_in || 3600));
      return { access_token: d.access_token, refresh_token: d.refresh_token || '', expires_at: exp, user: { id: claims.sub, email: String(claims.email || (d.user && d.user.email) || '') } };
    }
    async function authed(path, opt) {
      if (!session) throw new StoreError('Please sign in first.', 401);
      if (session.expires_at - now() / 1000 < 60) await refresh();
      try { return await raw(path, Object.assign({ token: session.access_token }, opt)); }
      catch (e) {
        if (e.status !== 401 || !session) throw e;
        await refresh();                                  // token rejected: refresh once, then retry
        return raw(path, Object.assign({ token: session.access_token }, opt));
      }
    }
    const rows = (d) => (Array.isArray(d) ? d : []);
    const idOk = (id) => { if (!UUID.test(String(id))) throw new StoreError('That is not a valid run id.'); return String(id); };

    return {
      enabled: true,
      user: () => (session ? session.user : null),
      async signInWithEmail(email, redirectTo) {
        email = String(email || '').trim();
        if (!EMAIL.test(email) || email.length > 254) throw new StoreError('Enter a valid email address.');
        await raw('/auth/v1/otp' + (redirectTo ? '?redirect_to=' + encodeURIComponent(redirectTo) : ''), { method: 'POST', body: { email, create_user: true } });
      },
      /* Call once on load with location.hash. -> null (nothing to do) | { ok: true } | { ok: false, error } */
      consumeRedirect(hash) {
        const p = new URLSearchParams(String(hash || '').replace(/^#/, ''));
        if (p.get('error_description') || p.get('error')) return { ok: false, error: (p.get('error_description') || p.get('error')).replace(/\+/g, ' ').slice(0, 200) };
        if (!p.get('access_token')) return null;
        try { session = fromTokens({ access_token: p.get('access_token'), refresh_token: p.get('refresh_token'), expires_in: p.get('expires_in'), expires_at: p.get('expires_at') }); }
        catch (e) { return { ok: false, error: e.message }; }
        persist();
        return { ok: true };
      },
      async signOut() {
        const t = session && session.access_token;
        session = null; persist();
        if (t) { try { await raw('/auth/v1/logout', { method: 'POST', token: t }); } catch (_) { /* already signed out locally */ } }
      },
      async list() {
        return rows(await authed('/rest/v1/runs?select=id,name,instrument,created_at,summary&order=created_at.desc&limit=50'));
      },
      async save(run) {
        const name = String(run.name || '').trim().slice(0, 80);
        if (!name) throw new StoreError('Give the run a name.');
        const d = await authed('/rest/v1/runs', { method: 'POST', headers: { Prefer: 'return=representation' },
          body: { name, instrument: String(run.instrument).slice(0, 80), session: run.session, summary: run.summary || {} } });
        const r = rows(d)[0];
        if (!r) throw new StoreError('The run was not saved.');
        return r;
      },
      async get(id) {
        const r = rows(await authed('/rest/v1/runs?id=eq.' + idOk(id) + '&select=id,name,instrument,session'))[0];
        if (!r) throw new StoreError('That run no longer exists.');
        return r;
      },
      async remove(id) {
        const d = rows(await authed('/rest/v1/runs?id=eq.' + idOk(id), { method: 'DELETE', headers: { Prefer: 'return=representation' } }));
        if (!d.length) throw new StoreError('That run no longer exists.');
      },
    };
  }
  return { create, StoreError, goodUrl };
})();
if (typeof module !== 'undefined') module.exports = Store;
