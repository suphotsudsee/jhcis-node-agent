#!/usr/bin/env python3
"""
JHCIS Summary Centralization Sync Agent
สำหรับ รพ.สต./สถานบริการ ในระบบ JHCIS

ดึงข้อมูล Summary จาก MySQL Local และส่งไปยัง Central API
"""

import argparse
import decimal
import logging
import os
import re
import sys
import time
from datetime import date as date_type, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import mysql.connector
import requests
from mysql.connector import Error
from requests.exceptions import RequestException, Timeout, ConnectionError


# ==================== Configuration ====================

DEFAULT_CONFIG = {
    "database": {
        "host": "localhost",
        "port": 3306,
        "user": "jhcis_user",
        "password": "jhcis_password",
        "database": "jhcis_db",
        "charset": "utf8mb4",
        "collation": "utf8mb4_unicode_ci"
    },
    "api": {
        "endpoint": "https://central.jhcis.go.th/api/v1/sync",
        "api_key": "your-api-key-here"
    },
    "settings": {
        "retry_attempts": 3,
        "retry_delay_seconds": 30,
        "timeout_seconds": 60,
        "batch_size": 1000,
        "log_level": "INFO"
    },
    "facility": {
        "facility_id": "YOUR_FACILITY_ID",
        "facility_name": "ชื่อ รพ.สต./สถานบริการ",
        "facility_code": "FACILITY_CODE"
    }
}

SUMMARY_TYPES = [
    "OP",        # Outpatient
    "IP",        # Inpatient
    "ER",        # Emergency
    "PP",        # Preventive & Promotive
    "Pharmacy",  # Pharmacy
    "Lab",       # Laboratory
    "Radiology", # Radiology
    "Financial", # Financial
    "Resource",  # Resource/HR
    "PERSON",    # Person registry snapshot
]

SUMMARY_TYPE_ENDPOINTS = {
    "OP": "op",
    "IP": "ip",
    "ER": "er",
    "PP": "pp",
    "Pharmacy": "pharmacy",
    "Lab": "lab",
    "Radiology": "radiology",
    "Financial": "financial",
    "Resource": "resource",
    "PERSON": "person",
}


# ==================== Logging Setup ====================

def setup_logger(log_dir: Path, date_str: str) -> logging.Logger:
    """ตั้งค่า Logger สำหรับบันทึกการ sync"""
    log_file = log_dir / f"sync_{date_str}.log"
    
    logger = logging.getLogger("jhcis_sync")
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(levelname)s: %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    return logger


# ==================== Database Connection ====================

def connect_to_database(
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None
) -> Optional[mysql.connector.MySQLConnection]:
    """เชื่อมต่อ MySQL Database"""
    try:
        connection = mysql.connector.connect(
            host=config["database"]["host"],
            port=config["database"]["port"],
            user=config["database"]["user"],
            password=config["database"]["password"],
            database=config["database"]["database"],
            use_pure=True,
        )
        return connection
    except Error as e:
        message = f"Database connection error: {e}"
        logging.error(message)
        if logger is not None:
            logger.error(message)
        return None


def load_sql_query(query_file: Path, summary_type: str) -> Optional[str]:
    """โหลด SQL Query จากไฟล์"""
    if not query_file.exists():
        logging.error(f"Query file not found: {query_file}")
        return None
    
    with open(query_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # ค้นหา query สำหรับ summary_type ที่ต้องการ
    # คาดว่าไฟล์ queries.sql มีรูปแบบ: -- QUERY: OP, IP, etc.
    queries = content.split("-- QUERY:")
    
    for query_block in queries:
        if query_block.strip().startswith(summary_type):
            # เอาส่วน header ออก
            lines = query_block.strip().split('\n', 1)
            if len(lines) > 1:
                return lines[1].strip()
    
    logging.warning(f"Query for {summary_type} not found in {query_file}")
    return None


BLOCKED_SQL_PATTERN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|grant|revoke|call|do|set|use)\b",
    re.IGNORECASE,
)


def normalize_sql(query: str) -> str:
    """Strip comments and normalize whitespace for SQL safety checks."""
    query = re.sub(r"/\*[\s\S]*?\*/", " ", query)
    query = re.sub(r"--.*$", " ", query, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", query).strip()


def is_safe_select_query(query: str) -> bool:
    """Allow only a single SELECT statement to be executed."""
    normalized = normalize_sql(query)
    if not normalized:
        return False

    if not normalized.lower().startswith("select "):
        return False

    if ";" in normalized:
        return False

    return BLOCKED_SQL_PATTERN.search(normalized) is None


def fetch_central_query(
    summary_type: str,
    config: Dict[str, Any],
    logger: logging.Logger
) -> Optional[str]:
    """Fetch the centrally managed SQL query from the API."""
    base_endpoint = config["api"]["endpoint"].rstrip("/")
    if base_endpoint.endswith("/sync"):
        queries_endpoint = f"{base_endpoint[:-5]}/queries/{SUMMARY_TYPE_ENDPOINTS.get(summary_type, summary_type.lower())}"
    else:
        queries_endpoint = f"{base_endpoint}/queries/{SUMMARY_TYPE_ENDPOINTS.get(summary_type, summary_type.lower())}"

    headers = {"X-API-Key": config["api"]["api_key"]}

    try:
        response = requests.get(queries_endpoint, headers=headers, timeout=config["settings"]["timeout_seconds"])
        if response.status_code == 200:
            payload = response.json()
            sql = payload.get("data", {}).get("sql")
            if sql and is_safe_select_query(sql):
                logger.info(f"Loaded central query for {summary_type} from API")
                return sql

            logger.error(f"Central query for {summary_type} failed SELECT-only validation")
            return None

        logger.warning(f"Central query unavailable for {summary_type}: {response.status_code} - {response.text}")
        return None
    except RequestException as e:
        logger.warning(f"Failed to fetch central query for {summary_type}: {e}")
        return None


def write_queries_file(queries_file: Path, queries_by_type: Dict[str, str]) -> None:
    """Write central queries into docs/queries.sql using the legacy section format."""
    queries_file.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for summary_type in SUMMARY_TYPES:
        query = queries_by_type.get(summary_type)
        if not query:
            continue
        blocks.append(f"-- QUERY: {summary_type}\n{query.strip()}\n")

    queries_file.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8")


def sync_central_queries_to_file(
    summary_types: List[str],
    config: Dict[str, Any],
    logger: logging.Logger,
) -> Dict[str, str]:
    """Fetch central queries from API and materialize them into docs/queries.sql."""
    queries_by_type: Dict[str, str] = {}

    for summary_type in summary_types:
        query = fetch_central_query(summary_type, config, logger)
        if query:
            queries_by_type[summary_type] = query

    if not queries_by_type:
        logger.error("No central queries were available from API")
        return {}

    queries_file = get_app_dir() / "docs" / "queries.sql"
    write_queries_file(queries_file, queries_by_type)
    logger.info(f"Saved {len(queries_by_type)} central queries to {queries_file}")
    return queries_by_type


def fetch_summary_data(
    connection: mysql.connector.MySQLConnection,
    query: str,
    date: str
) -> List[Dict[str, Any]]:
    """ดึงข้อมูล Summary จาก Database"""
    try:
        cursor = connection.cursor(dictionary=True)
        
        # แทนที่ placeholder ใน query ด้วยวันที่
        query = query.replace("{date}", date)
        query = query.replace("{hcode}", str(os.environ.get("JHCIS_FACILITY_CODE", "")))
        
        cursor.execute(query)
        results = cursor.fetchall()
        
        cursor.close()
        return results
    except Error as e:
        logging.error(f"Query execution error: {e}")
        return []


def fetch_person_summary(
    connection: mysql.connector.MySQLConnection,
    date: str,
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Build the person summary payload directly from the local person table."""
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_person,
                SUM(CASE WHEN sex = '1' THEN 1 ELSE 0 END) AS male,
                SUM(CASE WHEN sex = '2' THEN 1 ELSE 0 END) AS female
            FROM person
            """
        )
        row = cursor.fetchone() or {}
        cursor.close()

        return [{
            "hcode": config["facility"]["facility_code"],
            "report_date": date,
            "report_period": date[:7],
            "total_person": int(row.get("total_person") or 0),
            "male": int(row.get("male") or 0),
            "female": int(row.get("female") or 0),
        }]
    except Error as e:
        logging.error(f"Person summary query error: {e}")
        return []


# ==================== API Communication ====================

def send_to_central_api(
    data: List[Dict[str, Any]],
    summary_type: str,
    date: str,
    config: Dict[str, Any],
    logger: logging.Logger
) -> bool:
    """ส่งข้อมูลไปยัง Central API พร้อมระบบ Retry"""
    
    summary_endpoint = SUMMARY_TYPE_ENDPOINTS.get(summary_type)
    if not summary_endpoint:
        logger.error(f"Unsupported summary type for API send: {summary_type}")
        return False

    base_endpoint = config["api"]["endpoint"].rstrip("/")
    endpoint = f"{base_endpoint}/{summary_endpoint}"
    api_key = config["api"]["api_key"]
    retry_attempts = config["settings"]["retry_attempts"]
    retry_delay = config["settings"]["retry_delay_seconds"]
    timeout = config["settings"]["timeout_seconds"]

    if not data:
        logger.warning(f"No payload to send for {summary_type}")
        return False

    if len(data) == 1:
        payload = data[0]
    else:
        endpoint = f"{base_endpoint}/batch"
        payload = [
            {"summaryType": summary_endpoint, "data": row}
            for row in data
        ]
    
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key
    }
    
    for attempt in range(1, retry_attempts + 1):
        try:
            logger.info(f"Attempt {attempt}/{retry_attempts}: POST to {endpoint}")
            
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout
            )
            
            if response.status_code == 200:
                logger.info(f"✓ Success: {response.status_code} - {response.text}")
                return True
            elif response.status_code == 429:
                logger.warning(f"Rate limited (429). Retry-After: {response.headers.get('Retry-After', 'N/A')}")
            else:
                logger.error(f"✗ Error: {response.status_code} - {response.text}")
                
        except Timeout as e:
            logger.error(f"Attempt {attempt}: Timeout - {e}")
        except ConnectionError as e:
            logger.error(f"Attempt {attempt}: Connection error - {e}")
        except RequestException as e:
            logger.error(f"Attempt {attempt}: Request failed - {e}")
        
        if attempt < retry_attempts:
            logger.info(f"Waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)
    
    logger.error(f"Failed after {retry_attempts} attempts")
    return False


# ==================== Main Sync Logic ====================

def run_sync(
    date: str,
    summary_types: List[str],
    config: Dict[str, Any],
    query_file: Path,
    log_dir: Path,
    logger: Optional[logging.Logger] = None
) -> Dict[str, bool]:
    """รันกระบวนการ Sync สำหรับวันที่และประเภทที่กำหนด"""
    
    if logger is None:
        logger = setup_logger(log_dir, date)
    logger.info("=" * 60)
    logger.info(f"JHCIS Summary Sync Started")
    logger.info(f"Date: {date}")
    logger.info(f"Summary Types: {', '.join(summary_types)}")
    logger.info("=" * 60)
    
    # เชื่อมต่อ Database
    connection = connect_to_database(config, logger=logger)
    if not connection:
        logger.error("Failed to connect to database. Aborting.")
        return {t: False for t in summary_types}
    
    results = {}
    
    for summary_type in summary_types:
        logger.info(f"\nProcessing: {summary_type}")
        
        # โหลด Query
        query = load_sql_query(query_file, summary_type)
        if not query:
            logger.warning(f"Skipping {summary_type}: Query not found")
            results[summary_type] = False
            continue
        
        # ดึงข้อมูล
        data = fetch_summary_data(connection, query, date)
        
        if not data:
            logger.warning(f"No data found for {summary_type} on {date}")
            results[summary_type] = False
            continue
        
        logger.info(f"Fetched {len(data)} records for {summary_type}")
        
        # ส่งไปยัง API
        success = send_to_central_api(data, summary_type, date, config, logger)
        results[summary_type] = success
        
        if success:
            logger.info(f"✓ {summary_type} synced successfully")
        else:
            logger.error(f"✗ {summary_type} sync failed")
    
    connection.close()
    
    logger.info("=" * 60)
    logger.info("Sync Completed")
    success_count = sum(1 for v in results.values() if v)
    logger.info(f"Success: {success_count}/{len(summary_types)}")
    logger.info("=" * 60)
    
    return results


# ==================== Configuration Loading ====================

def merge_nested_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Merge nested dict values with override taking precedence."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merged[key] = merge_nested_dict(base[key], value)
        else:
            merged[key] = value
    return merged


def apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply .env values over default config values."""
    env_mapping = {
        ("database", "host"): ("JHCIS_DB_HOST", str),
        ("database", "port"): ("JHCIS_DB_PORT", int),
        ("database", "user"): ("JHCIS_DB_USER", str),
        ("database", "password"): ("JHCIS_DB_PASSWORD", str),
        ("database", "database"): ("JHCIS_DB_NAME", str),
        ("api", "endpoint"): ("JHCIS_API_ENDPOINT", str),
        ("api", "api_key"): ("JHCIS_API_KEY", str),
        ("settings", "retry_attempts"): ("JHCIS_RETRY_ATTEMPTS", int),
        ("settings", "retry_delay_seconds"): ("JHCIS_RETRY_DELAY_SECONDS", int),
        ("settings", "timeout_seconds"): ("JHCIS_TIMEOUT_SECONDS", int),
        ("settings", "log_level"): ("JHCIS_LOG_LEVEL", str),
        ("facility", "facility_id"): ("JHCIS_FACILITY_ID", str),
        ("facility", "facility_name"): ("JHCIS_FACILITY_NAME", str),
        ("facility", "facility_code"): ("JHCIS_FACILITY_CODE", str),
    }

    merged = {
        section: dict(values) if isinstance(values, dict) else values
        for section, values in config.items()
    }

    for (section, key), (env_key, caster) in env_mapping.items():
        env_value = os.environ.get(env_key)
        if env_value:
            merged[section][key] = caster(env_value)

    return merged


def load_env_config() -> Dict[str, Any]:
    """Build runtime config from DEFAULT_CONFIG and .env only."""
    return apply_env_overrides(DEFAULT_CONFIG)


def load_config_with_env(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Backward-compatible wrapper kept for older call sites."""
    return load_env_config()


def load_config(*_args: Any, **_kwargs: Any) -> Dict[str, Any]:
    """Backward-compatible wrapper kept for older call sites."""
    return load_env_config()


def load_config_with_env(config_file: Path) -> Dict[str, Any]:
    """Deprecated wrapper kept for compatibility."""
    return load_env_config()

def load_config(config_file: Path) -> Dict[str, Any]:
    """โหลดการตั้งค่าจากไฟล์ config.json หรือใช้ค่าเริ่มต้น"""
    if config_file.exists():
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    logging.warning(f"Config file not found: {config_file}. Using defaults.")
    return DEFAULT_CONFIG

def load_config(config_file: Path) -> Dict[str, Any]:
    """Deprecated wrapper kept for compatibility."""
    return load_env_config()


def load_env_file(env_file: Path) -> None:
    """โหลดตัวแปรแวดล้อมจากไฟล์ .env"""
    if not env_file.exists():
        return
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


def get_app_dir() -> Path:
    """Return the directory that should contain runtime config files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).parent.resolve()


def resolve_paths(
    script_dir: Path,
    env_path: str = ".env",
    log_dir_path: str = "logs"
) -> Dict[str, Path]:
    """Resolve runtime file paths relative to the script directory."""
    return {
        "env_file": script_dir / env_path,
        "log_dir": script_dir / log_dir_path,
    }


def parse_summary_types(summary_type_arg: Optional[str], all_types: bool = False) -> List[str]:
    """Parse and validate summary types from CLI or GUI input."""
    if all_types or not summary_type_arg:
        return SUMMARY_TYPES

    summary_types = [t.strip() for t in summary_type_arg.split(',') if t.strip()]
    invalid = set(summary_types) - set(SUMMARY_TYPES)
    if invalid:
        raise ValueError(f"Invalid summary types: {sorted(invalid)}. Valid types: {SUMMARY_TYPES}")

    return summary_types


def prepare_runtime(
    script_dir: Path,
    env_path: str = ".env",
    log_dir_path: str = "logs"
) -> Dict[str, Any]:
    """Load environment, config, and resolved paths for a sync run."""
    paths = resolve_paths(
        script_dir=script_dir,
        env_path=env_path,
        log_dir_path=log_dir_path,
    )
    paths["log_dir"].mkdir(exist_ok=True)
    load_env_file(paths["env_file"])

    return {
        **paths,
        "config": load_env_config(),
    }


def make_json_safe(value: Any) -> Any:
    """Convert MySQL values into JSON-serializable Python types."""
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date_type):
        return value.isoformat()
    return value


def fetch_summary_data(
    connection: mysql.connector.MySQLConnection,
    query: str,
    date: str
) -> List[Dict[str, Any]]:
    """Execute only validated SELECT queries with runtime placeholder replacement."""
    try:
        if not is_safe_select_query(query):
            logging.error("Rejected query because it is not a safe SELECT statement")
            return []

        cursor = connection.cursor(dictionary=True)
        query = query.replace("{date}", date)
        query = query.replace("{hcode}", str(os.environ.get("JHCIS_FACILITY_CODE", "")))
        cursor.execute(query)
        results = [
            {key: make_json_safe(value) for key, value in row.items()}
            for row in cursor.fetchall()
        ]
        cursor.close()
        return results
    except Error as e:
        logging.error(f"Query execution error: {e}")
        return []


def send_to_central_api(
    data: List[Dict[str, Any]],
    summary_type: str,
    date: str,
    config: Dict[str, Any],
    logger: logging.Logger
) -> bool:
    """Send summary data to the central API using the route structure the API exposes."""
    del date  # payload rows carry their own report_date/report_period fields

    summary_endpoint = SUMMARY_TYPE_ENDPOINTS.get(summary_type)
    if not summary_endpoint:
        logger.error(f"Unsupported summary type for API send: {summary_type}")
        return False

    if not data:
        logger.warning(f"No payload to send for {summary_type}")
        return False

    base_endpoint = config["api"]["endpoint"].rstrip("/")
    endpoint = f"{base_endpoint}/{summary_endpoint}"
    payload: Any = data[0]
    if len(data) > 1:
        endpoint = f"{base_endpoint}/batch"
        payload = [{"summaryType": summary_endpoint, "data": row} for row in data]

    api_key = config["api"]["api_key"]
    retry_attempts = config["settings"]["retry_attempts"]
    retry_delay = config["settings"]["retry_delay_seconds"]
    timeout = config["settings"]["timeout_seconds"]

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
    }

    for attempt in range(1, retry_attempts + 1):
        try:
            logger.info(f"Attempt {attempt}/{retry_attempts}: POST to {endpoint}")

            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=timeout
            )

            if response.status_code == 200:
                logger.info(f"Success: {response.status_code} - {response.text}")
                return True
            if response.status_code == 429:
                logger.warning(
                    f"Rate limited (429). Retry-After: {response.headers.get('Retry-After', 'N/A')}"
                )
            else:
                logger.error(f"Error: {response.status_code} - {response.text}")

        except Timeout as e:
            logger.error(f"Attempt {attempt}: Timeout - {e}")
        except ConnectionError as e:
            logger.error(f"Attempt {attempt}: Connection error - {e}")
        except RequestException as e:
            logger.error(f"Attempt {attempt}: Request failed - {e}")

        if attempt < retry_attempts:
            logger.info(f"Waiting {retry_delay} seconds before retry...")
            time.sleep(retry_delay)

    logger.error(f"Failed after {retry_attempts} attempts")
    return False


def run_sync(
    date: str,
    summary_types: List[str],
    config: Dict[str, Any],
    log_dir: Path,
    logger: Optional[logging.Logger] = None
) -> Dict[str, bool]:
    """Run sync for the requested summary types, including PERSON snapshot support."""
    if logger is None:
        logger = setup_logger(log_dir, date)
    logger.info("=" * 60)
    logger.info("JHCIS Summary Sync Started")
    logger.info(f"Date: {date}")
    logger.info(f"Summary Types: {', '.join(summary_types)}")
    logger.info("=" * 60)

    queries_by_type = sync_central_queries_to_file(summary_types, config, logger)
    if not queries_by_type:
        logger.error("Failed to prepare docs/queries.sql from central API. Aborting.")
        return {t: False for t in summary_types}

    connection = connect_to_database(config, logger=logger)
    if not connection:
        logger.error("Failed to connect to database. Aborting.")
        return {t: False for t in summary_types}

    results = {}

    for summary_type in summary_types:
        logger.info(f"\nProcessing: {summary_type}")

        query = queries_by_type.get(summary_type)
        if not query:
            logger.warning(f"Skipping {summary_type}: Central query not found or invalid")
            results[summary_type] = False
            continue

        data = fetch_summary_data(connection, query, date)

        if not data:
            logger.warning(f"No data found for {summary_type} on {date}")
            results[summary_type] = False
            continue

        logger.info(f"Fetched {len(data)} records for {summary_type}")
        success = send_to_central_api(data, summary_type, date, config, logger)
        results[summary_type] = success

        if success:
            logger.info(f"Success {summary_type} synced successfully")
        else:
            logger.error(f"Error {summary_type} sync failed")

    connection.close()

    logger.info("=" * 60)
    logger.info("Sync Completed")
    success_count = sum(1 for v in results.values() if v)
    logger.info(f"Success: {success_count}/{len(summary_types)}")
    logger.info("=" * 60)

    return results


# ==================== CLI Entry Point ====================

def main():
    parser = argparse.ArgumentParser(
        description="JHCIS Summary Centralization Sync Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
ตัวอย่างการใช้งาน:
  python sync_agent.py --date 2024-03-20
  python sync_agent.py --date 2024-03-20 --summary-type OP,IP,ER
  python sync_agent.py --all-types
        """
    )
    
    parser.add_argument(
        "--date",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="วันที่ที่ต้องการ sync (รูปแบบ: YYYY-MM-DD)"
    )
    
    parser.add_argument(
        "--summary-type",
        type=str,
        default=None,
        help="ประเภท Summary ที่ต้องการ sync (คั่นด้วย comma: OP,IP,ER)"
    )
    
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Sync ทุกประเภท (9 ประเภท)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="พาธไปยังไฟล์ config.json"
    )
    
    parser.add_argument(
        "--env",
        type=str,
        default=".env",
        help="พาธไปยังไฟล์ .env"
    )
    
    parser.add_argument(
        "--queries",
        type=str,
        default="../docs/queries.sql",
        help="พาธไปยังไฟล์ SQL queries"
    )
    
    parser.add_argument(
        "--log-dir",
        type=str,
        default="logs",
        help="พาธไปยังโฟลเดอร์ log"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="แสดง log แบบละเอียด"
    )
    
    args = parser.parse_args()
    
    # กำหนดพาธ
    script_dir = get_app_dir()
    config_file = script_dir / args.config
    env_file = script_dir / args.env
    query_file = script_dir / args.queries
    log_dir = script_dir / args.log_dir
    
    # สร้าง log directory ถ้ายังไม่มี
    log_dir.mkdir(exist_ok=True)
    
    # โหลดการตั้งค่า
    load_env_file(env_file)
    config = load_config_with_env(config_file)
    
    # กำหนด summary types ที่จะ sync
    if args.all_types:
        summary_types = SUMMARY_TYPES
    elif args.summary_type:
        summary_types = [t.strip() for t in args.summary_type.split(',')]
        # Validate
        invalid = set(summary_types) - set(SUMMARY_TYPES)
        if invalid:
            print(f"Error: Invalid summary types: {invalid}")
            print(f"Valid types: {SUMMARY_TYPES}")
            sys.exit(1)
    else:
        # Default: sync ทุกประเภท
        summary_types = SUMMARY_TYPES
    
    # รัน sync
    results = run_sync(
        date=args.date,
        summary_types=summary_types,
        config=config,
        query_file=query_file,
        log_dir=log_dir
    )
    
    # สรุปผล
    success_count = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"\n{'='*60}")
    print(f"Sync Summary: {success_count}/{total} successful")
    print(f"{'='*60}")
    
    # Exit code
    if success_count == total:
        sys.exit(0)
    else:
        sys.exit(1)


def cli_main() -> None:
    """CLI entry point used by the terminal workflow."""
    parser = argparse.ArgumentParser(
        description="JHCIS Summary Centralization Sync Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_agent.py --date 2024-03-20
  python sync_agent.py --date 2024-03-20 --summary-type OP,IP,ER
  python sync_agent.py --all-types
        """
    )

    parser.add_argument("--date", type=str, default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--summary-type", type=str, default=None)
    parser.add_argument("--all-types", action="store_true")
    parser.add_argument("--env", type=str, default=".env")
    parser.add_argument("--log-dir", type=str, default="logs")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()
    script_dir = Path(__file__).parent.resolve()
    runtime = prepare_runtime(
        script_dir=script_dir,
        env_path=args.env,
        log_dir_path=args.log_dir,
    )

    try:
        summary_types = parse_summary_types(args.summary_type, all_types=args.all_types)
    except ValueError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    results = run_sync(
        date=args.date,
        summary_types=summary_types,
        config=runtime["config"],
        log_dir=runtime["log_dir"],
    )

    success_count = sum(1 for value in results.values() if value)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"Sync Summary: {success_count}/{total} successful")
    print(f"{'=' * 60}")
    sys.exit(0 if success_count == total else 1)


def main() -> None:
    """Backward-compatible alias for the env-only CLI entry point."""
    cli_main()


if __name__ == "__main__":
    cli_main()
