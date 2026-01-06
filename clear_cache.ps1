$paths = @(
    "cache\audio",
    "cache\transcripts",
    "cache\universal_client"
)

foreach ($path in $paths) {
    if (Test-Path $path) {
        Get-ChildItem $path -Recurse -Force |
            Remove-Item -Recurse -Force
    }
}
if (!(Test-Path "cache\mcp.pid")) {
    Remove-Item "cache\mcp.log" -Force
} 