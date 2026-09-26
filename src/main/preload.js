const { contextBridge, ipcRenderer } = require('electron');

const exposed = {
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  minimizeWindow: () => ipcRenderer.send('minimize-window'),
  maximizeWindow: () => ipcRenderer.send('maximize-window'),
  closeWindow: () => ipcRenderer.send('close-window'),
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  selectFile: (options) => ipcRenderer.invoke('select-file', options),
  openPath: (targetPath) => ipcRenderer.invoke('open-path', targetPath),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  onBackendLog: (callback) => {
    const handler = (event, data) => callback(data);
    ipcRenderer.on('backend-log', handler);
    return () => ipcRenderer.removeListener('backend-log', handler);
  },
  getInitialLogs: () => ipcRenderer.invoke('get-initial-logs')
};

contextBridge.exposeInMainWorld('api', exposed);
contextBridge.exposeInMainWorld('fantaAPI', exposed);
