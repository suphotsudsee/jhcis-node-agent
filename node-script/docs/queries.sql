-- QUERY: OP
SELECT '{hcode}' AS hcode, '{date}' AS report_date, DATE_FORMAT('{date}', '%Y-%m') AS report_period, COUNT(*) AS total_visits, COUNT(DISTINCT pid) AS unique_patients FROM visit WHERE visitdate = '{date}'
