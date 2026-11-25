/**
 * Local Mock Update Server for testing Stable vs Beta update channels
 * without publishing a real GitHub Release.
 *
 * Usage:
 *   node scripts/mock-update-server.js [beta_version]
 *   Default beta_version: 2.5.0-beta.1
 *
 * Expects gitignored `dev-app-update.yml` in the repo root pointing to
 * http://127.0.0.1:8787 (provider: generic).
 */

const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8787;
const HOST = '127.0.0.1';
const pkgPath = path.resolve(__dirname, '..', 'package.json');
const pkgVersion = JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version || '2.1.6';
const betaVersion = (process.argv[2] || '2.5.0-beta.1').trim().replace(/^v/i, '');

function buildYml(version) {
  const installerName = `Fanta-OFME-Downloader-Setup-${version}.exe`;
  const fakeSha512 = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==';
  return [
    `version: ${version}`,
    `files:`,
    `  - url: ${installerName}`,
    `    sha512: ${fakeSha512}`,
    `    size: 104857600`,
    `path: ${installerName}`,
    `sha512: ${fakeSha512}`,
    `releaseDate: '${new Date().toISOString()}'`,
    ''
  ].join('\n');
}

const server = http.createServer((req, res) => {
  const reqPath = (req.url || '/').split('?')[0];

  if (reqPath === '/latest.yml') {
    console.log(`[MockUpdater] ${req.method} ${reqPath} -> serving Stable v${pkgVersion}`);
    res.writeHead(200, { 'Content-Type': 'text/yaml; charset=utf-8' });
    res.end(buildYml(pkgVersion));
    return;
  }

  if (reqPath === '/beta.yml') {
    console.log(`[MockUpdater] ${req.method} ${reqPath} -> serving Beta v${betaVersion}`);
    res.writeHead(200, { 'Content-Type': 'text/yaml; charset=utf-8' });
    res.end(buildYml(betaVersion));
    return;
  }

  console.log(`[MockUpdater] ${req.method} ${reqPath} -> 404 Not Found`);
  res.writeHead(404, { 'Content-Type': 'text/plain' });
  res.end('Not found');
});

server.listen(PORT, HOST, () => {
  console.log(`[MockUpdater] Listening on http://${HOST}:${PORT}`);
  console.log(`[MockUpdater]   /latest.yml -> v${pkgVersion} (Stable)`);
  console.log(`[MockUpdater]   /beta.yml   -> v${betaVersion} (Beta)`);
  console.log('[MockUpdater] Start the app with `npm start` and toggle "Receive Beta Updates" in Settings.');
});
