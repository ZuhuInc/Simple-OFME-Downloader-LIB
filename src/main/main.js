const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

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

function startBackend() {
  const backendScript = path.join(__dirname, '..', 'backend', 'bridge_server.py');
  const pythonExe = findPythonPath();
  console.log(`[Main] Spawning Python Backend (${pythonExe}):`, backendScript);

  try {
    pythonProcess = spawn(pythonExe, [backendScript], {
      cwd: path.join(__dirname, '..', '..'),
      env: { ...process.env, PYTHONUNBUFFERED: '1', FANTA_BACKEND_PORT: '5004' }
    });

    pythonProcess.stdout.on('data', (data) => {
      console.log(`[Python Backend] ${data.toString().trim()}`);
    });

    pythonProcess.stderr.on('data', (data) => {
      const msg = data.toString().trim();
      if (msg.includes('HTTP/1.1" 200') || msg.includes('HTTP/1.1" 304') || msg.includes('Running on http://')) {
        console.log(`[Python Backend] ${msg}`);
      } else {
        console.log(`[Python Backend] ${msg}`);
      }
    });

    pythonProcess.on('close', (code) => {
      console.log(`[Python Backend] exited with code ${code}`);
      pythonProcess = null;
    });
  } catch (err) {
    console.error('[Main] Failed to spawn Python backend process:', err);
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

app.whenReady().then(() => {
  startBackend();
  createWindow();

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
