Get-CimInstance Win32_Process |
  Where-Object {
    $_.CommandLine -match "modules\.mcp_servers\.(demo_server|long_job_server)"
  } |
  Select-Object ProcessId, ParentProcessId, Name, CommandLine
