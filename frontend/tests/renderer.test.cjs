const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const source = fs.readFileSync(path.join(__dirname, '../index.html'), 'utf8');

function page() {
  const dom = new JSDOM(source, { runScripts: 'outside-only', url: 'http://127.0.0.1:8000/' });
  const win = dom.window;
  const layer = () => ({ addTo() { return this; }, clearLayers() {}, addLayer() {}, bindPopup() { return this; },
    openPopup() {}, setView() {}, fitBounds() {}, setStyle() {} });
  win.L = { map: layer, tileLayer: layer, markerClusterGroup: layer, layerGroup: layer, circleMarker: layer,
    divIcon: x => x, marker: layer, polyline: layer };
  win.fetch = async () => ({ ok: true, json: async () => ({ results: [] }) });
  win.Headers = Headers;
  win.TextEncoder = TextEncoder;
  win.setInterval = () => 0;
  win.setTimeout = () => 0;
  win.eval(source.match(/<script>([\s\S]*?)<\/script>/)[1] + '\nwindow.S=S;');
  return win;
}

test('student data cannot create HTML or events', () => {
  const win = page();
  win.eval(`renderPaxPreview({passengers:[{name:'<img src=x onerror=alert(1)>',address:'\" onmouseover=alert(1) x=\"',passenger_count:1,geocoded:true}],total:1,success:1,failed:0},'test.xlsx')`);
  assert.equal(win.document.querySelector('#paxPreview img'), null);
  assert.equal(win.document.querySelector('#paxPreview [onmouseover]'), null);
  assert.match(win.document.querySelector('#paxPreview').textContent, /<img/);
  win.close();
});

test('changing address text clears previously selected coordinates and routes', () => {
  const win = page();
  win.eval(`S.routes=[{}]; S.addrSearches.destAddrWrap.selected={lat:37,lng:127};S.addrSearches.destAddrWrap._onInput('new address')`);
  assert.equal(win.eval('S.addrSearches.destAddrWrap.getValue()'), null);
  assert.equal(win.eval('S.routes'), null);
  win.close();
});

test('bus IDs cannot inject JavaScript into event attributes', () => {
  const win = page();
  win.eval(`S.vehicles=[{bus_id:"x');alert(1);//",capacity:21,start_location:'<b>x</b>',start_lat:37,start_lng:127}];renderVList()`);
  assert.equal(win.document.querySelector('.btn-edit').getAttribute('onclick'), 'startEdit(S.vehicles[0].bus_id)');
  assert.equal(win.document.querySelector('.v-detail b'), null);
  win.close();
});

test('editing limits invalidates the saved result', () => {
  const win = page();
  win.eval('S.routes=[{}]');
  win.document.getElementById('maxRide').dispatchEvent(new win.Event('input'));
  assert.equal(win.eval('S.routes'), null);
  assert.equal(win.eval('readOptions().max_ride_min'), 90);
  win.close();
});

test('failed geocoding blocks route creation instead of dropping students', async () => {
  const win = page();
  await win.eval('S.failedRows=1;S.passengers=[{}];generateRoutes()');
  assert.equal(win.eval('S.jobId'), null);
  assert.match(win.document.querySelector('.toast').textContent, /주소 확인 실패/);
  win.close();
});

test('renderer does not have Node access and vendor scripts are local', () => {
  const main = fs.readFileSync(path.join(__dirname, '../src/main.js'), 'utf8');
  assert.match(main, /nodeIntegration: false/);
  assert.match(main, /contextIsolation: true/);
  assert.match(main, /webSecurity: true/);
  assert.doesNotMatch(source, /require\(['"]electron/);
  assert.doesNotMatch(source, /<script src="https:/);
});
