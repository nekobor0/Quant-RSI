#!/usr/bin/env node
/**
 * git_sync diagnose — classify why a GitHub push is or is not working, and name
 * the next action, in one call instead of a dozen probes.
 *
 * Why: across two sessions the cost was never "how do I push". It was
 *   1. re-discovering the same broken network path each session,
 *   2. blind-retrying a route that cannot work (the ~21 s connect timeout is a
 *      signature, not a blip), and
 *   3. misreading a successful push as a failure (pwsh reports exit 1 because git
 *      writes progress to stderr).
 *
 * This tool performs the diagnostic ladder, classifies the failure against known
 * signatures, and emits a structured verdict with the exact command to run next.
 *
 * Zero dependencies. Reads the token for the `gh` API probe via `gh auth token`
 * in-process only; never prints, logs or persists it.
 *
 * Usage:
 *   node tools/git_sync_diagnose.mjs [--repo owner/name] [--branch main] [--json] [--quick]
 */
import { execFileSync } from 'node:child_process';

const GITHUB_US_IPS = ['140.82.114.4', '140.82.113.4', '140.82.112.4', '140.82.116.4'];
const CONNECT_TIMEOUT_MS = 21_000; // observed characteristic value
const DEFAULT_REPO = 'nekobor0/Quant-RSI';
const DEFAULT_BRANCH = 'main';

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
}
const asJson = process.argv.includes('--json');
const quick = process.argv.includes('--quick');
const repo = arg('repo', DEFAULT_REPO);
const branch = arg('branch', DEFAULT_BRANCH);

/** Run a command, capture stdout+stderr, never throw. */
function run(cmd, args, timeout = 40_000) {
  const started = Date.now();
  try {
    const out = execFileSync(cmd, args, {
      encoding: 'utf8', timeout, stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    return { ok: true, code: 0, out: out.trim(), ms: Date.now() - started };
  } catch (err) {
    const out = `${err.stdout || ''}${err.stderr || ''}`.trim();
    return { ok: false, code: err.status ?? -1, out, ms: Date.now() - started };
  }
}

function dnsA(host) {
  const r = run('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command',
    `(Resolve-DnsName ${host} -Type A -ErrorAction SilentlyContinue | ` +
    `Where-Object { $_.IPAddress } | Select-Object -First 1).IPAddress`], 15_000);
  const ip = r.out.split(/\r?\n/).map((s) => s.trim()).filter((s) => /^\d+\.\d+\.\d+\.\d+$/.test(s))[0];
  return ip || null;
}

/** TCP reachability, measured locally so we control the timeout. */
function tcpProbe(host, port = 443, timeoutMs = CONNECT_TIMEOUT_MS) {
  const py = `
import socket, sys, time
host, port, tmo = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])/1000
t0 = time.time()
try:
    s = socket.create_connection((host, port), timeout=tmo)
    s.close()
    print("OPEN %.0f" % ((time.time()-t0)*1000))
except Exception as e:
    print("BLOCKED %.0f %s" % ((time.time()-t0)*1000, type(e).__name__))
`;
  const r = run('python', ['-c', py, host, String(port), String(timeoutMs)], timeoutMs + 10_000);
  const line = r.out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean).pop() || '';
  const [state, ms, kind] = line.split(/\s+/);
  return { state: state === 'OPEN' ? 'OPEN' : 'BLOCKED', ms: Number(ms) || null, kind: kind || null };
}

/**
 * Sample TCP repeatedly. A single probe is actively misleading on this machine:
 * the same address alternates between ~80 ms success and ~21 s timeout, so one
 * sample can report a healthy route while git is failing, or the reverse. Only a
 * repeat sample reveals the intermittency that actually governs the outcome.
 */
function tcpProbeSeries(host, samples, port = 443, timeoutMs = CONNECT_TIMEOUT_MS) {
  const py = `
import socket, sys, time
host, port, tmo, n = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])/1000, int(sys.argv[4])
for _ in range(n):
    t0 = time.time()
    try:
        s = socket.create_connection((host, port), timeout=tmo); s.close()
        print("OPEN %.0f" % ((time.time()-t0)*1000))
    except Exception:
        print("BLOCKED %.0f" % ((time.time()-t0)*1000))
`;
  const r = run('python', ['-c', py, host, String(port), String(timeoutMs), String(samples)],
    samples * (timeoutMs + 2_000));
  const rows = r.out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)
    .map((line) => {
      const [state, ms] = line.split(/\s+/);
      return { state, ms: Number(ms) || null };
    })
    .filter((x) => x.state === 'OPEN' || x.state === 'BLOCKED');
  const open = rows.filter((x) => x.state === 'OPEN');
  const times = open.map((x) => x.ms).sort((a, b) => a - b);
  return {
    host, samples: rows.length,
    open: open.length,
    blocked: rows.length - open.length,
    openRate: rows.length ? Number((open.length / rows.length).toFixed(3)) : null,
    fastestMs: times[0] ?? null,
    slowestMs: times[times.length - 1] ?? null,
    intermittent: open.length > 0 && open.length < rows.length,
    outcomes: rows.map((x) => `${x.state}${x.ms ? ':' + x.ms : ''}`),
  };
}

/** Prove a pinned IP really serves GitHub over TLS for this hostname. */
function pinnedTlsProbe(host, ip) {
  const r = run('curl.exe', ['-sS', '-o', 'NUL', '-w', '%{http_code}',
    '--max-time', '20', '--resolve', `${host}:443:${ip}`, `https://${host}`], 30_000);
  const code = (r.out.match(/\d{3}/) || [])[0] || '000';
  return { httpCode: code, usable: code === '200' };
}

function ghApiReachable() {
  const r = run('gh', ['api', '/user', '--jq', '.login'], 20_000);
  return { ok: r.ok && Boolean(r.out) && !/error/i.test(r.out), login: r.ok ? r.out : null, ms: r.ms };
}

function gitRemote() {
  const r = run('git', ['remote', 'get-url', 'origin'], 10_000);
  return r.ok ? r.out : null;
}

function gitLsRemote(branch) {
  const r = run('git', ['ls-remote', 'origin', `refs/heads/${branch}`], 45_000);
  return { ok: r.ok, sha: r.ok ? (r.out.split(/\s+/)[0] || null) : null, error: r.ok ? null : r.out, ms: r.ms };
}

const SIGNATURES = [
  { match: /Failed to connect to github\.com port 443 after (\d+) ms/i,
    kind: 'SYN_DROPPED',
    means: 'TCP SYN to the resolved github.com IP is dropped; there is no route to that edge.',
    retryable: false },
  { match: /Recv failure: Connection was reset/i,
    kind: 'RST_IN_PATH',
    means: 'A reset is injected into the path; the TCP connection is being torn down.',
    retryable: false },
  { match: /unexpected eof while reading|TLS connect error/i,
    kind: 'TLS_STREAM_KILLED',
    means: 'TCP connected but the TLS stream was cut mid-handshake or mid-transfer.',
    retryable: false },
  { match: /Proxy CONNECT aborted/i,
    kind: 'PROXY_UPSTREAM_DOWN',
    means: 'The local CONNECT proxy could not reach its pinned upstream; the pinned IP is also down.',
    retryable: false },
  { match: /Could not resolve host|Name or service not known/i,
    kind: 'DNS_FAILURE',
    means: 'DNS resolution failed outright.',
    retryable: true },
];

function classify(errorText) {
  if (!errorText) return null;
  for (const s of SIGNATURES) {
    const m = errorText.match(s.match);
    if (m) {
      return { kind: s.kind, means: s.means, retryable: s.retryable,
               measuredMs: m[1] ? Number(m[1]) : null, raw: errorText.split('\n')[0].trim() };
    }
  }
  return { kind: 'UNCLASSIFIED', means: 'Error text matched no known signature.',
           retryable: true, measuredMs: null, raw: errorText.split('\n')[0].trim() };
}

function main() {
  const steps = {};
  const notes = [];

  steps.repo = { configured: repo };
  steps.remote = { originUrl: gitRemote() };

  const resolvedIp = (steps.dns = { githubCom: dnsA('github.com'), apiGithubCom: dnsA('api.github.com') });

  // Is the API surface reachable? This is the fallback path that is independent
  // of the git transport route.
  steps.ghApi = ghApiReachable();

  if (!quick) {
    steps.probeSeries = tcpProbeSeries('github.com', 5);
    steps.probeUsIps = GITHUB_US_IPS.slice(0, 2).map((ip) => ({ ip, ...tcpProbe(ip, 443, 8_000) }));
  }

  // Only run the git-level check if the route looks plausible, to keep this fast.
  const anyUsOpen = !quick && (steps.probeUsIps || []).some((p) => p.state === 'OPEN');
  const resolvedOpen = !quick && (steps.probeSeries?.open ?? 0) > 0;

  let lsRemote = null;
  if (quick || resolvedOpen || anyUsOpen) {
    lsRemote = gitLsRemote(branch);
    steps.lsRemote = lsRemote;
  } else {
    steps.lsRemote = { skipped: true,
      reason: 'no route to any candidate IP; running ls-remote would burn another ~21 s timeout' };
  }

  // Verdict. GitHub's API and git transport resolve to different addresses, so
  // API reachability does not imply git reachability, and vice versa.
  //
  // The decisive split is whether TCP itself works. A transport reset layered on
  // top of a *working* TCP connection is a different fault from a dropped SYN:
  //   TCP blocked  -> nothing at the socket layer gets through; pinning the host
  //                   to a reachable IP can help.
  //   TCP open     -> the socket is fine, so something above it (TLS / HTTP) is
  //                   being cut. Pinning the IP cannot help, because the US IPs
  //                   are equally open. Only rerouting the traffic can.
  const failure = classify(lsRemote?.error);
  const series = steps.probeSeries;
  const tcpWorks = Boolean(anyUsOpen || (series?.open ?? 0) > 0);
  let status;
  let nextAction;
  let detail;

  if (lsRemote?.ok) {
    status = 'PUSH_PATH_OK';
    nextAction = `git push -u origin ${branch}`;
    detail = `git ls-remote succeeded; origin/${branch} is at ${lsRemote.sha}.`;
  } else if (steps.ghApi.ok) {
    status = 'PUSH_BLOCKED_API_OK';
    nextAction = `node tools/publish_via_api.mjs --repo ${repo} --branch ${branch}`;
    detail = 'The git transport route is unusable, but api.github.com is reachable. ' +
             'Publishing through the REST API works and does not need the VPN. ' +
             'Caveat: an API publish is a flattened single commit and does not carry local history.';
  } else {
    status = 'FULLY_BLOCKED';
    nextAction = 'Change the VPN to GLOBAL mode (this is the fix that has actually worked), then re-run this diagnostic.';
    detail = 'Neither the git transport nor api.github.com is reachable.';
  }

  // Name the transport-level failure and whether retrying can help.
  if (!lsRemote?.ok && failure) {
    notes.push(`transport failure: ${failure.kind} — ${failure.means}`);
    if (series?.intermittent) {
      notes.push(`The route is INTERMITTENT, not dead: TCP to github.com succeeded ${series.open}/${series.samples} ` +
                 `times (${series.fastestMs}–${series.slowestMs} ms across successes). A single probe is therefore ` +
                 'unreliable in both directions — it can report a healthy route while git fails, or the reverse.');
      notes.push('Because a success window exists, BOUNDED RETRY IS THE CORRECT FIRST MOVE here ' +
                 '(4–5 attempts, ~8 s apart). Do not conclude "blocked" from one failure.');
    } else if ((series?.open ?? 0) === 0 && !anyUsOpen) {
      notes.push('Every probe failed, so the route appears genuinely blocked rather than intermittent.');
    }
    if (failure.kind === 'RST_IN_PATH' || failure.kind === 'TLS_STREAM_KILLED') {
      notes.push('git reached the TLS layer (certificate presented, request headers sent) before the peer reset. ' +
                 'The reset lands after the request, which points at connection-level interference rather than a bad IP. ' +
                 'Pinning github.com to a US IP does not address this: those IPs are equally reachable and equally reset.');
      notes.push('It also explains why the earlier CONNECT-proxy workaround only sometimes worked — it was riding the ' +
                 'same intermittent windows, not fixing the route.');
      notes.push('Effective options, in order: bounded retry (cheap, often enough); VPN in GLOBAL mode (the one change ' +
                 'that has actually fixed the route); publish through api.github.com.');
    } else if (failure.kind === 'SYN_DROPPED') {
      notes.push('The connect attempt consumed the full ~21 s budget without a SYN-ACK, i.e. a timeout rather than a reset. ' +
                 'On this machine both signatures occur against the same address, so classify per attempt, not per host.');
    }

    // Route-specific guidance: the resolved address and the US addresses can be
    // in opposite states, which is the case that makes IP pinning worthwhile.
    if ((series?.open ?? 0) === 0 && anyUsOpen) {
      notes.push('ROUTE SPLIT: the resolved github.com address is refusing connections while the US addresses accept them. ' +
                 'This is the one situation where pinning github.com to a reachable US IP is the applicable workaround, ' +
                 'because it changes which address git talks to.');
      notes.push('Before spending effort on that proxy, note the API path is already working and needs no proxy at all.');
    }
  }
  if (failure?.measuredMs && Math.abs(failure.measuredMs - CONNECT_TIMEOUT_MS) < 2500) {
    notes.push(`The ${failure.measuredMs} ms connect time matches this machine's characteristic dead-route signature (~21 s).`);
  }
  if (steps.ghApi.ok) {
    notes.push('Note: api.github.com resolves separately from github.com here, so git transport can be dead while the API works.');
  }
  notes.push('Trap: a successful `git push` can still surface as exit code 1 under pwsh, because git writes progress to stderr. Confirm success from the `old..new  branch -> branch` line or by re-running ls-remote, not from the exit code alone.');

  const report = {
    tool: 'git_sync_diagnose',
    generatedAt: new Date().toISOString(),
    repo, branch,
    status, nextAction, detail, notes,
    classification: failure,
    probes: steps,
    doNotRetry: failure && !failure.retryable
      ? (tcpWorks
        ? ['plain git push on the current route (the reset is above TCP; the route, not the IP, is the problem)',
           'pinning github.com to a US IP (those IPs are equally reachable and equally reset)']
        : ['plain git push on the current route (TCP is blocked)',
           'a local CONNECT proxy whose pinned IP probe shows BLOCKED'])
      : [],
    ruledOut: [
      'editing the hosts file (needs elevation; BUILTIN\\Users lacks write)',
      'SSH to ssh.github.com:443 (port is open but this machine has no SSH key)',
      'git --resolve / http.curloptResolve (git does not expose it; only curl does)',
      'http.lowSpeedLimit=0 (no independent effect)',
      'changing the remote URL (the remote is correct; the route is the problem)',
    ],
  };

  if (asJson) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`status: ${status}`);
    console.log(`next  : ${nextAction}`);
    console.log(`why   : ${detail}`);
    if (failure) console.log(`fail  : ${failure.kind} (${failure.raw})`);
    console.log('');
    for (const n of notes) console.log(`- ${n}`);
    console.log('');
    console.log('probes:');
    console.log(`  dns github.com        : ${steps.dns.githubCom}`);
    console.log(`  dns api.github.com    : ${steps.dns.apiGithubCom}`);
    if (steps.probeSeries) {
      console.log(`  tcp github.com:443    : ${steps.probeSeries.open}/${steps.probeSeries.samples} open` +
                  `${steps.probeSeries.intermittent ? '  <-- INTERMITTENT' : ''}` +
                  (steps.probeSeries.outcomes ? `  [${steps.probeSeries.outcomes.join(', ')}]` : ''));
    }
    if (steps.probeUsIps) for (const p of steps.probeUsIps) console.log(`  tcp ${p.ip.padEnd(15)} : ${p.state} (${p.ms} ms)`);
    console.log(`  gh api /user          : ${steps.ghApi.ok ? 'OK as ' + steps.ghApi.login : 'FAILED'}`);
    console.log(`  git ls-remote         : ${steps.lsRemote.ok ? 'OK @ ' + steps.lsRemote.sha : (steps.lsRemote.skipped ? 'skipped' : 'FAILED')}`);
  }

  process.exitCode = status === 'PUSH_PATH_OK' ? 0 : 1;
}

main();
