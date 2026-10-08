#!/usr/bin/env node
/**
 * Publish the current working tree to GitHub through the REST API.
 *
 * Why this exists: on this machine `github.com:443` is routed into a black hole
 * (TCP connect hangs, or TLS is reset mid-handshake) while `api.github.com:443`
 * is reachable. `git push` therefore cannot complete even though the repository
 * and credentials are fine. This script performs the equivalent write over the
 * API, which uses a different endpoint.
 *
 * It creates ONE squashed commit representing the current tree. Full local
 * history is preserved separately in a git bundle so nothing is lost.
 *
 * Credential handling: the token is obtained from `gh auth token` at runtime,
 * held only in this process, sent only in the Authorization header, and never
 * printed, logged or written to disk.
 *
 * Usage:
 *   node scripts/publish_via_api.mjs --repo owner/name [--branch main]
 *                                    [--bundle artifacts/Quant-RSI-main.bundle]
 *                                    [--message "..."] [--dry-run]
 */
import { execFileSync } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';

const API = 'https://api.github.com';

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
}
const dryRun = process.argv.includes('--dry-run');

const repo = arg('repo');
if (!repo || !repo.includes('/')) {
  console.error('usage: --repo owner/name [--branch main] [--bundle path] [--message "..."] [--dry-run]');
  process.exit(2);
}
const [owner, name] = repo.split('/');
const branch = arg('branch', 'main');
const bundlePath = arg('bundle', null);

// Token stays in-process. execFileSync avoids shell interpolation.
function token() {
  try {
    return execFileSync('gh', ['auth', 'token'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    console.error('could not obtain a token from `gh auth token`; run `gh auth login` first');
    process.exit(3);
  }
}
const TOKEN = token();
if (!TOKEN) {
  console.error('empty token from gh; aborting');
  process.exit(3);
}

async function api(path, { method = 'GET', body } = {}) {
  const res = await fetch(API + path, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'quant-rsi-publisher',
      'Content-Type': 'application/json',
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let json;
  try { json = text ? JSON.parse(text) : {}; } catch { json = { raw: text }; }
  if (!res.ok) {
    const detail = json?.message || res.statusText;
    throw new Error(`${method} ${path} -> ${res.status} ${detail}`);
  }
  return json;
}

/** Files tracked by git: exactly what .gitignore has already vetted. */
function git(args, opts = {}) {
  return execFileSync('git', args, { encoding: 'utf8', maxBuffer: 256 * 1024 * 1024, ...opts });
}

function trackedFiles() {
  const out = git(['-c', 'core.quotepath=false', 'ls-files', '-z']);
  return out.split('\0').filter(Boolean);
}

/**
 * A brand-new GitHub repo has no git object store, so blob/tree creation is
 * rejected with 409 "Git Repository is empty". The Contents API can create the
 * very first commit, which initialises the store and the default branch.
 */
async function bootstrapIfEmpty() {
  try {
    await api(`/repos/${owner}/${name}/git/ref/heads/${branch}`);
    return false; // branch exists, nothing to do
  } catch {
    // fall through
  }
  const seed = Buffer.from(
    '# Quant-RSI\n\nInitialising commit created by scripts/publish_via_api.mjs so the git object\n' +
    'store exists. The full project tree is published in the commit that follows.\n'
  ).toString('base64');
  try {
    await api(`/repos/${owner}/${name}/contents/README.md`, {
      method: 'PUT',
      body: { message: 'chore: initialise repository', content: seed, branch },
    });
    console.log('bootstrapped empty repository via Contents API');
    return true;
  } catch (err) {
    if (/already exists|422/.test(err.message)) return false;
    throw err;
  }
}

async function main() {
  const base = await api(`/repos/${owner}/${name}`);
  console.log(`repo: ${base.full_name}  private=${base.private}  default=${base.default_branch}`);

  await bootstrapIfEmpty();

  const files = trackedFiles();
  console.log(`tracked files: ${files.length}`);

  // Optional bundle carrying the complete local history.
  const extra = [];
  if (bundlePath) {
    if (!existsSync(bundlePath)) {
      console.error(`bundle not found: ${bundlePath}`);
      process.exit(4);
    }
    extra.push({ path: bundlePath.replace(/\\/g, '/').replace(/^.*?(artifacts\/)/, '$1'), abs: bundlePath });
    console.log(`bundle: ${extra[0].path} (${readFileSync(bundlePath).length} bytes)`);
  }

  if (dryRun) {
    console.log('dry run: no API writes performed');
    return;
  }

  // Build a path -> blob sha map from the current remote tree so unchanged
  // files are reused instead of re-uploaded. Makes re-publishing cheap.
  const existing = new Map();
  try {
    const ref = await api(`/repos/${owner}/${name}/git/ref/heads/${branch}`);
    const current = await api(`/repos/${owner}/${name}/git/trees/${ref.object.sha}?recursive=1`);
    for (const entry of current.tree || []) {
      if (entry.type === 'blob') existing.set(entry.path, entry.sha);
    }
    console.log(`reusing shas from existing tree: ${existing.size} entries`);
  } catch {
    console.log('no existing tree to reuse from');
  }

  /** Compute a file's git blob sha locally, so no upload is needed to compare. */
  function localBlobSha(abs) {
    return git(['hash-object', '--', abs]).trim();
  }

  const tree = [];
  let uploaded = 0;
  let reused = 0;
  for (const rel of files) {
    const abs = rel;
    if (!existsSync(abs)) { console.log(`skip (missing): ${rel}`); continue; }
    const localSha = localBlobSha(abs);
    if (existing.get(rel) === localSha) {
      tree.push({ path: rel, mode: '100644', type: 'blob', sha: localSha });
      reused += 1;
      continue;
    }
    const content = readFileSync(abs);
    const blob = await api(`/repos/${owner}/${name}/git/blobs`, {
      method: 'POST',
      body: { content: content.toString('base64'), encoding: 'base64' },
    });
    tree.push({ path: rel, mode: '100644', type: 'blob', sha: blob.sha });
    uploaded += 1;
    if (uploaded % 25 === 0) console.log(`  uploaded ${uploaded}`);
  }
  for (const item of extra) {
    const localSha = localBlobSha(item.abs);
    if (existing.get(item.path) === localSha) {
      tree.push({ path: item.path, mode: '100644', type: 'blob', sha: localSha });
      reused += 1;
      continue;
    }
    const content = readFileSync(item.abs);
    const blob = await api(`/repos/${owner}/${name}/git/blobs`, {
      method: 'POST',
      body: { content: content.toString('base64'), encoding: 'base64' },
    });
    tree.push({ path: item.path, mode: '100644', type: 'blob', sha: blob.sha });
    uploaded += 1;
  }
  console.log(`blobs: reused ${reused}, uploaded ${uploaded}, total ${tree.length}`);

  const newTree = await api(`/repos/${owner}/${name}/git/trees`, {
    method: 'POST',
    body: { tree },
  });

  let parents = [];
  try {
    const ref = await api(`/repos/${owner}/${name}/git/ref/heads/${branch}`);
    parents = [ref.object.sha];
    console.log(`existing branch ${branch} at ${ref.object.sha.slice(0, 8)}`);
  } catch {
    console.log(`branch ${branch} does not exist yet; creating it`);
  }

  const localHead = git(['rev-parse', 'HEAD']).trim();
  const treeHash = createHash('sha256')
    .update(tree.map((t) => `${t.path}:${t.sha}`).sort().join('\n'))
    .digest('hex');

  const message = arg('message',
    `chore: publish working tree via API (local history preserved in bundle)\n\n` +
    `Published by scripts/publish_via_api.mjs because github.com:443 is unreachable\n` +
    `on this machine while api.github.com:443 is reachable.\n\n` +
    `Local HEAD: ${localHead}\nTree digest (sha256 over path:blob pairs): ${treeHash}\n` +
    `Files: ${tree.length}`);

  const commit = await api(`/repos/${owner}/${name}/git/commits`, {
    method: 'POST',
    body: { message, tree: newTree.sha, parents },
  });
  console.log(`commit: ${commit.sha}`);

  if (parents.length === 0) {
    await api(`/repos/${owner}/${name}/git/refs`, {
      method: 'POST',
      body: { ref: `refs/heads/${branch}`, sha: commit.sha },
    });
  } else {
    await api(`/repos/${owner}/${name}/git/refs/heads/${branch}`, {
      method: 'PATCH',
      body: { sha: commit.sha, force: true },
    });
  }

  const check = await api(`/repos/${owner}/${name}/git/ref/heads/${branch}`);
  console.log(`branch ${branch} now at ${check.object.sha}`);
  console.log(`done. view: https://github.com/${owner}/${name}`);
}

main().catch((err) => {
  console.error('FAILED:', err.message);
  process.exit(1);
});
