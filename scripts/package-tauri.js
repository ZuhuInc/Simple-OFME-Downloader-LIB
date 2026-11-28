/**
 * Fanta OFME Downloader - Tauri Release Packager
 *
 * Packages compiled Tauri v2 outputs into release-ready folders matching
 * Electron's `build/Installer/` and `build/File/` layout:
 *   - build/Tauri/Installer/
 *       - Fanta-OFME-Downloader-Setup-<version>.exe
 *       - latest.json (for Tauri signed in-app auto-updates)
 *       - latest.yml  (for Electron v2.1.7 -> Tauri prerelease upgrades)
 *   - build/Tauri/File/
 *       - Fanta-OFME-Downloader-Portable-<version>.exe (single standalone runnable exe)
 */

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');

const ROOT_DIR = path.resolve(__dirname, '..');

function getVersion() {
  const tauriConfPath = path.join(ROOT_DIR, 'src-tauri', 'tauri.conf.json');
  if (fs.existsSync(tauriConfPath)) {
    const conf = JSON.parse(fs.readFileSync(tauriConfPath, 'utf8'));
    if (conf.version) return String(conf.version).trim();
  }
  const pkgPath = path.join(ROOT_DIR, 'package.json');
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
  return String(pkg.version || '0.0.0').trim();
}

function sha512Base64(filePath) {
  const hash = crypto.createHash('sha512');
  const data = fs.readFileSync(filePath);
  hash.update(data);
  return hash.digest('base64');
}

function buildUpdaterYml(version, installerName, sha512, sizeBytes) {
  return [
    `version: ${version}`,
    `files:`,
    `  - url: ${installerName}`,
    `    sha512: ${sha512}`,
    `    size: ${sizeBytes}`,
    `path: ${installerName}`,
    `sha512: ${sha512}`,
    `releaseDate: '${new Date().toISOString()}'`,
    ''
  ].join('\n');
}

function buildTauriManifestJson(version, installerName, signature) {
  const tag = `v${version}`;
  return JSON.stringify(
    {
      version,
      notes: `Fanta OFME Downloader ${tag}`,
      pub_date: new Date().toISOString(),
      platforms: {
        'windows-x86_64': {
          signature: signature.trim(),
          url: `https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/releases/download/${tag}/${installerName}`
        }
      }
    },
    null,
    2
  ) + '\n';
}

function findMakensis() {
  const localAppData = process.env.LOCALAPPDATA || '';
  const candidates = [
    path.join(localAppData, 'tauri', 'NSIS', 'makensis.exe'),
    path.join(localAppData, 'tauri', 'NSIS', 'Bin', 'makensis.exe'),
    'C:\\Program Files (x86)\\NSIS\\makensis.exe',
    'C:\\Program Files\\NSIS\\makensis.exe',
    'makensis.exe'
  ];

  for (const candidate of candidates) {
    if (candidate === 'makensis.exe' || fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return 'makensis.exe';
}

function main() {
  const version = getVersion();
  const releaseDir = path.join(ROOT_DIR, 'src-tauri', 'target', 'release');
  const nsisDir = path.join(releaseDir, 'bundle', 'nsis');
  const iconPath = path.join(ROOT_DIR, 'src', 'renderer', 'assets', 'OFME-DWND-ICO.ico');

  const appExeSrc = path.join(releaseDir, 'fanta-ofme-downloader.exe');
  const sidecarExeSrc = path.join(releaseDir, 'bridge_server.exe');
  const rawSetupName = `Fanta OFME Downloader_${version}_x64-setup.exe`;
  const setupExeSrc = path.join(nsisDir, rawSetupName);

  const missing = [appExeSrc, sidecarExeSrc, setupExeSrc].filter(p => !fs.existsSync(p));
  if (missing.length > 0) {
    console.error('❌ Missing Tauri build artifacts:');
    missing.forEach(p => console.error(`   - ${p}`));
    console.error('Run `npm run tauri:sidecar` and `npm run tauri build` first.');
    process.exit(1);
  }

  // 1. Package Installer + beta.yml / latest.yml
  const outInstallerDir = path.join(ROOT_DIR, 'build', 'Tauri', 'Installer');
  fs.mkdirSync(outInstallerDir, { recursive: true });

  const cleanSetupName = `Fanta-OFME-Downloader-Setup-${version}.exe`;
  const outSetupPath = path.join(outInstallerDir, cleanSetupName);
  fs.copyFileSync(setupExeSrc, outSetupPath);

  const setupSize = fs.statSync(outSetupPath).size;
  const setupSha512 = sha512Base64(outSetupPath);
  const ymlContent = buildUpdaterYml(version, cleanSetupName, setupSha512, setupSize);

  // Remove stale duplicate beta.yml / beta.json if present from earlier builds
  for (const staleName of ['beta.yml', 'beta.json']) {
    const stalePath = path.join(outInstallerDir, staleName);
    if (fs.existsSync(stalePath)) fs.unlinkSync(stalePath);
  }

  const latestYmlPath = path.join(outInstallerDir, 'latest.yml');
  fs.writeFileSync(latestYmlPath, ymlContent, 'utf8');

  // Generate Tauri static JSON manifest (`latest.json`) from `.sig`
  const setupSigSrc = `${setupExeSrc}.sig`;
  let latestJsonPath = null;
  if (fs.existsSync(setupSigSrc)) {
    const signature = fs.readFileSync(setupSigSrc, 'utf8').trim();
    const manifestJson = buildTauriManifestJson(version, cleanSetupName, signature);
    latestJsonPath = path.join(outInstallerDir, 'latest.json');
    fs.writeFileSync(latestJsonPath, manifestJson, 'utf8');
  } else {
    console.warn(`⚠️ Signature file not found (${setupSigSrc}); skipping latest.json.`);
  }

  // 2. Package Single Standalone Portable Executable via NSIS
  const outFileDir = path.join(ROOT_DIR, 'build', 'Tauri', 'File');
  const stagingDir = path.join(outFileDir, 'portable');
  fs.rmSync(stagingDir, { recursive: true, force: true });
  fs.mkdirSync(stagingDir, { recursive: true });

  const stagedAppExe = path.join(stagingDir, 'Fanta OFME Downloader.exe');
  const stagedSidecarExe = path.join(stagingDir, 'bridge_server.exe');
  fs.copyFileSync(appExeSrc, stagedAppExe);
  fs.copyFileSync(sidecarExeSrc, stagedSidecarExe);

  // Clean up any older standalone zip/nsi leftovers
  const oldZip = path.join(outFileDir, `Fanta-OFME-Downloader-Portable-${version}.zip`);
  if (fs.existsSync(oldZip)) fs.unlinkSync(oldZip);

  const portableExePath = path.join(outFileDir, `Fanta-OFME-Downloader-Portable-${version}.exe`);
  if (fs.existsSync(portableExePath)) fs.unlinkSync(portableExePath);

  const nsiScriptPath = path.join(outFileDir, 'portable-wrapper.nsi');
  const nsiLines = [
    'Unicode True',
    'Name "Fanta OFME Downloader"',
    `OutFile "${portableExePath}"`,
    fs.existsSync(iconPath) ? `Icon "${iconPath}"` : '',
    'SilentInstall silent',
    'RequestExecutionLevel user',
    'SetCompressor /SOLID lzma',
    'ShowInstDetails nevershow',
    '',
    'Section "RunPortable"',
    '  InitPluginsDir',
    '  SetOutPath "$PLUGINSDIR"',
    `  File "${stagedAppExe}"`,
    `  File "${stagedSidecarExe}"`,
    '  System::Call \'Kernel32::SetEnvironmentVariable(t "PORTABLE_EXECUTABLE_DIR", t "$EXEDIR")\'',
    '  System::Call \'Kernel32::SetEnvironmentVariable(t "PORTABLE_EXECUTABLE_FILE", t "$EXEPATH")\'',
    '  ExecWait \'"$PLUGINSDIR\\Fanta OFME Downloader.exe"\'',
    'SectionEnd',
    ''
  ].filter(Boolean);

  fs.writeFileSync(nsiScriptPath, nsiLines.join('\n'), 'utf8');

  const makensis = findMakensis();
  console.log(`[Package Tauri] Compiling standalone portable executable with: ${makensis}`);
  try {
    execFileSync(makensis, ['/V2', nsiScriptPath], { stdio: 'inherit' });
  } finally {
    if (fs.existsSync(nsiScriptPath)) fs.unlinkSync(nsiScriptPath);
  }

  const portableSize = fs.statSync(portableExePath).size;

  console.log('\n======================================================');
  console.log(`📦 Tauri v${version} Release Package Ready`);
  console.log('======================================================');
  console.log(`💿 Installer (.exe) : ${outSetupPath} (${setupSize} bytes)`);
  if (latestJsonPath) {
    console.log(`🔄 Tauri (latest)   : ${latestJsonPath}`);
  }
  console.log(`📄 Electron (latest): ${latestYmlPath}`);
  console.log(`📦 Portable (.exe)  : ${portableExePath} (${portableSize} bytes)`);
  console.log('======================================================\n');
}

main();
