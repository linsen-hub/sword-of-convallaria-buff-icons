/**
 * 铃兰图标流水线 —— 沙箱电子脑。
 *
 * 这一层只做三件事：定位项目根目录、把调用转给 Node 工作进程、把结果整理回 Agent。
 * 真正的活（跑 Python 脚本）在 node/worker.cjs 里，因为沙箱本身没有文件系统和子进程。
 */

const TOOLS = [
  'check_env',
  'normalize_skill_icons',
  'composite_buff_icons',
  'generate_comparison_chart',
  'package_character',
];

/**
 * 决定用哪个目录当项目根。
 * 优先用调用方明确传的 project_dir；否则用宿主铸造的会话工作目录。
 * 远程会话（SSH 工作区）的 workdir 是远端路径，拿到本机来读写就是事故，所以直接拒。
 */
function resolveProjectDir(args) {
  if (args.project_dir) {
    return { dir: String(args.project_dir), source: '参数 project_dir' };
  }

  const ctx = args.session_context;
  if (!ctx || !ctx.workdir) {
    return {
      error: {
        code: 'PROJECT_DIR_UNKNOWN',
        message: '拿不到当前工作目录，请在参数里明确传 project_dir（图标流水线仓库根目录的绝对路径）。',
      },
    };
  }
  if (!ctx.workdir_is_local) {
    return {
      error: {
        code: 'WORKDIR_NOT_LOCAL',
        message: '当前会话的工作目录不在本机（可能是 SSH 远程工作区），这个插件需要读写本机文件。'
          + '请在本机会话里使用，或明确传一个本机路径的 project_dir。',
      },
    };
  }
  return { dir: ctx.workdir, source: '当前会话工作目录' };
}

/** 只有会改文件的工具需要写权限；check_env 是只读的，只读会话里也该能跑。 */
const READ_ONLY_TOOLS = new Set(['check_env']);

function checkWritable(tool, args) {
  if (READ_ONLY_TOOLS.has(tool)) return null;
  const ctx = args.session_context;
  // 只有在用宿主 workdir 时才受这条裁决约束；用户明确给了 project_dir 就按他说的算
  if (!args.project_dir && ctx && ctx.workdir_is_read_only) {
    return {
      code: 'WORKDIR_READ_ONLY',
      message: '当前会话是只读状态，不能生成或覆盖图标文件。请先解除只读，或改用 check_env 只做检查。',
    };
  }
  return null;
}

cindy.onHostMessage(async function (msg) {
  if (msg.type !== 'tool-call' || !TOOLS.includes(msg.tool)) return;

  const args = msg.args || {};

  const fail = (errorCode, message) => cindy.send({
    type: 'tool-result', callId: msg.callId, ok: false, errorCode, message,
  });

  const writeBlocked = checkWritable(msg.tool, args);
  if (writeBlocked) {
    await fail(writeBlocked.code, writeBlocked.message);
    return;
  }

  const resolved = resolveProjectDir(args);
  if (resolved.error) {
    await fail(resolved.error.code, resolved.error.message);
    return;
  }

  const params = { projectDir: resolved.dir };
  if (args.character !== undefined) params.character = args.character;
  if (args.overscan_px !== undefined) params.overscanPx = args.overscan_px;

  const response = await cindy.node.request({
    method: msg.tool,
    params,
    // 一次可能处理十几张 1024x1024 的图，给足时间；沉默 90 秒才判死，有输出就续期
    timeoutMs: 90000,
    maxTotalMs: 600000,
  });

  if (!response.ok) {
    await fail('NODE_REQUEST_FAILED', response.message);
    return;
  }

  await cindy.send({
    type: 'tool-result',
    callId: msg.callId,
    ok: true,
    result: { projectDir: resolved.dir, projectDirSource: resolved.source, ...response.result },
  });
});
