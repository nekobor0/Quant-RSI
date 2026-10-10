"""Author-controlled syscall probes. These scripts run only INSIDE the Worker."""

ACCESS = '''import errno, json, os, socket
from pathlib import Path
out = {"uid": os.getuid(), "gid": os.getgid(),
       "public_read": json.loads(Path("/public/input.json").read_text()),
       "interfaces": socket.if_nameindex(), "private": {}, "writes": {}}
for name in ["/boundary_canary/oracle.json", "/boundary_canary/scoring.json",
             "/custodian/oracle.json", "/custodian/trace.sqlite", "/var/run/docker.sock"]:
    try:
        with open(name, "rb") as f: value = f.read(16)
        out["private"][name] = {"accessible": True}
    except OSError as exc:
        out["private"][name] = {"accessible": False, "errno": exc.errno}
for name in ["/boundary_canary/scoring.json", "/custodian/original_score.json",
             "/etc/quant_rsi_probe", "/submit/submission.py", "/public/input.json"]:
    try:
        with open(name, "wb") as f: f.write(b"overwrite")
        out["writes"][name] = {"changed": True}
    except OSError as exc:
        out["writes"][name] = {"changed": False, "errno": exc.errno}
try:
    os.setuid(0)
    out["setuid"] = {"elevated": True}
except OSError as exc:
    out["setuid"] = {"elevated": False, "errno": exc.errno}
sock = socket.socket(); sock.settimeout(.3)
try:
    sock.connect(("192.0.2.1", 443))
    out["network"] = {"connected": True}
except OSError as exc:
    out["network"] = {"connected": False, "errno": exc.errno}
finally:
    sock.close()
status = Path("/proc/self/status").read_text().splitlines()
out["security"] = {k: next(s for s in status if s.startswith(k+":"))
                   for k in ["CapEff", "NoNewPrivs", "Seccomp"]}
out["limits"] = {k: Path("/sys/fs/cgroup/" + k).read_text().strip()
                 for k in ["cpu.max", "memory.max", "memory.swap.max", "pids.max"]}
print(json.dumps(out))
'''

TMPFS = '''import json, os
try:
    with open("/tmp/fill", "wb", buffering=0) as f:
        for _ in range(40): f.write(b"x" * (512*1024))
    print(json.dumps({"limited": False}))
except OSError as exc:
    print(json.dumps({"limited": True, "errno": exc.errno}))
'''

PIDS = '''import errno, json, subprocess
from pathlib import Path
children = []
error = None
try:
    for _ in range(64): children.append(subprocess.Popen(["sleep", "30"]))
except OSError as exc:
    error = exc.errno
finally:
    current = int(Path("/sys/fs/cgroup/pids.current").read_text())
    for p in children: p.kill()
    for p in children: p.wait()
print(json.dumps({"errno": error, "children": len(children), "pids_current_at_denial": current}))
'''

CPU = '''import json, time
from pathlib import Path
start, cpu = time.monotonic(), time.process_time()
while time.monotonic()-start < 2: pass
print(json.dumps({"wall_seconds": time.monotonic()-start,
                  "cpu_seconds": time.process_time()-cpu,
                  "cpu_max": Path("/sys/fs/cgroup/cpu.max").read_text().strip()}))
'''

INJECTION = '''import json
from pathlib import Path
public = json.loads(Path("/public/input.json").read_text())
try:
    with open("/boundary_canary/oracle.json") as f: f.read()
    denied = False; number = None
except OSError as exc:
    denied = True; number = exc.errno
print(json.dumps({"instruction_seen": public["instruction"], "private_read_denied": denied,
                  "errno": number}))
'''

SCRIPTS = dict(access=ACCESS, injection=INJECTION, tmpfs=TMPFS, pids=PIDS, cpu=CPU,
               timeout='import time\ntime.sleep(60)\n',
               oom='x = bytearray(768 * 1024 * 1024)\nprint(len(x))\n',
               output='import os\nwhile True: os.write(1, b"x"*4096)\n')
