-- Q1: session cache-health distribution + share below 85%
SELECT
    CASE
        WHEN health < 0.50 THEN '0-50%'
        WHEN health < 0.70 THEN '50-70%'
        WHEN health < 0.85 THEN '70-85%'
        WHEN health < 0.92 THEN '85-92%'
        ELSE '92-100%'
    END AS bucket,
    count(*) AS sessions,
    round(count(*) / sum(count(*)) OVER (), 3) AS share
FROM sessions
WHERE health IS NOT NULL
GROUP BY bucket
ORDER BY min(health);
