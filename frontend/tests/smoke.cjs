// Hidden, isolated Electron window: never starts or stops the user's containers.
const { app, BrowserWindow, session } = require('electron');
const path = require('path');
app.commandLine.appendSwitch('disable-gpu');
app.whenReady().then(async () => {
  session.defaultSession.webRequest.onBeforeRequest({ urls: ['https://*/*', 'http://*/*'] }, (_details, done) => done({ cancel: true }));
  const window = new BrowserWindow({ show: false, webPreferences: {
    preload: path.join(__dirname, '../src/preload.js'), nodeIntegration: false,
    contextIsolation: true, sandbox: true, webSecurity: true,
  } });
  try {
    await window.loadFile(path.join(__dirname, '../index.html'));
    const result = await window.webContents.executeJavaScript(`({
      mapReady: typeof map !== 'undefined',
      nodeDisabled: typeof require === 'undefined',
      saveBridge: typeof window.daonroad?.saveFile === 'function',
      limit: readOptions().max_ride_min,
      date: document.getElementById('serviceDate').value
    })`);
    if (!result.mapReady || !result.nodeDisabled || !result.saveBridge || result.limit !== 90 || !result.date) throw new Error(JSON.stringify(result));
    console.log('Electron smoke passed', JSON.stringify(result));
    app.exit(0);
  } catch (error) {
    console.error(error);
    app.exit(1);
  }
});
