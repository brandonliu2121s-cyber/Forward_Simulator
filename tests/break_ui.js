// Worst-case ("break the UI") test for dashboard/index.html. Playwright + Chromium.
//   node tests/break_ui.js            # imports tests/fixtures/worst_case_* through the real import dialog, checks every view at 4 widths
//   node tests/break_ui.js --demo     # same checks with the built-in demo data (baseline)
// Reports page-level horizontal scroll and any element that spills out of its card/tile/pill/popover. Exit code 1 if anything is found.
const path = require('path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..');
const DEMO = process.argv.includes('--demo');
const WIDTHS = [1280, 640, 400, 320];            // 640 ~ a 1280px window at 200% browser zoom
const VIEWS = ['Desk', 'Pricing', 'Instruments', 'Activity', 'Setup'];

const detect = () => {
  const out = [], vw = document.documentElement.clientWidth;
  if (document.documentElement.scrollWidth > vw + 1) out.push({ sel: 'PAGE', over: document.documentElement.scrollWidth - vw, text: 'horizontal scroll' });
  const skip = (el) => el.closest('.scroll, .wl, .nav, svg, .tip, .mono-area, .fmt, pre');
  const boxes = '.card, .tile, .wl-item, .pop, .dlg, .kpi, .qbox, .opt, .hero, .chips, .pill, .who, .brand, .prev, .field';
  for (const el of document.querySelectorAll('#app *, #dlg *')) {
    if (skip(el)) continue;
    const r = el.getBoundingClientRect(); if (r.width === 0 || r.height === 0) continue;
    if (r.right > vw + 1) { out.push({ sel: el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0], over: Math.round(r.right - vw), text: (el.textContent || '').trim().slice(0, 28), why: 'past viewport' }); continue; }
    const box = el.parentElement && el.parentElement.closest(boxes); if (!box || box === el) continue;
    const b = box.getBoundingClientRect();
    if (r.right > b.right + 1.5 || r.left < b.left - 1.5) out.push({ sel: el.tagName.toLowerCase() + '.' + String(el.className).split(' ')[0] + ' in ' + box.className.split(' ')[0], over: Math.round(Math.max(r.right - b.right, b.left - r.left)), text: (el.textContent || '').trim().slice(0, 28), why: 'out of its box' });
  }
  return out;
};

const detectSrc = detect.toString();
(async () => {
  const b = await chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});
  const found = new Map(); const errs = [];
  for (const w of WIDTHS) {
    const pg = await b.newPage({ viewport: { width: w, height: 900 } });
    pg.on('pageerror', (e) => errs.push(e.message));
    await pg.addInitScript(`window.detect = ${detectSrc}`);
    await pg.goto('file://' + ROOT + '/dashboard/index.html#desk'); await pg.waitForTimeout(250);
    let names = [];
    if (!DEMO) {
      await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]');
      await pg.setInputFiles('#imp-file', ROOT + '/tests/fixtures/worst_case_library.json'); await pg.waitForTimeout(200); await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(250);
      await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]');
      await pg.setInputFiles('#imp-file', ROOT + '/tests/fixtures/worst_case_scenario.csv'); await pg.waitForTimeout(250); await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(250);
      names = JSON.parse(await pg.evaluate(() => JSON.stringify([...document.querySelectorAll('.wl-item')].map((e) => e.dataset.name)))).slice(-12);
    } else names = ['USD/SGD', 'Brent Crude'];
    for (const name of names) {
      await pg.click('.who'); await pg.waitForTimeout(60);
      for (const f of await pg.evaluate(() => { const o = window.detect(); const pop = document.querySelector('.pop'); if (pop) { const r = pop.getBoundingClientRect(), cs = getComputedStyle(pop); if ((r.bottom > innerHeight + 1 || pop.scrollHeight > pop.clientHeight + 1) && cs.overflowY !== 'auto' && cs.overflowY !== 'scroll') o.push({ sel: 'pop (taller than the viewport, no scroll)', over: Math.round(Math.max(r.bottom - innerHeight, pop.scrollHeight - pop.clientHeight)), text: 'instrument menu' }); } return o; }, 0)) { const k = `${f.sel} | Menu`; const cur = found.get(k) || { n: 0, worst: 0, widths: new Set(), ex: f.text, names: new Set() }; cur.n++; cur.worst = Math.max(cur.worst, f.over); cur.widths.add(w); found.set(k, cur); }
      await pg.evaluate((n) => { [...document.querySelectorAll('.pop .item')].find((e) => e.dataset.name === n).click(); }, name);
      await pg.waitForTimeout(120);
      for (const v of VIEWS) {
        await pg.evaluate((vv) => { [...document.querySelectorAll('.nav button')].find((e) => e.textContent.trim() === vv).click(); }, v); await pg.waitForTimeout(90);
        const flags = await pg.evaluate(detect);
        for (const f of flags) { const k = `${f.sel} | ${v}`; const cur = found.get(k) || { n: 0, worst: 0, widths: new Set(), ex: f.text, names: new Set() }; cur.n++; cur.worst = Math.max(cur.worst, f.over); cur.widths.add(w); cur.names.add(name.slice(0, 18)); found.set(k, cur); }
        if (!DEMO && w === 400 && ['Desk', 'Instruments'].includes(v) && name.startsWith('Singapore')) await pg.screenshot({ path: process.env.SHOTS ? `${process.env.SHOTS}/worst_${v}_${w}.png` : '/dev/null', fullPage: true }).catch(() => {});
      }
    }
    // the front page before any run, and the gate shown on a result tab
    const fresh = await b.newPage({ viewport: { width: w, height: 900 } }); await fresh.addInitScript(`window.detect = ${detectSrc}`);
    await fresh.goto('file://' + ROOT + '/dashboard/index.html'); await fresh.waitForTimeout(200);
    for (const [label, act] of [['Setup (before run)', async () => {}], ['Gate (before run)', async () => { await fresh.click('.nav button:has-text("Desk")'); await fresh.waitForTimeout(80); }]]) {
      await act();
      for (const f of await fresh.evaluate(detect)) { const k = `${f.sel} | ${label}`; const cur = found.get(k) || { n: 0, worst: 0, widths: new Set(), ex: f.text, names: new Set() }; cur.n++; cur.worst = Math.max(cur.worst, f.over); cur.widths.add(w); found.set(k, cur); }
    }
    await fresh.close();
    // the dialog itself with a hostile library loaded
    await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="export"]'); await pg.waitForTimeout(150);
    for (const f of await pg.evaluate(detect)) { const k = `${f.sel} | Dialog`; const cur = found.get(k) || { n: 0, worst: 0, widths: new Set(), ex: f.text, names: new Set() }; cur.n++; cur.worst = Math.max(cur.worst, f.over); cur.widths.add(w); found.set(k, cur); }
    await pg.close();
  }
  // ---- semantic checks (the worst-case values must also be *right*, not just fit)
  const sem = [];
  if (!DEMO) {
    const pg = await b.newPage({ viewport: { width: 1280, height: 900 } }); pg.on('pageerror', (e) => errs.push(e.message));
    await pg.goto('file://' + ROOT + '/dashboard/index.html#desk'); await pg.waitForTimeout(200);
    const loadFile = async (f) => { await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]'); await pg.setInputFiles('#imp-file', ROOT + '/tests/fixtures/' + f); await pg.waitForTimeout(200); const prev = await pg.locator('#imp-prev').innerText(); await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(250); return prev; };
    const libPrev = await loadFile('worst_case_library.json');
    sem.push(['importer says when a name is shortened', /shortened/.test(libPrev)]);
    const pick = async (n) => { await pg.click('.who'); await pg.evaluate((x) => [...document.querySelectorAll('.pop .item')].find((e) => e.dataset.name === x).click(), n); await pg.waitForTimeout(150); };
    await pg.click('.nav button:has-text("Pricing")'); await pick('SHIB/USD');
    const bid = await pg.locator('.qbox .big').first().innerText();
    sem.push([`tiny tick (1e-8) keeps its decimals: bid shows "${bid}"`, /^0\.\d{7,}$/.test(bid.trim())]);
    await pick('\u{1F98A} Fox Oil Futures'); await pg.click('.nav button:has-text("Desk")');
    const badge = await pg.locator('.who .badge').innerText();
    sem.push([`emoji-first name makes a clean badge: "${badge}"`, !badge.includes('�') && badge.length >= 2]);
    // one-step scenario, and exactly one fill => singular
    await pg.click('button[aria-label="Import or export data"]'); await pg.click('button[data-act="dlgtab"][data-k="import"]');
    await pg.fill('#imp-text', 'step,move_sigma,action\n1,0.5,BUY'); await pg.waitForTimeout(150); await pg.click('button[data-act="dlgapply"]'); await pg.waitForTimeout(300);
    const one = await pg.locator('#app').innerText();
    sem.push(['one-step scenario renders (no NaN / undefined)', !/NaN|undefined/.test(one) && (await pg.locator('#plot svg').count()) === 1]);
    sem.push(['singular wording: "1 fill", "1 step"', /\b1 fill\b/.test(one) && /Over 1 step\b/.test(one) && !/\b1 fills\b/.test(one)]);
    for (const v of ['Pricing', 'Instruments', 'Activity', 'Setup']) { await pg.click(`.nav button:has-text("${v}")`); await pg.waitForTimeout(80); }
    sem.push(['every view survives a one-step scenario', true]);
    await pg.close();
  }
  await b.close();
  const rows = [...found.entries()].sort((a, c) => c[1].worst - a[1].worst);
  console.log(`${DEMO ? 'DEMO data' : 'WORST-CASE data'}: ${rows.length} distinct overflow finding(s); page errors: ${JSON.stringify(errs)}`);
  for (const [k, v] of rows) console.log(`  ${k.padEnd(58)} worst +${String(v.worst).padStart(4)}px  widths [${[...v.widths].join(',')}]  e.g. "${v.ex}"`);
  let bad = rows.length || errs.length;
  for (const [label, okk] of sem) { console.log((okk ? 'PASS  ' : 'FAIL  ') + label); if (!okk) bad = 1; }
  process.exit(bad ? 1 : 0);
})();
