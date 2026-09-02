/**
 * 铃兰图标流水线 Node 工作进程。
 *
 * 设计要点：
 * - 图像处理逻辑不在这里重写，而是调用项目里已有的 4 个 Python 脚本。那些脚本是
 *   这条流水线的事实标准（缩放/抠图/避让规则都在里面调校过），复制一份到插件里
 *   迟早两边不一致。
 * - Python 用本机的：插件包不允许捆绑运行时，也不允许安装时 pip install。
 *   所以启动前先自检，缺什么直接告诉用户怎么装，而不是抛一堆 traceback。
 */
const readline = require('node:readline');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

function reply(message) {
  process.stdout.write(JSON.stringify(message) + '\n');
}

function notify(method, params) {
  reply({ jsonrpc: '2.0', method, params });
}

/** 依次试这些命令，找一个真的能跑起来的 Python。 */
const PYTHON_CANDIDATES = process.platform === 'win32'
  ? [['py', ['-3']], ['python', []], ['python3', []]]
  : [['python3', []], ['python', []]];

const REQUIRED_MODULES = ['PIL', 'numpy', 'scipy'];

function runProcess(cmd, args, options = {}) {
  return new Promise((resolve) => {
    let child;
    try {
      child = spawn(cmd, args, { cwd: options.cwd, windowsHide: true });
    } catch (err) {
      resolve({ code: -1, stdout: '', stderr: String(err && err.message || err), spawnFailed: true });
      return;
    }
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (buf) => {
      const text = buf.toString('utf8');
      stdout += text;
      // 往 stderr 打一份，宿主把"有动静"当续期信号，长任务不会被误判超时
      process.stderr.write(text);
      if (options.progressMethod) notify(options.progressMethod, { chunk: text });
    });
    child.stderr.on('data', (buf) => {
      const text = buf.toString('utf8');
      stderr += text;
      process.stderr.write(text);
    });
    child.on('error', (err) => {
      resolve({ code: -1, stdout, stderr: stderr + String(err && err.message || err), spawnFailed: true });
    });
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

let cachedPython = null;

/** 找到一个装齐了依赖的 Python，结果缓存在进程里。 */
async function resolvePython() {
  if (cachedPython) return cachedPython;

  const probe = 'import PIL, numpy, scipy, sys; print(sys.executable)';
  const tried = [];
  for (const [cmd, baseArgs] of PYTHON_CANDIDATES) {
    const found = await runProcess(cmd, [...baseArgs, '-c', probe]);
    if (found.code === 0) {
      cachedPython = { cmd, baseArgs, executable: found.stdout.trim() };
      return cachedPython;
    }
    // 区分"没这个 Python"和"有 Python 但缺库"——后者对用户更有用
    const exists = await runProcess(cmd, [...baseArgs, '-c', 'import sys; print(sys.version)']);
    tried.push({
      command: [cmd, ...baseArgs].join(' '),
      found: exists.code === 0,
      detail: exists.code === 0
        ? '找到 Python，但缺依赖：' + (found.stderr.trim().split('\n').pop() || '未知')
        : '没找到这个命令',
    });
  }

  const err = new Error(
    '找不到可用的 Python。需要 Python 3 且装好 pillow / numpy / scipy。\n'
    + '安装依赖：pip install pillow numpy scipy\n'
    + '尝试过：\n' + tried.map((t) => `  - ${t.command}：${t.detail}`).join('\n')
  );
  err.code = 'PYTHON_NOT_AVAILABLE';
  err.data = { tried, requiredModules: REQUIRED_MODULES };
  throw err;
}

function requireDir(dir, label) {
  if (!dir) {
    const err = new Error(`缺少 ${label}，且没能拿到当前工作目录。请在参数里明确传 project_dir。`);
    err.code = 'PROJECT_DIR_MISSING';
    throw err;
  }
  if (!fs.existsSync(dir) || !fs.statSync(dir).isDirectory()) {
    const err = new Error(`${label} 不是一个存在的目录：${dir}`);
    err.code = 'PROJECT_DIR_INVALID';
    throw err;
  }
  return dir;
}

/** 流水线里 4 个脚本的位置，全部相对项目根目录。 */
const SCRIPTS = {
  skill: path.join('技能图标', '处理脚本或素材', 'normalize_skill_icon.py'),
  buff: path.join('Buff-Debuff', '合成脚本', 'composite_buff_icons.py'),
  chart: path.join('图文技能对照表', 'generate_comparison_chart.py'),
  package: path.join('最终输出', 'package_character.py'),
};

function requireScript(projectDir, key) {
  const rel = SCRIPTS[key];
  const abs = path.join(projectDir, rel);
  if (!fs.existsSync(abs)) {
    const err = new Error(
      `在项目里找不到脚本 ${rel}。\n`
      + `确认 project_dir 指向的是图标流水线仓库根目录（里面应该有 技能图标/、Buff-Debuff/ 等子目录）。\n`
      + `当前 project_dir：${projectDir}`
    );
    err.code = 'SCRIPT_NOT_FOUND';
    err.data = { expected: rel, projectDir };
    throw err;
  }
  return abs;
}

/** 跑一个脚本，把 stdout/stderr 原样带回去——脚本自己打的 [OK]/[MISS] 就是最好的报告。 */
async function runScript(projectDir, key, args = [], env = {}) {
  const python = await resolvePython();
  const scriptPath = requireScript(projectDir, key);
  const result = await runProcess(
    python.cmd,
    [...python.baseArgs, scriptPath, ...args],
    { cwd: path.dirname(scriptPath), progressMethod: 'progress' }
  );

  const stdout = result.stdout.trim();
  const stderr = result.stderr.trim();
  if (result.code !== 0) {
    const err = new Error(
      `脚本执行失败（退出码 ${result.code}）：${path.basename(scriptPath)}\n`
      + (stderr || stdout || '（脚本没有输出）')
    );
    err.code = 'SCRIPT_FAILED';
    err.data = { exitCode: result.code, stdout, stderr, script: SCRIPTS[key] };
    throw err;
  }
  return { stdout, stderr, script: SCRIPTS[key], python: python.executable };
}

/** 解析脚本 stdout 里的 [OK] / [MISS] 行，给 Agent 一个结构化摘要。 */
function summarizeLines(stdout) {
  const lines = stdout.split('\n').map((l) => l.trim()).filter(Boolean);
  return {
    ok: lines.filter((l) => l.startsWith('[OK]')).length,
    missing: lines.filter((l) => l.startsWith('[MISS]')),
    lines,
  };
}

const OVERSCAN_MARKER = 'OVERSCAN_PX';

/**
 * 临时改脚本里的 OVERSCAN_PX 再跑，跑完还原。
 * 不直接给脚本加命令行参数，是为了让插件对脚本保持只读——用户手工跑脚本的行为不受影响。
 */
async function withOverscan(projectDir, overscanPx, fn) {
  if (overscanPx === undefined || overscanPx === null) return fn();

  const value = Number(overscanPx);
  if (!Number.isFinite(value) || value < 0 || value > 8) {
    const err = new Error(`overscan_px 应该是 0~8 之间的数字，收到：${overscanPx}`);
    err.code = 'INVALID_OVERSCAN';
    throw err;
  }

  const scriptPath = requireScript(projectDir, 'skill');
  const original = fs.readFileSync(scriptPath, 'utf8');
  const pattern = new RegExp(`^(${OVERSCAN_MARKER}\\s*=\\s*)([0-9.]+)`, 'm');
  if (!pattern.test(original)) {
    const err = new Error(
      `脚本里找不到 ${OVERSCAN_MARKER} 这一行，可能是旧版本脚本。请先更新 normalize_skill_icon.py。`
    );
    err.code = 'OVERSCAN_NOT_SUPPORTED';
    throw err;
  }

  const patched = original.replace(pattern, `$1${value}`);
  if (patched === original) return fn();

  fs.writeFileSync(scriptPath, patched, 'utf8');
  try {
    return await fn();
  } finally {
    fs.writeFileSync(scriptPath, original, 'utf8');
  }
}

const HANDLERS = {
  async check_env(params) {
    const projectDir = requireDir(params.projectDir, 'project_dir');
    const report = { projectDir, python: null, scripts: {}, circleMask: null, characters: {} };

    try {
      const python = await resolvePython();
      report.python = { ok: true, executable: python.executable, command: [python.cmd, ...python.baseArgs].join(' ') };
    } catch (err) {
      report.python = { ok: false, code: err.code, message: err.message, tried: err.data?.tried };
    }

    for (const [key, rel] of Object.entries(SCRIPTS)) {
      report.scripts[key] = { path: rel, exists: fs.existsSync(path.join(projectDir, rel)) };
    }

    const maskPath = path.join(projectDir, '技能图标', '处理脚本或素材', '圆形通道贴图.png');
    report.circleMask = {
      path: path.relative(projectDir, maskPath),
      exists: fs.existsSync(maskPath),
      note: fs.existsSync(maskPath)
        ? '就位，技能图标会走通道贴图模式（圆内像素原样保留）。'
        : '缺失，技能图标会退回按色差抠图，圆内接近背景色的白色高光会被误擦。',
    };

    // 顺便报一下有哪些角色可用，省得用户猜名字
    for (const [label, rel] of [['skill', path.join('技能图标', '角色原图')], ['buff', path.join('Buff-Debuff', '角色原图')]]) {
      const dir = path.join(projectDir, rel);
      report.characters[label] = fs.existsSync(dir)
        ? fs.readdirSync(dir).filter((n) => fs.statSync(path.join(dir, n)).isDirectory())
        : [];
    }

    return report;
  },

  async normalize_skill_icons(params) {
    const projectDir = requireDir(params.projectDir, 'project_dir');
    if (!params.character) {
      const err = new Error('缺少 character 参数。');
      err.code = 'MISSING_CHARACTER';
      throw err;
    }
    const run = await withOverscan(projectDir, params.overscanPx, () =>
      runScript(projectDir, 'skill', [String(params.character)])
    );
    const summary = summarizeLines(run.stdout);
    return {
      character: params.character,
      overscanPx: params.overscanPx ?? '脚本默认值',
      generated: summary.ok,
      missing: summary.missing,
      outputDir: path.join('技能图标', '合成成品', String(params.character)),
      log: run.stdout,
    };
  },

  async composite_buff_icons(params) {
    const projectDir = requireDir(params.projectDir, 'project_dir');
    // 这个脚本没有角色参数，它按 characters.json 跑全部角色
    const run = await runScript(projectDir, 'buff');
    const summary = summarizeLines(run.stdout);
    return {
      note: '这个脚本按 characters.json 里配置的所有角色跑，不接受单角色参数。',
      generated: summary.ok,
      missing: summary.missing,
      outputDir: path.join('Buff-Debuff', '合成成品'),
      log: run.stdout,
    };
  },

  async generate_comparison_chart(params) {
    const projectDir = requireDir(params.projectDir, 'project_dir');
    if (!params.character) {
      const err = new Error('缺少 character 参数。');
      err.code = 'MISSING_CHARACTER';
      throw err;
    }
    const run = await runScript(projectDir, 'chart', [String(params.character)]);
    return {
      character: params.character,
      outputDir: path.join('图文技能对照表', String(params.character)),
      log: run.stdout,
    };
  },

  async package_character(params) {
    const projectDir = requireDir(params.projectDir, 'project_dir');
    if (!params.character) {
      const err = new Error('缺少 character 参数。');
      err.code = 'MISSING_CHARACTER';
      throw err;
    }
    const run = await runScript(projectDir, 'package', [String(params.character)]);
    return {
      character: params.character,
      outputDir: path.join('最终输出', String(params.character)),
      note: '只复制不重新生成；目标目录不会被清空，改过命名规则的话旧文件需要手工删。',
      log: run.stdout,
    };
  },
};

readline.createInterface({ input: process.stdin }).on('line', async function (line) {
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    reply({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } });
    return;
  }

  const handler = HANDLERS[request.method];
  if (!handler) {
    reply({ jsonrpc: '2.0', id: request.id, error: { code: -32601, message: 'Method not found' } });
    return;
  }

  try {
    const result = await handler(request.params || {});
    reply({ jsonrpc: '2.0', id: request.id, result });
  } catch (err) {
    reply({
      jsonrpc: '2.0',
      id: request.id,
      error: {
        code: -32000,
        message: String(err && err.message || err),
        data: { errorCode: err && err.code, ...(err && err.data ? { detail: err.data } : {}) },
      },
    });
  }
});
