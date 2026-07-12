-- Q3: reconciliation divergence by day (empty until a reconcile export lands)
SELECT date, stream, jsonl_usd, api_usd, divergence, classification
FROM divergence
ORDER BY date, stream;
