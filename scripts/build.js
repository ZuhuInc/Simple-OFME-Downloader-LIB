/**
 * Fanta OFME Downloader - Packaging & Build Orchestrator
 * Compiles Python backend with PyInstaller and bundles Electron into:
 *   - build/File/       -> Standalone / Portable test executable & unpacked directory
 *   - build/Installer/  -> NSIS Setup executable + auto-update metadata (latest.yml)
 */

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ROOT_DIR = path.resolve(__dirname, '..');
const ICON_PATH = path.join(ROOT_DIR, 'src', 'renderer', 'assets', 'OFME-DWND-ICO.ico');

// Find Python interpreter (.venv preferred)
function getPythonExecutable() {
  const isWin = process.platform === 'win32';
  const candidates = [
    process.env.PYTHON,
    path.join(ROOT_DIR, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python'),
    path.join(ROOT_DIR, 'venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python'),
    'python3',
    'python',
    'py'
  ];

  for (const candidate of candidates) {
    if (candidate && (fs.existsSync(candidate) || candidate.startsWith('py'))) {
      return candidate;
    }
  }
  return 'python';
}

function buildBackend() {
  console.log('\n======================================================');
  console.log('🚀 STEP 1: Compiling Python Backend with PyInstaller');
  console.log('======================================================');

  const pythonExe = getPythonExecutable();
  const buildScript = path.join(ROOT_DIR, 'scripts', 'build_backend.py');

  console.log(`[Build] Using Python: ${pythonExe}`);
  console.log(`[Build] Running: ${buildScript}\n`);

  const result = spawnSync(pythonExe, [buildScript], {
    cwd: ROOT_DIR,
    stdio: 'inherit',
    shell: true,
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  if (result.status !== 0) {
    console.error(`\n❌ [Build] Python backend compilation failed with exit code ${result.status}`);
    process.exit(result.status || 1);
  }

  const backendDist = path.join(ROOT_DIR, 'dist_backend', 'bridge_server', 'bridge_server.exe');
  if (!fs.existsSync(backendDist)) {
    console.error(`\n❌ [Build] Expected backend binary not found at: ${backendDist}`);
    process.exit(1);
  }

  console.log(`\n✅ [Build] Python backend compiled successfully -> ${backendDist}`);
}

function runElectronBuilder(args) {
  const electronBuilderCli = require.resolve('electron-builder/out/cli/cli.js');

  console.log(`[Build] Invoking electron-builder: ${args.join(' ')}`);
  const result = spawnSync(process.execPath, [electronBuilderCli, ...args], {
    cwd: ROOT_DIR,
    stdio: 'inherit',
    env: { ...process.env }
  });

  if (result.status !== 0) {
    console.error(`\n❌ [Build] electron-builder failed with exit code ${result.status}`);
    process.exit(result.status || 1);
  }
}

function buildStandalone() {
  console.log('\n======================================================');
  console.log('📦 STEP 2: Packaging Standalone / Test File Build');
  console.log('   Destination: build/File/');
  console.log('======================================================');

  const outputDir = path.join(ROOT_DIR, 'build', 'File');
  fs.mkdirSync(outputDir, { recursive: true });

  const builderArgs = [
    '--win',
    'portable',
    'dir',
    `--config.directories.output=${outputDir}`,
    '--config.win.target=portable,dir',
    '--config.portable.artifactName=${productName} Portable ${version}.${ext}'
  ];

  runElectronBuilder(builderArgs);
  console.log(`\n✅ [Build] Standalone build ready in: ${outputDir}`);
}

function buildInstaller() {
  console.log('\n======================================================');
  console.log('💿 STEP 3: Packaging NSIS Installer & Auto-Updater');
  console.log('   Destination: build/Installer/');
  console.log('======================================================');

  const outputDir = path.join(ROOT_DIR, 'build', 'Installer');
  fs.mkdirSync(outputDir, { recursive: true });

  const builderArgs = [
    '--win',
    'nsis',
    `--config.directories.output=${outputDir}`,
    '--config.win.target=nsis',
    '--config.nsis.artifactName=${productName} Setup ${version}.${ext}'
  ];

  runElectronBuilder(builderArgs);
  console.log(`\n✅ [Build] Installer & auto-updater metadata ready in: ${outputDir}`);
}

function main() {
  const args = process.argv.slice(2);
  let target = 'all';
  let skipBackend = false;

  args.forEach(arg => {
    if (arg.startsWith('--target=')) {
      target = arg.split('=')[1].toLowerCase();
    } else if (arg === '--skip-backend') {
      skipBackend = true;
    }
  });

  console.log(`\n[Fanta OFME Build System] Target: "${target}", Skip Backend: ${skipBackend}`);

  if (target === 'backend') {
    buildBackend();
    return;
  }

  if (!skipBackend) {
    buildBackend();
  }

  if (target === 'file' || target === 'standalone') {
    buildStandalone();
  } else if (target === 'installer') {
    buildInstaller();
  } else if (target === 'all') {
    buildStandalone();
    buildInstaller();
  } else {
    console.error(`Unknown target: ${target}. Valid options: all, file, installer, backend`);
    process.exit(1);
  }

  console.log('\n======================================================');
  console.log('🎉 BUILD COMPLETE!');
  console.log('======================================================');
  if (target === 'all' || target === 'file' || target === 'standalone') {
    console.log(`📁 Standalone File Build : ${path.join(ROOT_DIR, 'build', 'File')}`);
  }
  if (target === 'all' || target === 'installer') {
    console.log(`💿 Setup Installer Build  : ${path.join(ROOT_DIR, 'build', 'Installer')}`);
  }
  console.log('======================================================\n');
}

main();
