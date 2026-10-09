# Native Windows capability probe/launcher. ACL changes are confined to TestRoot.
param([Parameter(Mandatory=$true)][string]$TestRoot)
$ErrorActionPreference = 'Stop'
$testPath = [IO.Path]::GetFullPath($TestRoot)
$workspacePath = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $testPath.StartsWith($workspacePath + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase)) { throw 'TestRoot must be inside workspace' }
if ([IO.Path]::GetDirectoryName($testPath) -ne $workspacePath -or
        -not [IO.Path]::GetFileName($testPath).StartsWith('.d05_synthetic_probe_')) {
    throw 'TestRoot must be a dedicated direct-child synthetic probe directory'
}
if (Test-Path -LiteralPath $testPath) { throw 'TestRoot must be new' }
New-Item -ItemType Directory -Path $testPath | Out-Null
$privatePath = Join-Path $testPath 'private'
$publicPath = Join-Path $testPath 'public'
$inboxPath = Join-Path $testPath 'inbox'
foreach ($path in @($privatePath, $publicPath, $inboxPath)) {
    New-Item -ItemType Directory -Path $path | Out-Null
}
$owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
$users = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-545')
foreach ($path in @($privatePath, $publicPath, $inboxPath)) {
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($owner)
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
        $owner, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
    if ($path -ne $privatePath) {
        $rights = if ($path -eq $inboxPath) { 'Modify' } else { 'ReadAndExecute' }
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule(
            $users, $rights, 'ContainerInherit,ObjectInherit', 'None', 'Allow')))
    }
    Set-Acl -LiteralPath $path -AclObject $acl
}
[IO.File]::WriteAllText((Join-Path $privatePath 'oracle.json'), '{"synthetic_answer":17}')
[IO.File]::WriteAllText((Join-Path $publicPath 'task.json'), '{"task_id":"D05-SYN-01"}')
$workerCode = @'
param([string]$Root)
$ErrorActionPreference = 'Stop'
$result = [ordered]@{ public_read=$null; private_read=$null; restriction=$null }
$result.public_read = [IO.File]::ReadAllText((Join-Path $Root 'public/task.json'))
try { $null = [IO.File]::ReadAllText((Join-Path $Root 'private/oracle.json')); $result.private_read='READ_SUCCEEDED' }
catch { $result.private_read = [ordered]@{ exception=$_.Exception.GetType().FullName; hresult=$_.Exception.HResult; inner=$_.Exception.InnerException.GetType().FullName; inner_hresult=$_.Exception.InnerException.HResult } }
$result.restriction = (& "$env:SystemRoot/System32/whoami.exe" /all | Out-String)
[IO.File]::WriteAllText((Join-Path $Root 'inbox/probe.json'), ($result | ConvertTo-Json -Depth 8))
'@
[IO.File]::WriteAllText((Join-Path $publicPath 'worker.ps1'), $workerCode)
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.ComponentModel;
public static class D05RestrictedProcess {
 [StructLayout(LayoutKind.Sequential)] struct SID_AND_ATTRIBUTES { public IntPtr Sid; public uint Attributes; }
 [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct STARTUPINFO { public int cb; public string reserved, desktop, title; public uint x,y,xsize,ysize,xchars,ychars,fill,flags; public ushort show, reserved2; public IntPtr reservedPtr,input,output,error; }
 [StructLayout(LayoutKind.Sequential)] struct PROCESS_INFORMATION { public IntPtr process,thread; public uint pid,tid; }
 [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
 [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
 [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h,uint ms);
 [DllImport("kernel32.dll")] static extern bool GetExitCodeProcess(IntPtr h,out uint code);
 [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr h,uint code);
 [DllImport("advapi32.dll", SetLastError=true)] static extern bool OpenProcessToken(IntPtr p,uint access,out IntPtr token);
 [DllImport("advapi32.dll", SetLastError=true)] static extern bool CreateRestrictedToken(IntPtr token,uint flags,uint disable,IntPtr disabled,uint del,IntPtr deleted,uint count,[In] SID_AND_ATTRIBUTES[] restricted,out IntPtr result);
 [DllImport("advapi32.dll", SetLastError=true)] static extern bool GetTokenInformation(IntPtr token,int kind,IntPtr buffer,int size,out int needed);
 [DllImport("advapi32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcessAsUser(IntPtr token,string application,System.Text.StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,uint flags,IntPtr environment,string cwd,ref STARTUPINFO si,out PROCESS_INFORMATION pi);
 static void Check(bool ok,string operation) { if(!ok) throw new Win32Exception(Marshal.GetLastWin32Error(),operation); }
 public static string Launch(string root,string executable,string command,string environment) {
   IntPtr token=IntPtr.Zero, restricted=IntPtr.Zero,env=IntPtr.Zero,groupsBuffer=IntPtr.Zero;
   PROCESS_INFORMATION pi=new PROCESS_INFORMATION();
   try {
     Check(OpenProcessToken(GetCurrentProcess(),0x000B,out token),"OpenProcessToken");
     // Restrict to existing group SIDs (including the logon SID), excluding the
     // user's own SID. Private ACL grants only that excluded user SID. No host
     // desktop/runtime ACL is modified to make a worker launch succeed.
     int needed; GetTokenInformation(token,2,IntPtr.Zero,0,out needed);
     groupsBuffer=Marshal.AllocHGlobal(needed);
     Check(GetTokenInformation(token,2,groupsBuffer,needed,out needed),"GetTokenInformation");
     int count=Marshal.ReadInt32(groupsBuffer), size=Marshal.SizeOf(typeof(SID_AND_ATTRIBUTES));
     var groups=new SID_AND_ATTRIBUTES[count];
     for(int i=0;i<count;i++) {
       var item=(SID_AND_ATTRIBUTES)Marshal.PtrToStructure(IntPtr.Add(groupsBuffer,(IntPtr.Size==8?8:4)+i*size),typeof(SID_AND_ATTRIBUTES));
       groups[i]=new SID_AND_ATTRIBUTES{Sid=item.Sid,Attributes=0};
     }
     Check(CreateRestrictedToken(token,1,0,IntPtr.Zero,0,IntPtr.Zero,(uint)count,groups,out restricted),"CreateRestrictedToken");
     var si=new STARTUPINFO();si.cb=Marshal.SizeOf(si);si.flags=1;si.show=0;
     env=Marshal.StringToHGlobalUni(environment);
     Check(CreateProcessAsUser(restricted,executable,new System.Text.StringBuilder(command),IntPtr.Zero,IntPtr.Zero,false,0x08000400,env,root,ref si,out pi),"CreateProcessAsUser");
     if(WaitForSingleObject(pi.process,30000)!=0) { TerminateProcess(pi.process,124); throw new Exception("WORKER_TIMEOUT"); }
     uint code; Check(GetExitCodeProcess(pi.process,out code),"GetExitCodeProcess");
     return "{\"worker_pid\":"+pi.pid+",\"exit_code\":"+code+",\"restriction\":\"group SIDs only; user SID excluded\",\"inherited_handles\":false}";
   } finally { if(pi.thread!=IntPtr.Zero)CloseHandle(pi.thread);if(pi.process!=IntPtr.Zero)CloseHandle(pi.process);if(restricted!=IntPtr.Zero)CloseHandle(restricted);if(token!=IntPtr.Zero)CloseHandle(token);if(env!=IntPtr.Zero)Marshal.FreeHGlobal(env);if(groupsBuffer!=IntPtr.Zero)Marshal.FreeHGlobal(groupsBuffer); }
 }
}
'@
$executable = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
$command = '"' + $executable + '" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    (Join-Path $publicPath 'worker.ps1') + '" -Root "' + $testPath + '"'
# Explicit clean environment; no credentials or inherited user environment.
$environment = 'SystemRoot=' + $env:SystemRoot + [char]0 + 'WINDIR=' + $env:SystemRoot + [char]0 +
    'PATH=' + (Join-Path $env:SystemRoot 'System32') + [char]0 + 'TEMP=' + $inboxPath + [char]0 +
    'TMP=' + $inboxPath + [char]0 + [char]0
try {
    $launch = [D05RestrictedProcess]::Launch($publicPath, $executable, $command, $environment) | ConvertFrom-Json
    $report = [ordered]@{ status='PROBE_EXECUTED'; launch=$launch; custodian_sid=$owner.Value }
    if (Test-Path -LiteralPath (Join-Path $inboxPath 'probe.json')) {
        $report.worker = Get-Content -LiteralPath (Join-Path $inboxPath 'probe.json') -Raw | ConvertFrom-Json
    } else {
        $report.status = 'BLOCKED_ENVIRONMENT_CAPABILITY'
        $report.reason = 'Restricted child terminated before producing a permission probe receipt'
    }
} catch {
    $errorObject = $_.Exception
    while ($errorObject.InnerException) { $errorObject=$errorObject.InnerException }
    $report = [ordered]@{ status='BLOCKED_ENVIRONMENT_CAPABILITY'; operation='restricted_process_launch';
        error_type=$errorObject.GetType().FullName; native_error=$errorObject.NativeErrorCode;
        message=$errorObject.Message; custodian_sid=$owner.Value }
}
[IO.File]::WriteAllText((Join-Path $testPath 'environment_probe.json'), ($report | ConvertTo-Json -Depth 12))
$report | ConvertTo-Json -Depth 12
if ($report.status -eq 'BLOCKED_ENVIRONMENT_CAPABILITY') { exit 2 }
