const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
for (const [pkg, target] of [['leaflet', 'leaflet'], ['leaflet.markercluster', 'markercluster']]) {
  fs.cpSync(path.join(root, 'node_modules', pkg, 'dist'), path.join(root, 'vendor', target), { recursive: true });
  const license = path.join(root, 'node_modules', pkg, 'LICENSE');
  if (fs.existsSync(license)) fs.copyFileSync(license, path.join(root, 'vendor', target, 'LICENSE'));
}
