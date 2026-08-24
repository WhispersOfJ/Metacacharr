# Loki Startup Failures - Investigation Log

## Error Pattern Observed
```
level=error ts=2026-08-21T13:53:22.81275965Z caller=log.go:230 msg="error running loki" err="mkdir : no such file or directory\nerror creating index client"
```

## Key Issues
1. "mkdir : no such file or directory" - path is empty or malformed
2. "error creating index client" - store initialization failing
3. Storage initialization failing before Loki's HTTP server starts
4. Happens with boltdb storage backend

## What We Tried
- ✗ boltdb with :ro volumes
- ✗ in-memory storage with disabled WAL
- ✗ Different schema versions (v11, v13)
- ✗ Various volume mount strategies

## Hypothesis
The error message "mkdir : no such file or directory" with an empty path suggests:
- The config path resolution is broken
- Or the storage config isn't being parsed correctly
- Or boltdb 2.9.3 has a regression/incompatibility

## Next Steps to Try
1. Use Loki 2.5.0 (known stable) instead of 2.9.3
2. Minimal config with only essentials
3. Memory storage + disk cache instead of boltdb
4. Verbose logging to see what path is actually being constructed
