const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

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

function startBackend() {
  const backendScript = path.join(__dirname, '..', 'backend', 'bridge_server.py');
  const pythonExe = findPythonPath();
  const spawnMsg = `[Main] Spawning Python Backend (${pythonExe}): ${backendScript}`;
  console.log(spawnMsg);
  broadcastLog(spawnMsg, 'info');

  try {
    pythonProcess = spawn(pythonExe, [backendScript], {
      cwd: path.join(__dirname, '..', '..'),
      env: { ...process.env, PYTHONUNBUFFERED: '1', FANTA_BACKEND_PORT: '5004' }
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
      await shell.openPath(targetPath);
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

app.whenReady().then(() => {
  createWindow();
  startBackend();

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
