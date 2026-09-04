# Performance Benchmark Report
## eval-1-polyglot-create - ✅ PASS
### Metrics & Assertions
- latency_ms: 412.52099999110214 < 500.0 -> True
- token_count: 1500 < 2500.0 -> True
- exit_code: 0 == 0 -> True
- deep_modules_found: 1 >= 1.0 -> True

## eval-2-federation-repair - ✅ PASS
### Metrics & Assertions
- pointer_shim: True == True -> True
- split_brain_warnings: 0 == 0 -> True

## eval-3-dag-cycle-detection - ✅ PASS
### Metrics & Assertions
- error_detected: expected ERR_DAG_CYCLE, got ERR_DAG_CYCLE -> True
- exit_code: 1 == 1 -> True

## eval-4-reality-drift-detection - ✅ PASS
### Metrics & Assertions
- warning_detected: expected WARN_REALITY_DRIFT, got WARN_REALITY_DRIFT -> True

