const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const https = require('https');
const { autoUpdater } = require('electron-updater');

// Configure autoUpdater settings (Notify only, download on user click)
autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = true;

let mainWindow = null;
let pythonProcess = null;
const logBuffer = [];

function findPythonPath() {
  const rootDir = path.join(__dirname, '..', '..');
  const isWin = process.platform === 'win32';

  const candidates = [
    process.env.PYTHON,
    // Project-specific .venv / venv
    path.join(rootDir, '.venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python'),
    path.join(rootDir, 'venv', isWin ? 'Scripts' : 'bin', isWin ? 'python.exe' : 'python'),
    // System PATH fallbacks
    'python3',
    'python',
    'py'
  ];

  for (const candidate of candidates) {
    if (candidate) {
      if (fs.existsSync(candidate) || candidate === 'python' || candidate === 'python3' || candidate === 'py') {
        return candidate;
      }
    }
  }
  return 'python';
}

function broadcastLog(text, customLevel = null) {
  if (!text || typeof text !== 'string') return;
  const cleanText = text.trim();
  if (!cleanText) return;

  let level = customLevel;
  if (!level) {
    const lower = cleanText.toLowerCase();
    if (lower.includes('error') || lower.includes('failed') || lower.includes('exception') || lower.includes('traceback') || lower.includes('errno')) {
      level = 'danger';
    } else if (lower.includes('warn') || lower.includes('warning') || lower.includes('skipped')) {
      level = 'warning';
    } else if (lower.includes('success') || lower.includes('connected') || lower.includes('loaded') || lower.includes('ready') || lower.includes('starting')) {
      level = 'success';
    } else {
      level = 'info';
    }
  }

  const logEntry = {
    text: cleanText,
    level,
    time: new Date().toLocaleTimeString()
  };

  logBuffer.push(logEntry);
  if (logBuffer.length > 200) {
    logBuffer.shift();
  }

  if (mainWindow && mainWindow.webContents) {
    mainWindow.webContents.send('backend-log', logEntry);
  }
}

function isSourceMode() {
  return !app.isPackaged || process.env.NODE_ENV === 'development' || Boolean(process.defaultApp);
}

function isPortable() {
  return Boolean(process.env.PORTABLE_EXECUTABLE_DIR || process.env.PORTABLE_EXECUTABLE_FILE);
}

function hasUpdateConfig() {
  if (!app.isPackaged) return false;
  const updateYml = path.join(process.resourcesPath, 'app-update.yml');
  return fs.existsSync(updateYml);
}

function cleanVersion(v) {
  if (!v || typeof v !== 'string') return '0.0.0';
  return v.trim().replace(/^[vV]/, '');
}

function isNewerVersion(remoteVer, currentVer) {
  const r = cleanVersion(remoteVer).split('.').map(n => parseInt(n, 10) || 0);
  const c = cleanVersion(currentVer).split('.').map(n => parseInt(n, 10) || 0);

  for (let i = 0; i < Math.max(r.length, c.length); i++) {
    const rNum = r[i] || 0;
    const cNum = c[i] || 0;
    if (rNum > cNum) return true;
    if (rNum < cNum) return false;
  }
  return false;
}

function checkGitHubRelease() {
  return new Promise((resolve) => {
    const options = {
      hostname: 'api.github.com',
      path: '/repos/ZuhuInc/Simple-OFME-Downloader-LIB/releases/latest',
      headers: {
        'User-Agent': 'Fanta-OFME-Downloader'
      }
    };

    const req = https.get(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        if (res.statusCode === 200) {
          try {
            const release = JSON.parse(data);
            const rawTag = release.tag_name || '';
            const cleanedTag = cleanVersion(rawTag);
            const currentVer = app.getVersion();
            if (isNewerVersion(cleanedTag, currentVer)) {
              resolve({
                status: 'update-available',
                version: cleanedTag,
                releaseUrl: release.html_url || 'https://github.com/ZuhuInc/Simple-OFME-Downloader-LIB/releases',
                releaseNotes: release.body || ''
              });
            } else {
              resolve({ status: 'up-to-date', version: currentVer });
            }
          } catch (e) {
            resolve({ status: 'up-to-date', version: app.getVersion() });
          }
        } else if (res.statusCode === 404) {
          resolve({ status: 'no-release', version: app.getVersion() });
        } else {
          resolve({ status: 'up-to-date', version: app.getVersion() });
        }
      });
    });

    req.on('error', () => {
      resolve({ status: 'up-to-date', version: app.getVersion() });
    });
  });
}

function setupAutoUpdater() {
  if (!app.isPackaged) {
    console.log('[AutoUpdater] Development/source mode detected: Auto-update checks disabled.');
    return;
  }

  if (!hasUpdateConfig()) {
    console.log('[AutoUpdater] Standalone portable mode: Checking GitHub releases via API...');
    setTimeout(async () => {
      const releaseInfo = await checkGitHubRelease();
      if (releaseInfo.status === 'update-available') {
        broadcastLog(`[AutoUpdater] New release available on GitHub: v${releaseInfo.version}!`, 'success');
        if (mainWindow && mainWindow.webContents) {
          mainWindow.webContents.send('updater-event', {
            type: 'portable-available',
            version: releaseInfo.version,
            releaseUrl: releaseInfo.releaseUrl
          });
        }
      }
    }, 5000);
    return;
  }

  autoUpdater.on('checking-for-update', () => {
    broadcastLog('[AutoUpdater] Checking GitHub releases for updates...', 'info');
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('updater-event', { type: 'checking' });
    }
  });

  autoUpdater.on('update-available', (info) => {
    broadcastLog(`[AutoUpdater] New update found: v${info.version}! Waiting for user confirmation to download...`, 'info');
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('updater-event', {
        type: 'available',
        version: info.version,
        releaseDate: info.releaseDate,
        releaseNotes: info.releaseNotes
      });
    }
  });

  autoUpdater.on('update-not-available', (info) => {
    broadcastLog(`[AutoUpdater] Current version (v${app.getVersion()}) is up-to-date.`, 'info');
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('updater-event', {
        type: 'not-available',
        version: app.getVersion()
      });
    }
  });

  autoUpdater.on('download-progress', (progressObj) => {
    const percent = Math.floor(progressObj.percent || 0);
    const speedMB = (progressObj.bytesPerSecond / (1024 * 1024)).toFixed(1);
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('updater-event', {
        type: 'progress',
        percent: percent,
        speed: `${speedMB} MB/s`,
        transferred: progressObj.transferred,
        total: progressObj.total
      });
    }
  });

  autoUpdater.on('update-downloaded', (info) => {
    broadcastLog(`[AutoUpdater] Update v${info.version} downloaded successfully and ready for install!`, 'success');
    if (mainWindow && mainWindow.webContents) {
      mainWindow.webContents.send('updater-event', {
        type: 'downloaded',
        version: info.version
      });
    }
  });

  autoUpdater.on('error', (err) => {
    const errText = err?.message || String(err);
    console.error('[AutoUpdater] Error:', errText);
    if (errText.includes('404') || errText.includes('HttpError: 404') || errText.includes('Cannot find latest') || errText.includes('ENOENT')) {
      broadcastLog(`[AutoUpdater] GitHub release check: App is currently on latest v${app.getVersion()}.`, 'info');
      if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send('updater-event', {
          type: 'not-available',
          version: app.getVersion()
        });
      }
    } else {
      broadcastLog(`[AutoUpdater] Update check notice: ${errText}`, 'warning');
      if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send('updater-event', {
          type: 'error',
          message: errText
        });
      }
    }
  });

  // Automatically check 5 seconds after startup
  setTimeout(() => {
    if (hasUpdateConfig()) {
      autoUpdater.checkForUpdates().catch(err => {
        console.warn('[AutoUpdater] Initial check notice:', err?.message || err);
      });
    }
  }, 5000);
}


function startBackend() {
  const sourceMode = isSourceMode();
  let pythonExe;
  let args = [];
  let cwd;

  if (app.isPackaged) {
    // Packaged production mode: Run frozen PyInstaller binary bundled in resources
    const primaryBin = path.join(process.resourcesPath, 'backend', 'bridge_server', 'bridge_server.exe');
    const fallbackBin = path.join(process.resourcesPath, 'bridge_server', 'bridge_server.exe');
    if (fs.existsSync(primaryBin)) {
      pythonExe = primaryBin;
    } else if (fs.existsSync(fallbackBin)) {
      pythonExe = fallbackBin;
    } else {
      pythonExe = path.join(__dirname, '..', '..', 'dist_backend', 'bridge_server', 'bridge_server.exe');
    }
    args = [];
    cwd = path.dirname(pythonExe);
  } else {
    // Source development mode: Run Python interpreter with bridge_server.py
    pythonExe = findPythonPath();
    const backendScript = path.join(__dirname, '..', 'backend', 'bridge_server.py');
    args = [backendScript];
    cwd = path.join(__dirname, '..', '..');
  }

  const spawnMsg = `[Main] Spawning Backend (${app.isPackaged ? 'Frozen Binary' : 'Python Interpreter'}, SourceMode=${sourceMode}): ${pythonExe}`;
  console.log(spawnMsg);
  broadcastLog(spawnMsg, 'info');

  try {
    pythonProcess = spawn(pythonExe, args, {
      cwd: cwd,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        FANTA_BACKEND_PORT: '5004',
        FANTA_SOURCE_MODE: sourceMode ? '1' : '0'
      }
    });

    pythonProcess.stdout.on('data', (data) => {
      const raw = data.toString();
      console.log(`[Python Backend] ${raw.trim()}`);
      raw.split(/\r?\n/).forEach(line => {
        if (line.trim()) broadcastLog(line);
      });
    });

    pythonProcess.stderr.on('data', (data) => {
      const raw = data.toString();
      console.log(`[Python Backend] ${raw.trim()}`);
      raw.split(/\r?\n/).forEach(line => {
        if (line.trim()) {
          // Suppress harmless Flask/WSGI server warnings from live UI console
          if (line.includes('WARNING: This is a development server') || line.includes('WSGI server instead') || line.includes('allow_unsafe_werkzeug')) {
            return;
          }
          // Filter common HTTP request info from being treated as errors
          if (line.includes('HTTP/1.1" 200') || line.includes('HTTP/1.1" 304') || line.includes('Running on http://')) {
            broadcastLog(line, 'info');
          } else {
            broadcastLog(line);
          }
        }
      });
    });

    pythonProcess.on('close', (code) => {
      const exitMsg = `[Python Backend] Exited with code ${code}`;
      console.log(exitMsg);
      broadcastLog(exitMsg, code === 0 ? 'info' : 'warning');
      pythonProcess = null;
    });
  } catch (err) {
    const errMsg = `[Main] Failed to spawn Python backend process: ${err.message}`;
    console.error(errMsg);
    broadcastLog(errMsg, 'danger');
  }
}

function createWindow() {
  const iconPath = path.join(__dirname, '..', 'renderer', 'assets', 'OFME-DWND-ICO.ico');
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 840,
    minWidth: 1000,
    minHeight: 700,
    frame: false,
    titleBarStyle: 'hidden',
    backgroundColor: '#0a0a0d',
    icon: iconPath,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'renderer', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Window control IPCs
ipcMain.on('minimize-window', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('maximize-window', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('close-window', () => {
  if (mainWindow) mainWindow.close();
});

ipcMain.handle('select-directory', async () => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('select-file', async (event, options = {}) => {
  if (!mainWindow) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    ...options
  });
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

ipcMain.handle('open-path', async (event, targetPath) => {
  if (!targetPath) return false;
  try {
    if (fs.existsSync(targetPath)) {
      const stat = fs.statSync(targetPath);
      if (stat.isDirectory()) {
        await shell.openPath(targetPath);
      } else {
        // Target is a file (.exe, .txt, etc.) - show it in explorer without executing it!
        shell.showItemInFolder(targetPath);
      }
      return true;
    } else {
      const parent = path.dirname(targetPath);
      if (fs.existsSync(parent)) {
        await shell.openPath(parent);
        return true;
      }
    }
  } catch (err) {
    console.error('[Main] openPath error:', err);
  }
  return false;
});

ipcMain.handle('show-item-in-folder', async (event, itemPath) => {
  if (!itemPath) return false;
  try {
    if (fs.existsSync(itemPath)) {
      shell.showItemInFolder(itemPath);
      return true;
    } else {
      const parent = path.dirname(itemPath);
      if (fs.existsSync(parent)) {
        await shell.openPath(parent);
        return true;
      }
    }
  } catch (err) {
    console.error('[Main] showItemInFolder error:', err);
  }
  return false;
});

ipcMain.handle('open-external', async (event, url) => {
  if (!url || typeof url !== 'string' || (!url.startsWith('http://') && !url.startsWith('https://'))) return false;
  try {
    await shell.openExternal(url);
    return true;
  } catch (err) {
    console.error('[Main] openExternal error:', err);
    return false;
  }
});

ipcMain.handle('get-app-version', () => app.getVersion());
ipcMain.handle('get-initial-logs', () => logBuffer);
ipcMain.handle('is-source-mode', () => isSourceMode());
ipcMain.handle('is-portable', () => isPortable());

// Auto-updater IPC handlers
ipcMain.handle('check-for-updates', async () => {
  if (!app.isPackaged) {
    return { status: 'dev-mode', message: 'Auto-updater is inactive in source/development mode.' };
  }
  if (!hasUpdateConfig()) {
    // Portable build: query GitHub API directly
    try {
      const releaseInfo = await checkGitHubRelease();
      if (releaseInfo.status === 'update-available') {
        return {
          status: 'portable-update-available',
          version: releaseInfo.version,
          releaseUrl: releaseInfo.releaseUrl,
          message: `New version v${releaseInfo.version} is available on GitHub!`
        };
      }
      return {
        status: 'up-to-date',
        message: 'Your standalone version is currently on the latest release.'
      };
    } catch (e) {
      return { status: 'up-to-date', message: 'Checked GitHub for updates.' };
    }
  }
  try {
    const result = await autoUpdater.checkForUpdates();
    return { status: 'success', updateInfo: result?.updateInfo };
  } catch (err) {
    const msg = err?.message || String(err);
    if (msg.includes('404') || msg.includes('HttpError: 404') || msg.includes('Cannot find latest') || msg.includes('ENOENT')) {
      return {
        status: 'no-release',
        message: 'No newer release published on GitHub yet (app is up to date).'
      };
    }
    return { status: 'error', error: msg };
  }
});

ipcMain.handle('start-download-update', async () => {
  if (!app.isPackaged || !hasUpdateConfig()) {
    return { status: 'error', message: 'Download updater is only active in the installed build.' };
  }
  try {
    broadcastLog('[AutoUpdater] User triggered download: Fetching update package...', 'info');
    await autoUpdater.downloadUpdate();
    return { status: 'downloading' };
  } catch (err) {
    const msg = err?.message || String(err);
    broadcastLog(`[AutoUpdater] Download failed: ${msg}`, 'warning');
    return { status: 'error', error: msg };
  }
});

ipcMain.handle('restart-and-install-update', () => {
  // isSilent = true: Headless background install without wizard UI
  // isForceRunAfter = true: Automatically relaunches the updated application in the same location
  autoUpdater.quitAndInstall(true, true);
});

app.whenReady().then(() => {
  createWindow();
  startBackend();
  setupAutoUpdater();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (pythonProcess) {
    console.log('[Main] Terminating Python backend process...');
    pythonProcess.kill();
    pythonProcess = null;
  }
});
