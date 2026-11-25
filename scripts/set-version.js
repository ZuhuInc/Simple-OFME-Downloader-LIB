/**
 * Fanta OFME Downloader - Version Synchronization Utility
 *
 * Usage:
 *   node scripts/set-version.js [new_version]
 *   npm run set-version 2.0.5
 *
 * If no version is supplied, it reads the version from package.json
 * and synchronizes all project files (package-lock.json, README.md, index.html, backend fallback).
 */

const fs = require('fs');
const path = require('path');

const ROOT_DIR = path.resolve(__dirname, '..');
const SEMVER_REGEX = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/;
const SEMVER_PATTERN = '[0-9]+\\.[0-9]+\\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?';
const SHIELDS_SEMVER_PATTERN = '[0-9]+\\.[0-9]+\\.[0-9]+(?:--?[0-9A-Za-z.-]+)?(?:\\+[0-9A-Za-z.-]+)?';

function getCleanVersion(raw) {
  if (!raw) return null;
  return raw.trim().replace(/^v/i, '');
}

function main() {
  const pkgPath = path.join(ROOT_DIR, 'package.json');
  if (!fs.existsSync(pkgPath)) {
    console.error('❌ Could not locate package.json at ' + pkgPath);
    process.exit(1);
  }

  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf-8'));
  let targetVersion = getCleanVersion(process.argv[2]) || pkg.version;

  if (!SEMVER_REGEX.test(targetVersion)) {
    console.error(`❌ Invalid semver version: "${targetVersion}". Expected format like "2.0.5" or "2.5.0-beta.1".`);
    process.exit(1);
  }

  console.log(`\n======================================================`);
  console.log(`🚀 Synchronizing Fanta OFME Downloader to version v${targetVersion}`);
  console.log(`======================================================\n`);

  const updatedFiles = [];

  // 1. Update package.json
  if (pkg.version !== targetVersion) {
    pkg.version = targetVersion;
    fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n', 'utf-8');
    updatedFiles.push('package.json');
  } else {
    updatedFiles.push('package.json (already up to date)');
  }

  // 2. Update package-lock.json if present
  const lockPath = path.join(ROOT_DIR, 'package-lock.json');
  if (fs.existsSync(lockPath)) {
    try {
      const lockData = JSON.parse(fs.readFileSync(lockPath, 'utf-8'));
      let lockChanged = false;
      if (lockData.version !== targetVersion) {
        lockData.version = targetVersion;
        lockChanged = true;
      }
      if (lockData.packages && lockData.packages[''] && lockData.packages[''].version !== targetVersion) {
        lockData.packages[''].version = targetVersion;
        lockChanged = true;
      }
      if (lockChanged) {
        fs.writeFileSync(lockPath, JSON.stringify(lockData, null, 2) + '\n', 'utf-8');
        updatedFiles.push('package-lock.json');
      } else {
        updatedFiles.push('package-lock.json (already up to date)');
      }
    } catch (e) {
      console.warn('⚠️ Could not update package-lock.json:', e.message);
    }
  }

  // 3. Update src/renderer/index.html placeholders
  const htmlPath = path.join(ROOT_DIR, 'src', 'renderer', 'index.html');
  if (fs.existsSync(htmlPath)) {
    let html = fs.readFileSync(htmlPath, 'utf-8');
    const oldHtml = html;
    html = html.replace(
      new RegExp(`(<span class="app-version-tag">)v${SEMVER_PATTERN}(<\\/span>)`, 'g'),
      `$1v${targetVersion}$2`
    );
    html = html.replace(
      new RegExp(`(<span id="updateAppVersionBadge"[^>]*>)v${SEMVER_PATTERN}(<\\/span>)`, 'g'),
      `$1v${targetVersion}$2`
    );
    if (html !== oldHtml) {
      fs.writeFileSync(htmlPath, html, 'utf-8');
      updatedFiles.push('src/renderer/index.html');
    } else {
      updatedFiles.push('src/renderer/index.html (already up to date)');
    }
  }

  // 4. Update README.md
  const readmePath = path.join(ROOT_DIR, 'README.md');
  if (fs.existsSync(readmePath)) {
    let readme = fs.readFileSync(readmePath, 'utf-8');
    const oldReadme = readme;
    const shieldsVersion = targetVersion.replace(/-/g, '--');

    // Header: # FANTA OFME Downloader (vX.X.X)
    readme = readme.replace(
      new RegExp(`(# FANTA OFME Downloader \\(v)${SEMVER_PATTERN}(\\))`, 'g'),
      `$1${targetVersion}$2`
    );
    // Version Shield Badge
    readme = readme.replace(
      new RegExp(`(img\\.shields\\.io\\/badge\\/version-)${SHIELDS_SEMVER_PATTERN}(-d4a853\\.svg)`, 'g'),
      `$1${shieldsVersion}$2`
    );
    // Setup and Portable executable references
    readme = readme.replace(
      new RegExp(`Fanta OFME Downloader Setup ${SEMVER_PATTERN}\\.exe`, 'g'),
      `Fanta OFME Downloader Setup ${targetVersion}.exe`
    );
    readme = readme.replace(
      new RegExp(`Fanta OFME Downloader Portable ${SEMVER_PATTERN}\\.exe`, 'g'),
      `Fanta OFME Downloader Portable ${targetVersion}.exe`
    );

    if (readme !== oldReadme) {
      fs.writeFileSync(readmePath, readme, 'utf-8');
      updatedFiles.push('README.md');
    } else {
      updatedFiles.push('README.md (already up to date)');
    }
  }

  // 5. Update backend fallback in src/backend/__init__.py
  const backendInitPath = path.join(ROOT_DIR, 'src', 'backend', '__init__.py');
  if (fs.existsSync(backendInitPath)) {
    let backendInit = fs.readFileSync(backendInitPath, 'utf-8');
    const oldBackendInit = backendInit;
    backendInit = backendInit.replace(
      new RegExp(`(# 3\\. Fallback default\\r?\\n\\s+return ")${SEMVER_PATTERN}(")`, 'g'),
      `$1${targetVersion}$2`
    );
    if (backendInit !== oldBackendInit) {
      fs.writeFileSync(backendInitPath, backendInit, 'utf-8');
      updatedFiles.push('src/backend/__init__.py');
    } else {
      updatedFiles.push('src/backend/__init__.py (already up to date)');
    }
  }

  // 6. Update backend fallback in src/backend/version_checker.py
  const vcPath = path.join(ROOT_DIR, 'src', 'backend', 'version_checker.py');
  if (fs.existsSync(vcPath)) {
    let vc = fs.readFileSync(vcPath, 'utf-8');
    const oldVc = vc;
    vc = vc.replace(
      new RegExp(`(__version__\\s*=\\s*")${SEMVER_PATTERN}(")`, 'g'),
      `$1${targetVersion}$2`
    );
    if (vc !== oldVc) {
      fs.writeFileSync(vcPath, vc, 'utf-8');
      updatedFiles.push('src/backend/version_checker.py');
    }
  }

  // 7. Update backend fallback in src/backend/config.py
  const configPath = path.join(ROOT_DIR, 'src', 'backend', 'config.py');
  if (fs.existsSync(configPath)) {
    let cfg = fs.readFileSync(configPath, 'utf-8');
    const oldCfg = cfg;
    cfg = cfg.replace(
      new RegExp(`(os\\.environ\\.get\\("FANTA_APP_VERSION",\\s*")${SEMVER_PATTERN}("\\))`, 'g'),
      `$1${targetVersion}$2`
    );
    if (cfg !== oldCfg) {
      fs.writeFileSync(configPath, cfg, 'utf-8');
      updatedFiles.push('src/backend/config.py');
    }
  }

  // 8. Update src-tauri/tauri.conf.json
  const tauriConfPath = path.join(ROOT_DIR, 'src-tauri', 'tauri.conf.json');
  if (fs.existsSync(tauriConfPath)) {
    const tauriConf = JSON.parse(fs.readFileSync(tauriConfPath, 'utf-8'));
    if (tauriConf.version !== targetVersion) {
      tauriConf.version = targetVersion;
      fs.writeFileSync(tauriConfPath, JSON.stringify(tauriConf, null, 2) + '\n', 'utf-8');
      updatedFiles.push('src-tauri/tauri.conf.json');
    } else {
      updatedFiles.push('src-tauri/tauri.conf.json (already up to date)');
    }
  }

  // 9. Update [package] version in src-tauri/Cargo.toml
  const cargoTomlPath = path.join(ROOT_DIR, 'src-tauri', 'Cargo.toml');
  if (fs.existsSync(cargoTomlPath)) {
    let cargoToml = fs.readFileSync(cargoTomlPath, 'utf-8');
    const oldCargo = cargoToml;
    cargoToml = cargoToml.replace(
      new RegExp(`(\\[package\\][\\s\\S]*?\\nversion\\s*=\\s*")${SEMVER_PATTERN}(")`, 'm'),
      `$1${targetVersion}$2`
    );
    if (cargoToml !== oldCargo) {
      fs.writeFileSync(cargoTomlPath, cargoToml, 'utf-8');
      updatedFiles.push('src-tauri/Cargo.toml');
    } else {
      updatedFiles.push('src-tauri/Cargo.toml (already up to date)');
    }
  }

  console.log('✅ Synchronization completed:');
  updatedFiles.forEach(file => console.log(`   - ${file}`));
  console.log(`\n🎉 Project version is now set to: v${targetVersion}\n`);
}

main();
