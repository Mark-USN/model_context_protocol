Get-NetTCPConnection -LocalPort 8085 | Select-Object LocalAddress, LocalPort, State, OwningProcess
