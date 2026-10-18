// Node harness: runs dashboard/engine.js over every instrument and prints JSON rows (compared to Python in test_dashboard_engine.py).
const fs = require('fs');
const Engine = require('../dashboard/engine.js');
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
for (const inst of data.instruments) {
  const p = Object.assign({}, inst.params, data.globals);
  out[inst.name] = Engine.simulate(data.scenario.zs, data.scenario.actions, p);
}
process.stdout.write(JSON.stringify(out));
