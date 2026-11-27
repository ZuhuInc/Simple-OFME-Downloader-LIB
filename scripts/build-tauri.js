/**
 * Fanta OFME Downloader - Signed Tauri Build Wrapper
 *
 * Automatically loads `%USERPROFILE%\.tauri\fanta-ofme.key` into
 * `TAURI_SIGNING_PRIVATE_KEY` (when not already set in env) and runs `tauri build`
 * so `.sig` updater artifacts are generated cleanly.
 */

const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const ROOT_DIR = path.resolve(__dirname, '..');

function main() {
  const env = { ...process.env };
  const keyCandidates = [
    path.join(os.homedir(), 'Documents', 'ZuhuProjects', 'ZuhuOFME', 'fanta-ofme.key'),
    path.join(os.homedir(), '.tauri', 'fanta-ofme.key')
  ];
  const foundKeyPath = keyCandidates.find((p) => fs.existsSync(p));

  if (!env.TAURI_SIGNING_PRIVATE_KEY && foundKeyPath) {
    env.TAURI_SIGNING_PRIVATE_KEY = fs.readFileSync(foundKeyPath, 'utf8').trim();
    if (env.TAURI_SIGNING_PRIVATE_KEY_PASSWORD === undefined) {
      env.TAURI_SIGNING_PRIVATE_KEY_PASSWORD = '';
    }
    console.log(`[Build Tauri] Loaded signing key from: ${foundKeyPath}`);
  } else if (!env.TAURI_SIGNING_PRIVATE_KEY) {
    console.warn('[Build Tauri] Warning: TAURI_SIGNING_PRIVATE_KEY not set and no fanta-ofme.key found.');
  }

  const extraArgs = process.argv.slice(2);
  const cmd = process.platform === 'win32' ? 'npx.cmd' : 'npx';
  const result = spawnSync(cmd, ['tauri', 'build', ...extraArgs], {
    cwd: ROOT_DIR,
    stdio: 'inherit',
    shell: true,
    env
  });

  process.exit(result.status ?? 1);
}

main();
