/* Forward Desk saved runs: a small client for the optional local server (server/app.py).
   The server keeps runs in a SQLite file on this machine. The dashboard only talks to it when the page itself was served by that
   server (same origin); opened as a plain file, or from the published artifact, probe() reports false and the page stays static. */
const Store = (() => {
  class StoreError extends Error { constructor(msg, status) { super(msg); this.name = 'StoreError'; this.status = status || 0; } }
  const ID = /^\d{1,12}$/;

  function create(deps) {
    deps = deps || {};
    const fetchFn = deps.fetch || (typeof fetch !== 'undefined' ? fetch.bind(globalThis) : null);
    const proto = 'protocol' in deps ? deps.protocol : (typeof location !== 'undefined' ? location.protocol : '');
    const timeout = deps.timeout || 1500;
    if (!fetchFn || !/^https?:$/.test(proto)) return { enabled: false, probe: async () => false };

    async function call(path, method, body) {
      let res;
      try {
        res = await fetchFn(path, { method, headers: body === undefined ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
      } catch (_) { throw new StoreError('Could not reach the local server. Is it still running?'); }
      let data = null;
      try { const t = await res.text(); data = t ? JSON.parse(t) : null; } catch (_) { data = null; }
      if (!res.ok) throw new StoreError(data && typeof data.error === 'string' ? data.error.slice(0, 200) : 'The server refused the request (' + res.status + ').', res.status);
      return data || {};
    }
    const idOk = (id) => { if (!ID.test(String(id))) throw new StoreError('That is not a valid run id.'); return String(id); };

    return {
      enabled: true,
      /* true when a Forward Desk server answers on this origin */
      async probe() {
        const ctl = typeof AbortController !== 'undefined' ? new AbortController() : null;
        const timer = ctl ? setTimeout(() => ctl.abort(), timeout) : null;
        try {
          const res = await fetchFn('/api/health', ctl ? { signal: ctl.signal } : {});
          const d = res.ok ? JSON.parse(await res.text()) : null;
          return !!(d && d.ok === true);
        } catch (_) { return false; } finally { if (timer) clearTimeout(timer); }
      },
      async list() { const d = await call('/api/runs', 'GET'); return Array.isArray(d.runs) ? d.runs : []; },
      async save(run) {
        const name = String(run.name || '').trim().slice(0, 80);
        if (!name) throw new StoreError('Give the run a name.');
        const d = await call('/api/runs', 'POST', { name, instrument: String(run.instrument).slice(0, 80), session: run.session, summary: run.summary || {} });
        if (!d.run) throw new StoreError('The run was not saved.');
        return d.run;
      },
      async get(id) { const d = await call('/api/runs/' + idOk(id), 'GET'); if (!d.run) throw new StoreError('That run no longer exists.'); return d.run; },
      async remove(id) { await call('/api/runs/' + idOk(id), 'DELETE'); },
    };
  }
  return { create, StoreError };
})();
if (typeof module !== 'undefined') module.exports = Store;
