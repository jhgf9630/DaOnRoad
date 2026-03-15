/**
 * DaOnRoad - Electron 메인 프로세스
 * ✅ 핵심: 앱 시작 시 Python 백엔드를 자동으로 실행
 */
const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs   = require('fs');
const { spawn } = require('child_process');

const IS_DEV  = process.argv.includes('--dev');
const API_PORT = 8000;

let mainWindow  = null;
let backendProc = null;  // Python 프로세스 핸들

// ─────────────────────────────────────────────
// 1. 백엔드 자동 실행
// ─────────────────────────────────────────────
function startBackend() {
  // 백엔드 디렉터리: frontend/../backend
  const backendDir = path.join(__dirname, '..', '..', 'backend');

  // Python 실행파일 탐색 순서
  // 1) 가상환경 venv (Windows)
  // 2) 가상환경 venv (Mac/Linux)
  // 3) 시스템 python3
  // 4) 시스템 python
  const candidates = [
    path.join(backendDir, 'venv', 'Scripts', 'python.exe'),  // Win venv
    path.join(backendDir, 'venv', 'bin', 'python'),           // Mac/Linux venv
    'python3',
    'python',
  ];

  const pythonPath = candidates.find(p => {
    try {
      // 절대 경로면 존재 여부 확인
      if (path.isAbsolute(p)) return fs.existsSync(p);
      return true; // PATH에서 찾을 것
    } catch { return false; }
  }) || 'python';

  console.log(`[DaOnRoad] Python: ${pythonPath}`);
  console.log(`[DaOnRoad] Backend dir: ${backendDir}`);

  backendProc = spawn(pythonPath, ['main.py'], {
    cwd: backendDir,
    stdio: ['ignore', 'pipe', 'pipe'],
    // Windows에서 콘솔 창 숨기기
    windowsHide: true,
  });

  backendProc.stdout.on('data', d => console.log(`[backend] ${d.toString().trim()}`));
  backendProc.stderr.on('data', d => console.log(`[backend:err] ${d.toString().trim()}`));

  backendProc.on('exit', (code) => {
    console.log(`[DaOnRoad] 백엔드 종료 (코드: ${code})`);
    backendProc = null;
  });

  backendProc.on('error', (err) => {
    console.error(`[DaOnRoad] 백엔드 실행 실패: ${err.message}`);
    // 사용자에게 안내
    if (mainWindow) {
      mainWindow.webContents.executeJavaScript(`
        toast('❌ Python 백엔드 실행 실패: ${err.message.replace(/'/g,"\\'")}\\n백엔드를 수동으로 실행해 주세요.', 'error');
      `).catch(() => {});
    }
  });
}

// ─────────────────────────────────────────────
// 2. 백엔드가 준비될 때까지 대기 (최대 20초)
// ─────────────────────────────────────────────
async function waitForBackend(retries = 40, interval = 500) {
  const http = require('http');
  for (let i = 0; i < retries; i++) {
    const ok = await new Promise(resolve => {
      const req = http.get(`http://127.0.0.1:${API_PORT}/health`, res => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(400, () => { req.destroy(); resolve(false); });
    });
    if (ok) return true;
    await new Promise(r => setTimeout(r, interval));
  }
  return false;
}

// ─────────────────────────────────────────────
// 3. 윈도우 생성
// ─────────────────────────────────────────────
function createWindow() {
  const iconPath = path.join(__dirname, '..', 'assets', 'DaOnRoad.ico');
  const iconExists = fs.existsSync(iconPath);

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      webSecurity: false,
    },
    title: 'DaOnRoad',
    backgroundColor: '#0f0f1a',
    // 아이콘 파일이 있을 때만 설정
    ...(iconExists ? { icon: iconPath } : {}),
    // 로딩 중 흰 화면 방지
    show: false,
  });

  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));

  if (IS_DEV) mainWindow.webContents.openDevTools();

  mainWindow.on('closed', () => { mainWindow = null; });
}

// ─────────────────────────────────────────────
// 4. 앱 시작 순서
// ─────────────────────────────────────────────
app.whenReady().then(async () => {
  // 백엔드 먼저 실행
  startBackend();

  // 창은 바로 열기 (스플래시 효과)
  createWindow();

  // 백그라운드에서 백엔드 준비 대기 → 준비되면 UI에 알림
  waitForBackend().then(ok => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.executeJavaScript(
        ok
          ? `updateApiStatus(true)`
          : `updateApiStatus(false, '백엔드 시작 시간 초과 — 수동 실행 필요')`
      ).catch(() => {});
    }
  });
});

app.on('window-all-closed', () => {
  // 백엔드 프로세스 종료
  if (backendProc) {
    console.log('[DaOnRoad] 백엔드 종료 중...');
    backendProc.kill();
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ─────────────────────────────────────────────
// 5. IPC 핸들러
// ─────────────────────────────────────────────
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
