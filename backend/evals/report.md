# Eval Report

Generated on: 2026-06-15

| run | ticker | period | iters | tools | faithfulness | structure | status |
| --- | ------ | ------ | ----- | ----- | ------------ | --------- | ------ |
| aapl_1y | AAPL | 1y | 10 | 9 | 100% | 100% | PASS |
| aapl_3mo | AAPL | 3mo | 4 | 5 | 100% | 100% | PASS |
| msft_6mo | MSFT | 6mo | 6 | 9 | 100% | 100% | PASS |
| nvda_3mo | NVDA | 3mo | 4 | 5 | 100% | 100% | PASS |
| reliance_ns_1y | RELIANCE.NS | 1y | 10 | 9 | 100% | 100% | PASS |
| tsla_6mo | TSLA | 6mo | 8 | 7 | 100% | 100% | PASS |

## Aggregate

- Runs: 6
- Mean faithfulness: 100.0% (gate: >=95%)
- Mean structure: 100.0% (gate: >=98%)
- All pass: True
- Anomaly detector: 100% (see test_fixtures_labels.py regression)
