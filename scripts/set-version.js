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

  if (!/^\d+\.\d+\.\d+/.test(targetVersion)) {
    console.error(`❌ Invalid semver version: "${targetVersion}". Expected format like "2.0.5".`);
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
      /(<span class="app-version-tag">)v[0-9.]+(<\/span>)/g,
      `$1v${targetVersion}$2`
    );
    html = html.replace(
      /(<span id="updateAppVersionBadge"[^>]*>)v[0-9.]+(<\/span>)/g,
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

    // Header: # FANTA OFME Downloader (vX.X.X)
    readme = readme.replace(
      /(# FANTA OFME Downloader \(v)[0-9.]+(\))/g,
      `$1${targetVersion}$2`
    );
    // Version Shield Badge
    readme = readme.replace(
      /(img\.shields\.io\/badge\/version-)[0-9.]+(-d4a853\.svg)/g,
      `$1${targetVersion}$2`
    );
    // Setup and Portable executable references
    readme = readme.replace(
      /Fanta OFME Downloader Setup [0-9.]+\.exe/g,
      `Fanta OFME Downloader Setup ${targetVersion}.exe`
    );
    readme = readme.replace(
      /Fanta OFME Downloader Portable [0-9.]+\.exe/g,
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
      /(# 3\. Fallback default\r?\n\s+return ")[0-9.]+(")/g,
      `$1${targetVersion}$2`
    );
    if (backendInit !== oldBackendInit) {
      fs.writeFileSync(backendInitPath, backendInit, 'utf-8');
      updatedFiles.push('src/backend/__init__.py');
    } else {
      updatedFiles.push('src/backend/__init__.py (already up to date)');
    }
  }

  console.log('✅ Synchronization completed:');
  updatedFiles.forEach(file => console.log(`   - ${file}`));
  console.log(`\n🎉 Project version is now set to: v${targetVersion}\n`);
}

main();
