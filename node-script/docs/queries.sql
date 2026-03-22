-- QUERY: PERSON
SELECT '{hcode}' AS hcode, '{date}' AS report_date, DATE_FORMAT('{date}', '%Y-%m') AS report_period, COUNT(*) AS total_person, SUM(CASE WHEN sex = '1' THEN 1 ELSE 0 END) AS male, SUM(CASE WHEN sex = '2' THEN 1 ELSE 0 END) AS female FROM person
