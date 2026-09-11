# US2 T021 evidence — three gate results

## Declared artifact only

- command: `echo declared > report.txt`
- status: `PASS`
- exit_code: `0`
- worktree_writes: `('report.txt',)`
- writes_declared: `False`

## Undeclared artifact only

- command: `echo undeclared > undeclared.txt`
- status: `DIRTIED_WORKTREE`
- exit_code: `0`
- worktree_writes: `('undeclared.txt',)`
- writes_declared: `False`

## Declared artifact and undeclared write

- command: `echo declared > report.txt; echo undeclared > undeclared.txt`
- status: `DIRTIED_WORKTREE`
- exit_code: `0`
- worktree_writes: `('report.txt', 'undeclared.txt')`
- writes_declared: `False`
