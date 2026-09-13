const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('daonroad', Object.freeze({
  saveFile: (defaultName, data) => ipcRenderer.invoke('save-file', { defaultName, data }),
}));
