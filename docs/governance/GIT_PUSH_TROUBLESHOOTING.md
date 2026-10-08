# Git 到 GitHub 的推送问题：根因与排查手册

日期：2026-10-08（2026-10-08 更新：已切换到 SSH over 443，问题解决）
适用：`D:\Claude_work_Territory\Quant-RSI` → `github.com:nekobor0/Quant-RSI`

## 当前状态：已解决

**远端已切换为 SSH（走 443 端口），`git push` 恢复正常。** 无需 VPN、无需代理、无需 API 回退。

```
origin  git@github.com:nekobor0/Quant-RSI.git
~/.ssh/config:  Host github.com → ssh.github.com:443
验证: ssh -T git@github.com → "Hi nekobor0! You've successfully authenticated"
```

**为什么这条路可行（实测数据）：**

| 通道 | 结果 |
|---|---|
| HTTPS `github.com:443` | 间歇性：同一地址曾在 5 分钟内从 `0/5 可用` 变成 `5/5 可用`，每次失败耗 ~21 秒 |
| SSH `ssh.github.com:443` | **稳定可用，一次成功** |
| SSH `github.com:22` | 也可用（但 22 端口在更多网络下会被封） |
| `api.github.com:443` | 稳定可用（回退方案） |

关键洞察：**SSH 与 HTTPS 虽然都走 443，但走的是不同的地址和协议栈** —— `ssh.github.com` 解析到 `20.205.243.160`，而 `github.com` 解析到 `20.205.243.166`。所以 HTTPS 那条路坏掉时，SSH 这条路可以完全正常。这是**换路**，不是碰运气撞窗口。

---

## 历史记录：HTTPS 路线为何失败

以下保留完整的故障分析，供将来参考或用于其他机器。

## 结论摘要（HTTPS 路线）

**根因是网络路径，不是仓库、凭据或 GitHub。**

本机 DNS 把 `github.com` 解析到 **`20.205.243.166`（GitHub 亚太边缘节点）**，
该地址在本网络下 **TCP 443 基本不可达**；而 GitHub 美国节点
（`140.82.112–116.x`）**可达**。ICMP 通（RTT ~124ms）但 TCP 443 不通，
说明不是链路中断，而是这一跳被丢弃/重置。失败是**间歇性**的，同一命令
几分钟内可能一次失败一次成功。

这一点在本机已由独立取证确认，并且是**跨会话复现的同一个问题**：
此前的 `QuantTradingSystem` 同步会话（36 轮）记录的失败签名与本轮完全一致。

## 失败签名识别（先看错误属于哪一类）

| 错误文本 | 含义 | 处置 |
|---|---|---|
| `Recv failure: Connection was reset` | 路径中有 RST 注入 | 换 VPN 节点 |
| `Failed to connect to github.com port 443 after 21xxx ms` | SYN 被丢弃，**~21.0–21.3s 是特征值** | 换 VPN 节点；此 IP 大概率不通 |
| `OpenSSL SSL_read ... unexpected eof while reading` | TCP 通但 TLS 流被切断 | 换节点 |
| `TLS connect error ... unexpected eof` | 同上，更早阶段 | 换节点 |

**重要陷阱：`exit code 1` 不代表失败。** git 会把 `To https://…` 和 GitHub 的
PR 横幅写到 stderr，PowerShell 包装器因此报 `exit code 1`，但推送其实成功了。
必须显式读真实退出码：

```powershell
git push -u origin main 2>&1; "push_exit=$LASTEXITCODE"
```

`128` 才是真失败。判断成功要看输出里有没有 `<old>..<new>  main -> main`。

## 排查步骤（按顺序，逐步升级）

### 1. 最省事的前置探测

```powershell
git ls-remote origin refs/heads/main 2>&1; "lsremote_exit=$LASTEXITCODE"
```

### 2. DNS 与路径三分

```powershell
Resolve-DnsName github.com -Type A
Test-NetConnection github.com -Port 443 -InformationLevel Detailed   # 看 TcpTestSucceeded / PingSucceeded
Test-NetConnection 140.82.114.4 -Port 443
Test-NetConnection 20.205.243.166 -Port 443
Get-DnsClientServerAddress -AddressFamily IPv4
```

判读：**ICMP 通 + TCP 443 不通 + DNS 只给一个亚太 IP ⇒ 适用下面两种修法。**

### 3. 确认美国节点是否真能用（TLS 证明）

```powershell
curl.exe -sS -o NUL -w "http_code=%{http_code}`n" --max-time 20 --resolve github.com:443:140.82.114.4 https://github.com
```

`http_code=200` → 该 IP 可用，代理法有效。
`http_code=000` → 该 IP 也不通，代理法无效，必须换 VPN 节点。

### 4. 有界盲重试（抓间歇窗口，4–5 次，间隔 6–8 秒）

```powershell
$ok=$false
foreach($i in 1..5){
  git push -u origin main >$null 2>$null
  if($LASTEXITCODE -eq 0){ "PUSH_SUCCEEDED on attempt $i"; $ok=$true; break }
  "attempt $i failed (exit $LASTEXITCODE)"; Start-Sleep -Seconds 8
}
if(-not $ok){ "PUSH_FAILED_ALL_ATTEMPTS" }
```

## 推荐修法

### 修法 A（首选，最简单）：把 VPN 切到 **全局模式**

**这是本机历史上唯一一次真正一次性解决的修法。** 此前会话记录：
「我调整了VPN端口，现在是全局模式」之后，`20.205.243.166` 从不可达**首次变为
可达**，`curl https://github.com` 返回 `200`，随后**普通 `git push` 直接成功**，
不需要任何代理。

> 注意：单纯「重新调整 VPN」或「切换节点」**不一定有效，甚至可能更差**——
> 历史记录里有一次调整后连美国节点也开始 stall。关键是**全局模式**，不是换节点。

### 修法 B（VPN 无法更改时）：本地 CONNECT 代理把 github.com 钉到美国 IP

原理：**只改 TCP 目标，TLS 仍是端到端 client↔github.com**，因此证书校验不受影响，
不是 MITM。

```python
# 存为 %TEMP%\gh_pin_proxy.py，用 python gh_pin_proxy.py <port> 启动
"""Transient local HTTP CONNECT proxy pinning github.com to a reachable IP.
TLS stays end-to-end client<->github.com; only the CONNECT TCP target changes."""
import socket, threading, sys

TARGET_MAP = {"github.com:443": ("140.82.114.4", 443)}

def pipe(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try: s.close()
            except OSError: pass

def handle(conn):
    try:
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = conn.recv(4096)
            if not chunk: return
            head += chunk
        line = head.split(b"\r\n", 1)[0].decode()
        hostport = line.split()[1]
        target = TARGET_MAP.get(hostport)
        if target is None:
            host, _, port = hostport.rpartition(":")
            target = (host, int(port))
        upstream = socket.create_connection(target, timeout=20)
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        threading.Thread(target=pipe, args=(conn, upstream), daemon=True).start()
        pipe(upstream, conn)
    except OSError:
        pass
    finally:
        try: conn.close()
        except OSError: pass

port = int(sys.argv[1])
srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", port)); srv.listen(50)
print(f"PROXY_LISTENING 127.0.0.1:{port}", flush=True)
while True:
    conn, _ = srv.accept()
    threading.Thread(target=handle, args=(conn,), daemon=True).start()
```

用法：

```powershell
$p=31288; $listen=(Get-NetTCPConnection -State Listen).LocalPort
while($listen -contains $p){ $p++ }
python "$env:TEMP\gh_pin_proxy.py" $p      # 后台作业启动，打印 PROXY_LISTENING
Start-Sleep 2; Test-NetConnection 127.0.0.1 -Port $p -InformationLevel Quiet   # 必须 True
git -c http.proxy=http://127.0.0.1:$p push -u origin main
git -c http.proxy=http://127.0.0.1:$p ls-remote origin refs/heads/main        # 服务端确认
# 用完 job_kill 并删除脚本
```

**注意**：若第 3 步 `http_code=000`，代理法同样会失败；此时只能回到修法 A。

## 已排除的方案（不要浪费时间重复）

| 方案 | 结论 |
|---|---|
| 改 hosts 文件 | **不可行**：需要管理员权限（`IsAdmin: False`），当前 ACL 不允许 |
| SSH（`ssh.github.com:443`） | 端口**通**，但本机**没有任何 SSH 密钥**（无 `.ssh` 目录） |
| `git --resolve` / `http.curloptResolve` | git 不暴露该选项，只有 curl 有 |
| `http.lowSpeedLimit=0` | 试过，无独立效果 |
| 改 remote URL | 无意义：远端正确，问题是路径 |

## 本项目的现状（2026-10-08）

因为 `github.com:443` 不通，本轮改用**可达的 `api.github.com`** 完成发布：

- 脚本：`scripts/publish_via_api.mjs`（`gh` 令牌仅在进程内读取，不打印、不落盘）
- 远端：`main` @ `2ec2de0`，**194 个 blob**，已逐文件比对 blob SHA 与本地一致
- 安全：远端**不含**受限 Tushare 原始数据、凭据或工作缓存

**已知限制：API 发布是"压平"的单一提交，丢失了本地两次提交的历史。**
本地完整历史（`bcd9354`、`7462162`、`59c657c`）保存在 Git 仓库中未受影响。
待 `github.com:443` 恢复后，执行下面命令即可把真实历史推上去，覆盖压平提交：

```powershell
git push -u origin main --force-with-lease
```

（`--force-with-lease` 是安全的：若远端在此期间被别人改动，它会拒绝而不是覆盖。）

## 附：模型 API 端点连通性（2026-10-08 实测，未使用凭据）

GitHub 的问题**不影响模型 API**：两个厂商端点在本机 TCP 443 均可达。

| 端点 | DNS | TCP 443 | 无凭据探测结果 |
|---|---|---|---|
| `api.deepseek.com` | `36.150.244.216` | OPEN | `/v1/models` → **401**；`/v1/chat/completions` POST → **401**（路径正确，仅缺认证） |
| `api.xiaomimimo.com` | — | OPEN | `/v1/models` → **401**；GET `/v1/chat/completions` → **405**（路径正确，需 POST） |
| `batch-api-cn.xiaomimimo.com` | `111.13.40.48` | OPEN | 根路径 → 200，但**所有 API 路径 → 404**（openresty 批处理服务，非 chat 接口） |

**结论：`batch-api-cn.xiaomimimo.com` 不是 OpenAI 兼容的 chat 端点**，尽管已确认
可达。`ChatProvider` 默认已改为 `https://api.xiaomimimo.com/v1`。
