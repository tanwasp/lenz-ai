
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  onDisplayTooltip: (callback) => ipcRenderer.on('display-tooltip', callback),
});
