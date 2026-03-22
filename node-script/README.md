# JHCIS Summary Centralization Sync Agent

สคริปต์สำหรับดึงข้อมูล Summary จาก JHCIS MySQL Local และส่งไปยัง Central API

## โครงสร้างไฟล์

```text
node-script/
├── sync_agent.py
├── desktop_app.py
├── build_desktop.ps1
├── .env.example
├── requirements.txt
└── logs/
```

## การติดตั้ง

```powershell
cd node-script
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

## การตั้งค่า

โปรแกรมใช้ `.env` ไฟล์เดียว

ตัวอย่างค่าใน `.env`

```bash
JHCIS_DB_HOST=localhost
JHCIS_DB_PORT=3306
JHCIS_DB_USER=jhcis_user
JHCIS_DB_PASSWORD=your_password
JHCIS_DB_NAME=jhcis_db

JHCIS_API_ENDPOINT=https://central.jhcis.go.th/api/v1/summary
JHCIS_API_KEY=your-api-key

JHCIS_FACILITY_ID=YOUR_FACILITY_ID
JHCIS_FACILITY_NAME=ชื่อ รพ.สต./สถานบริการ
JHCIS_FACILITY_CODE=FACILITY_CODE

JHCIS_RETRY_ATTEMPTS=3
JHCIS_RETRY_DELAY_SECONDS=30
JHCIS_TIMEOUT_SECONDS=60
JHCIS_LOG_LEVEL=INFO
```

## การใช้งาน

Desktop App

```powershell
python desktop_app.py
```

ถ้าต้องการเปิดแบบไม่มี console บน Windows:

```powershell
pythonw desktop_app.py
```

Command Line

```powershell
python sync_agent.py
python sync_agent.py --date 2024-03-20
python sync_agent.py --summary-type OP,IP,ER
python sync_agent.py --all-types
```

Options

- `--date` วันที่ที่ต้องการ sync รูปแบบ `YYYY-MM-DD`
- `--summary-type` ระบุประเภทข้อมูลแบบคั่นด้วย comma
- `--all-types` sync ทุกประเภท
- `--env` พาธไฟล์ `.env`
- `--queries` พาธไฟล์ `queries.sql`
- `--log-dir` โฟลเดอร์เก็บ log

## Build EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\build_desktop.ps1
```

ไฟล์ที่ได้:

```text
dist\JHCISSyncDesktop\JHCISSyncDesktop.exe
```

## หมายเหตุ

- เก็บ API Key ไว้ใน `.env` และไม่ควร commit ขึ้น Git
- log จะถูกบันทึกใน `logs\sync_YYYY-MM-DD.log`
