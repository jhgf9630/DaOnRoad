/**
 * DaOnRoad - Electron 메인 프로세스
 *
 * [배포 구조]
 *   Electron(UI) → docker compose up → Backend(FastAPI) + OSRM
 *
 * [실행 순서]
 *   1. docker compose up -d  (백엔드 + OSRM 컨테이너 시작)
 *   2. BrowserWindow 생성
 *   3. 백엔드 준비 대기 (최대 60초)
 *   4. 준비 완료 → UI에 상태 알림
 */
const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path  = require('path');
const fs    = require('fs');
const { spawn, spawnSync } = require('child_process');

const IS_DEV   = process.argv.includes('--dev');
const API_PORT = 8000;
const BACKEND_URL = `http://127.0.0.1:${API_PORT}`;

let mainWindow    = null;
let composeProc   = null;

// ─────────────────────────────────────────────────────────────────
// 프로젝트 루트 경로 계산
// 구조: DaOnRoad/frontend/src/main.js → DaOnRoad/
// ─────────────────────────────────────────────────────────────────
function getProjectRoot() {
  // 개발 환경: DaOnRoad/frontend/src/main.js → DaOnRoad/
  const devRoot = path.resolve(__dirname, '..', '..');
  if (fs.existsSync(path.join(devRoot, 'docker-compose.yml'))) return devRoot;

  // 패키징된 환경:
  // process.resourcesPath = .../DaOnRoad/resources/
  // extraResources → resources/docker-compose.yml, resources/backend/
  if (process.resourcesPath) {
    const resRoot = process.resourcesPath;
    if (fs.existsSync(path.join(resRoot, 'docker-compose.yml'))) return resRoot;
  }

  return devRoot;
}

// ─────────────────────────────────────────────────────────────────
// Docker 설치 여부 확인
// ─────────────────────────────────────────────────────────────────
function isDockerAvailable() {
  try {
    const result = spawnSync('docker', ['info'], { stdio: 'ignore', windowsHide: true, timeout: 5000 });
    return result.status === 0;
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────
// docker compose 명령어 자동 감지
// 신버전: ["docker", "compose", ...]
// 구버전: ["docker-compose", ...]
// ─────────────────────────────────────────────────────────────────
function getComposeCmd() {
  // V2: docker compose
  const v2 = spawnSync('docker', ['compose', 'version'], { stdio: 'ignore', windowsHide: true, timeout: 3000 });
  if (v2.status === 0) return { cmd: 'docker', args: ['compose'] };

  // V1: docker-compose
  const v1 = spawnSync('docker-compose', ['version'], { stdio: 'ignore', windowsHide: true, timeout: 3000 });
  if (v1.status === 0) return { cmd: 'docker-compose', args: [] };

  return null;
}

// ─────────────────────────────────────────────────────────────────
// Docker Compose 실행
// ─────────────────────────────────────────────────────────────────
function startDockerCompose() {
  const projectRoot = getProjectRoot();
  console.log(`[DaOnRoad] Project root: ${projectRoot}`);

  if (!isDockerAvailable()) {
    console.error('[DaOnRoad] Docker is not running.');
    showDockerError();
    return false;
  }

  const compose = getComposeCmd();
  if (!compose) {
    console.error('[DaOnRoad] docker compose command not found.');
    showDockerError();
    return false;
  }

  // .env 파일 존재 확인
  const envPath = path.join(projectRoot, 'backend', '.env');
  if (!fs.existsSync(envPath)) {
    console.warn('[DaOnRoad] backend/.env not found. Copy .env.example to .env');
  }

  console.log(`[DaOnRoad] Starting Docker Compose... (${compose.cmd})`);

  // docker compose up -d (백그라운드 실행)
  const composeArgs = [...compose.args, 'up', '-d', '--build'];
  composeProc = spawn(compose.cmd, composeArgs, {
    cwd: projectRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  composeProc.stdout.on('data', d => console.log(`[compose] ${d.toString().trim()}`));
  composeProc.stderr.on('data', d => console.log(`[compose] ${d.toString().trim()}`));

  composeProc.on('exit', code => {
    console.log(`[DaOnRoad] docker compose done (code: ${code})`);
    if (code !== 0) {
      showComposeError(code);
    }
  });

  composeProc.on('error', err => {
    console.error(`[DaOnRoad] docker compose error: ${err.message}`);
    showDockerError();
  });

  return true;
}

// ─────────────────────────────────────────────────────────────────
// 백엔드 준비 대기 (최대 60초)
// ─────────────────────────────────────────────────────────────────
async function waitForBackend(retries = 120, interval = 1000) {
  const http = require('http');
  for (let i = 0; i < retries; i++) {
    const ok = await new Promise(resolve => {
      const req = http.get(`${BACKEND_URL}/health`, res => {
        let body='';
        res.on('data',chunk=>{body+=chunk;if(body.length>65536)res.destroy();});
        res.on('end',()=>{try{resolve(res.statusCode===200 && JSON.parse(body).routing_jobs===true);}catch{resolve(false);}});
        res.on('error',()=>resolve(false));
      });
      req.on('error', () => resolve(false));
      req.setTimeout(800, () => { req.destroy(); resolve(false); });
    });
    if (ok) {
      console.log(`[DaOnRoad] Backend ready (${i + 1}s)`);
      return true;
    }
    if (i % 5 === 0 && i > 0) {
      console.log(`[DaOnRoad] Waiting for backend... (${i}/${retries}s)`);
    }
    await new Promise(r => setTimeout(r, interval));
  }
  return false;
}

// ─────────────────────────────────────────────────────────────────
// 오류 다이얼로그
// ─────────────────────────────────────────────────────────────────
function showDockerError() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  dialog.showMessageBox(mainWindow, {
    type: 'error',
    title: 'Docker Error',
    message: 'Docker Desktop is not running.',
    detail: [
      '1. Start Docker Desktop.',
      '2. Wait until the tray icon turns green.',
      '3. Restart DaOnRoad app.',
    ].join('\n'),
    buttons: ['Open Docker Desktop', 'Close'],
  }).then(({ response }) => {
    if (response === 0) shell.openExternal('https://www.docker.com/get-started');
  });
}

function showComposeError(code) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const projectRoot = getProjectRoot();
  dialog.showMessageBox(mainWindow, {
    type: 'warning',
    title: 'Backend Start Error',
    message: `Docker Compose failed (code: ${code})`,
    detail: [
      'Run manually to see details:',
      `  cd ${projectRoot}`,
      '  docker compose up --build',
      '',
      'Check terminal: docker compose logs -f',
    ].join('\n'),
    buttons: ['OK'],
  });
}

// ─────────────────────────────────────────────────────────────────
// 창 생성
// ─────────────────────────────────────────────────────────────────
function createWindow() {
  const iconPath   = path.join(__dirname, '..', 'assets', 'DaOnRoad.ico');
  const iconExists = fs.existsSync(iconPath);

  mainWindow = new BrowserWindow({
    width: 1440, height: 900,
    minWidth: 1100, minHeight: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
    },
    title: 'DaOnRoad',
    backgroundColor: '#0f0f1a',
    show: false,
    ...(iconExists ? { icon: iconPath } : {}),
  });

  mainWindow.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  mainWindow.webContents.on('will-navigate', event => event.preventDefault());
  mainWindow.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  mainWindow.once('ready-to-show', () => mainWindow.show());
  mainWindow.loadFile(path.join(__dirname, '..', 'index.html'));
  if (IS_DEV) mainWindow.webContents.openDevTools();
  mainWindow.on('closed', () => { mainWindow = null; });
}

// ─────────────────────────────────────────────────────────────────
// 앱 시작
// ─────────────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  // 1. 창 먼저 열기
  createWindow();

  // 2. Docker Compose 백그라운드 실행
  const dockerOk = startDockerCompose();

  // 3. 백엔드 준비 대기 → UI 상태 업데이트
  if (dockerOk) {
    waitForBackend().then(ok => {
      if (!mainWindow || mainWindow.isDestroyed()) return;
      const js = ok
        ? `updateApiStatus(true)`
        : `updateApiStatus(false, 'Backend timeout. Run: docker compose logs -f backend')`;
      mainWindow.webContents.executeJavaScript(js).catch(() => {});
    });
  }
});

// ─────────────────────────────────────────────────────────────────
// 앱 종료 (컨테이너는 유지 — 다음 실행 시 빠르게 재시작)
// ─────────────────────────────────────────────────────────────────
app.on('window-all-closed', () => {
  // docker compose stop (컨테이너 중지, 삭제는 안 함)
  const projectRoot = getProjectRoot();
  const stopCompose = getComposeCmd();
  console.log('[DaOnRoad] Stopping containers...');
  if (stopCompose) {
    spawnSync(stopCompose.cmd, [...stopCompose.args, 'stop'], {
      cwd: projectRoot,
      stdio: 'ignore',
      windowsHide: true,
      timeout: 10000,
    });
  }
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) { createWindow(); startDockerCompose(); }
});

// ─────────────────────────────────────────────────────────────────
// IPC 핸들러
// ─────────────────────────────────────────────────────────────────
ipcMain.handle('save-file', async (event, { defaultName, data }) => {
  if (!mainWindow || event.sender !== mainWindow.webContents || event.senderFrame !== mainWindow.webContents.mainFrame) throw new Error('Invalid sender');
  if (!Array.isArray(data) || data.length > 20 * 1024 * 1024 || !data.every(n => Number.isInteger(n) && n >= 0 && n <= 255)) throw new Error('Invalid file data');
  defaultName = path.basename(String(defaultName || 'DaOnRoad.xlsx')).replace(/[<>:"/\\|?*]/g, '_');
  const { filePath, canceled } = await dialog.showSaveDialog(mainWindow, {
    defaultPath: defaultName,
    filters: [{ name: 'Excel Files', extensions: ['xlsx'] }],
  });
  if (canceled || !filePath) return { success: false };
  fs.writeFileSync(filePath, Buffer.from(data));
  return { success: true, path: filePath };
});
