/**
 * DaOnRoad - Electron 메인 프로세스
 */
const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path  = require('path');
const fs    = require('fs');
const { spawn, execSync } = require('child_process');

const IS_DEV   = process.argv.includes('--dev');
const API_PORT = 8000;

let mainWindow  = null;
let backendProc = null;

// ─── 백엔드 디렉터리 경로 계산 ───────────────────────────────────
// 구조: DaOnRoad/frontend/src/main.js
//       DaOnRoad/backend/
function getBackendDir() {
  // __dirname = .../frontend/src
  const fromSrc = path.resolve(__dirname, '..', '..', 'backend');
  if (fs.existsSync(path.join(fromSrc, 'main.py'))) return fromSrc;

  // 패키징된 경우 (asar 밖)
  const fromExe = path.resolve(process.execPath, '..', 'backend');
  if (fs.existsSync(path.join(fromExe, 'main.py'))) return fromExe;

  // resources 폴더
  const fromRes = path.resolve(process.resourcesPath || __dirname, 'backend');
  if (fs.existsSync(path.join(fromRes, 'main.py'))) return fromRes;

  return fromSrc; // 기본값
}

// ─── Python 실행파일 탐색 ────────────────────────────────────────
function findPython(backendDir) {
  const candidates = [
    path.join(backendDir, 'venv', 'Scripts', 'python.exe'), // Win venv
    path.join(backendDir, 'venv', 'bin', 'python3'),         // Mac/Linux venv
    path.join(backendDir, 'venv', 'bin', 'python'),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) return p;
  }
  // 시스템 Python
  for (const cmd of ['python3', 'python']) {
    try {
      execSync(`${cmd} --version`, { stdio: 'ignore' });
      return cmd;
    } catch {}
  }
  return 'python';
}

// ─── 백엔드 자동 실행 ────────────────────────────────────────────
function startBackend() {
  const backendDir = getBackendDir();
  const python     = findPython(backendDir);

  console.log(`[DaOnRoad] Backend dir: ${backendDir}`);
  console.log(`[DaOnRoad] Python:      ${python}`);
  console.log(`[DaOnRoad] main.py 존재: ${fs.existsSync(path.join(backendDir,'main.py'))}`);

  backendProc = spawn(python, ['main.py'], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
    env: { ...process.env }   // 현재 환경변수 전달
  });

  backendProc.stdout.on('data', d => {
    const msg = d.toString().trim();
    console.log(`[backend] ${msg}`);
  });
  backendProc.stderr.on('data', d => {
    const msg = d.toString().trim();
    // uvicorn 정상 로그도 stderr로 오므로 info로 처리
    console.log(`[backend:log] ${msg}`);
  });
  backendProc.on('exit', code => {
    console.log(`[DaOnRoad] 백엔드 종료 (코드: ${code})`);
    backendProc = null;
  });
  backendProc.on('error', err => {
    console.error(`[DaOnRoad] 백엔드 실행 오류: ${err.message}`);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.executeJavaScript(
        `toast('Python 백엔드 실행 실패.\\n터미널에서 직접 실행해 주세요:\\ncd backend && python main.py', 'error')`
      ).catch(() => {});
    }
  });
}

// ─── 백엔드 준비 대기 (최대 30초) ────────────────────────────────
async function waitForBackend(retries = 60, interval = 500) {
  const http = require('http');
  for (let i = 0; i < retries; i++) {
    const ok = await new Promise(resolve => {
      const req = http.get(`http://127.0.0.1:${API_PORT}/health`, res => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(400, () => { req.destroy(); resolve(false); });
    });
    if (ok) {
      console.log(`[DaOnRoad] 백엔드 준비 완료 (${(i+1)*interval/1000}초)`);
      return true;
    }
    await new Promise(r => setTimeout(r, interval));
  }
  return false;
}

// ─── 창 생성 ─────────────────────────────────────────────────────
function createWindow() {
  const iconPath   = path.join(__dirname, '..', 'assets', 'DaOnRoad.ico');
  const iconExists = fs.existsSync(iconPath);

  mainWindow = new BrowserWindow({
    width: 1440, height: 900,
    minWidth: 1100, minHeight: 700,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webSecurity: false,
    },
    title: 'DaOnRoad',
    backgroundColor: '#0f0f1a',
    show: false,
    ...(iconExists ? { icon: iconPath } : {}),
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));
  if (IS_DEV) mainWindow.webContents.openDevTools();
  mainWindow.on('closed', () => { mainWindow = null; });
}

// ─── 앱 시작 ─────────────────────────────────────────────────────
app.whenReady().then(async () => {
  startBackend();
  createWindow();

  // 백엔드 준비 확인 → UI에 상태 알림
  waitForBackend().then(ok => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    const js = ok
      ? `updateApiStatus(true)`
      : `updateApiStatus(false, '백엔드 시작 실패 — 수동 실행: cd backend && python main.py')`;
    mainWindow.webContents.executeJavaScript(js).catch(() => {});
  });
});

app.on('window-all-closed', () => {
  if (backendProc) { console.log('[DaOnRoad] 백엔드 종료'); backendProc.kill(); }
  if (process.platform !== 'darwin') app.quit();
});
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });

// ─── IPC ─────────────────────────────────────────────────────────
ipcMain.handle('save-file', async (event, { defaultName, data }) => {
  const { filePath, canceled } = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultName,
    filters: [{ name: 'Excel Files', extensions: ['xlsx'] }],
  });
  if (canceled || !filePath) return { success: false };
  fs.writeFileSync(filePath, Buffer.from(data));
  return { success: true, path: filePath };
});

ipcMain.handle('open-file', async () => {
  const { filePaths, canceled } = await dialog.showOpenDialog(mainWindow, {
    filters: [{ name: 'Excel Files', extensions: ['xlsx', 'xls'] }],
    properties: ['openFile'],
  });
  return canceled ? null : (filePaths[0] || null);
});

ipcMain.handle('get-api-port', () => API_PORT);
