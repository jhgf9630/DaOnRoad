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
const { spawn, execSync, spawnSync } = require('child_process');

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
  // 개발: frontend/src/main.js → ../../
  const devRoot = path.resolve(__dirname, '..', '..');
  if (fs.existsSync(path.join(devRoot, 'docker-compose.yml'))) return devRoot;

  // 패키징된 경우: app.asar 밖의 extraResources
  const resRoot = path.resolve(process.resourcesPath || __dirname, '..');
  if (fs.existsSync(path.join(resRoot, 'docker-compose.yml'))) return resRoot;

  return devRoot;
}

// ─────────────────────────────────────────────────────────────────
// Docker 설치 여부 확인
// ─────────────────────────────────────────────────────────────────
function isDockerAvailable() {
  try {
    const result = spawnSync('docker', ['info'], { stdio: 'ignore', timeout: 5000 });
    return result.status === 0;
  } catch {
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────
// Docker Compose 실행
// ─────────────────────────────────────────────────────────────────
function startDockerCompose() {
  const projectRoot = getProjectRoot();
  console.log(`[DaOnRoad] 프로젝트 루트: ${projectRoot}`);

  if (!isDockerAvailable()) {
    console.error('[DaOnRoad] Docker가 설치되지 않았거나 실행 중이 아닙니다.');
    showDockerError();
    return false;
  }

  // .env 파일 존재 확인
  const envPath = path.join(projectRoot, 'backend', '.env');
  if (!fs.existsSync(envPath)) {
    console.warn('[DaOnRoad] backend/.env 파일이 없습니다. .env.example을 복사하세요.');
  }

  console.log('[DaOnRoad] Docker Compose 시작 중...');

  // docker compose up -d (백그라운드 실행)
  composeProc = spawn('docker', ['compose', 'up', '-d', '--build'], {
    cwd: projectRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  composeProc.stdout.on('data', d => console.log(`[compose] ${d.toString().trim()}`));
  composeProc.stderr.on('data', d => console.log(`[compose] ${d.toString().trim()}`));

  composeProc.on('exit', code => {
    console.log(`[DaOnRoad] docker compose 완료 (코드: ${code})`);
    if (code !== 0) {
      showComposeError(code);
    }
  });

  composeProc.on('error', err => {
    console.error(`[DaOnRoad] docker compose 실행 오류: ${err.message}`);
    showDockerError();
  });

  return true;
}

// ─────────────────────────────────────────────────────────────────
// 백엔드 준비 대기 (최대 60초)
// ─────────────────────────────────────────────────────────────────
async function waitForBackend(retries = 60, interval = 1000) {
  const http = require('http');
  for (let i = 0; i < retries; i++) {
    const ok = await new Promise(resolve => {
      const req = http.get(`${BACKEND_URL}/health`, res => {
        resolve(res.statusCode === 200);
      });
      req.on('error', () => resolve(false));
      req.setTimeout(800, () => { req.destroy(); resolve(false); });
    });
    if (ok) {
      console.log(`[DaOnRoad] 백엔드 준비 완료 (${i + 1}초)`);
      return true;
    }
    if (i % 5 === 0 && i > 0) {
      console.log(`[DaOnRoad] 백엔드 대기 중... (${i}/${retries}초)`);
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
    title: 'Docker 오류',
    message: 'Docker가 실행되지 않았습니다.',
    detail: [
      '1. Docker Desktop을 실행하세요.',
      '2. 트레이 아이콘이 초록색이 될 때까지 기다리세요.',
      '3. 앱을 다시 시작하세요.',
    ].join('\n'),
    buttons: ['Docker Desktop 열기', '닫기'],
  }).then(({ response }) => {
    if (response === 0) shell.openExternal('https://www.docker.com/get-started');
  });
}

function showComposeError(code) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const projectRoot = getProjectRoot();
  dialog.showMessageBox(mainWindow, {
    type: 'warning',
    title: '백엔드 시작 오류',
    message: `Docker Compose 실행 실패 (코드: ${code})`,
    detail: [
      '터미널에서 직접 실행해보세요:',
      `  cd ${projectRoot}`,
      '  docker compose up --build',
      '',
      '오류 내용은 터미널 로그를 확인하세요.',
    ].join('\n'),
    buttons: ['확인'],
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
        : `updateApiStatus(false, '백엔드 시작 시간 초과\\ndocker compose up 상태를 확인하세요.')`;
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
  console.log('[DaOnRoad] 컨테이너 중지 중...');
  spawnSync('docker', ['compose', 'stop'], {
    cwd: projectRoot,
    stdio: 'ignore',
    timeout: 10000,
  });
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ─────────────────────────────────────────────────────────────────
// IPC 핸들러
// ─────────────────────────────────────────────────────────────────
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

// 컨테이너 상태 조회 (UI에서 사용 가능)
ipcMain.handle('get-docker-status', () => {
  const result = spawnSync('docker', ['compose', 'ps', '--format', 'json'], {
    cwd: getProjectRoot(),
    stdio: 'pipe',
    timeout: 5000,
  });
  try {
    return JSON.parse(result.stdout.toString());
  } catch {
    return [];
  }
});
