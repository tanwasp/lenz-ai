
const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const fs = require('fs'); const net = require('net');

let mainWindow;

function createWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  mainWindow = new BrowserWindow({
    width,
    height,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
    },
  });

  mainWindow.setIgnoreMouseEvents(true);
  mainWindow.loadFile('renderer/index.html');
}

app.whenReady().then(() => {
  createWindow();

  if (process.argv.includes('--test')) {
    setTimeout(() => {
      const cursor = screen.getCursorScreenPoint();
      mainWindow.webContents.send('display-tooltip', { text: 'This is a test tooltip.', x: cursor.x, y: cursor.y });
    }, 1000);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.on('show-tooltip', (event, text) => {
  const cursor = screen.getCursorScreenPoint();
  mainWindow.webContents.send('display-tooltip', { text, x: cursor.x, y: cursor.y });
});

const SOCK = '/tmp/screenpipe_tooltip.sock';

// Remove stale socket from previous run
try { fs.unlinkSync(SOCK); } catch (e) { /* ignore */ }

net.createServer(conn => {
  conn.on('data', buf => {
    let payload;
    try   { payload = JSON.parse(buf.toString()); }
    catch { return; }                     // bad JSON, ignore

    const { text = '', duration = 5 } = payload;

    // current cursor position
    const { x, y } = screen.getCursorScreenPoint();

    // forward to renderer
    mainWindow.webContents.send('display-tooltip', { text, x, y, duration });
  });
}).listen(SOCK, () => {
  console.log('Tooltip socket listening:', SOCK);
});