const { contextBridge, ipcRenderer } = require('electron');

const exposed = {
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  minimizeWindow: () => ipcRenderer.send('minimize-window'),
  maximizeWindow: () => ipcRenderer.send('maximize-window'),
  closeWindow: () => ipcRenderer.send('close-window'),
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  selectFile: (options) => ipcRenderer.invoke('select-file', options),
  openPath: (targetPath) => ipcRenderer.invoke('open-path', targetPath),
  showItemInFolder: (itemPath) => ipcRenderer.invoke('show-item-in-folder', itemPath),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  onBackendLog: (callback) => {
    const handler = (event, data) => callback(data);
    ipcRenderer.on('backend-log', handler);
    return () => ipcRenderer.removeListener('backend-log', handler);
  },
  getInitialLogs: () => ipcRenderer.invoke('get-initial-logs'),
  isSourceMode: () => ipcRenderer.invoke('is-source-mode'),
  isPortable: () => ipcRenderer.invoke('is-portable'),
  checkForUpdates: () => ipcRenderer.invoke('check-for-updates'),
  startDownloadUpdate: () => ipcRenderer.invoke('start-download-update'),
  restartAndInstallUpdate: () => ipcRenderer.invoke('restart-and-install-update'),
  onUpdaterEvent: (callback) => {
    const handler = (event, data) => callback(data);
    ipcRenderer.on('updater-event', handler);
    return () => ipcRenderer.removeListener('updater-event', handler);
  }
};

contextBridge.exposeInMainWorld('api', exposed);
contextBridge.exposeInMainWorld('fantaAPI', exposed);
