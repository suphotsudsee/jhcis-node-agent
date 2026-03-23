#!/usr/bin/env python3
"""
Build script for JHCIS Sync Agent CLI
Creates a standalone Windows executable for scheduled sync
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

def main():
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    print("=" * 60)
    print("JHCIS Sync Agent CLI - Builder")
    print("=" * 60)
    
    # Check Python version
    print(f"\nPython version: {sys.version}")
    
    # Install dependencies
    print("\nInstalling dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=True)
    
    # Install PyInstaller
    print("\nInstalling PyInstaller...")
    subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
    
    # Clean previous build
    print("\nCleaning previous CLI build...")
    for folder in ["build_cli", "dist_cli"]:
        path = script_dir / folder
        if path.exists():
            shutil.rmtree(path)
    
    # Build CLI executable
    print("\nBuilding CLI executable...")
    
    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console",  # Console app for CLI
        "--name", "jhcis-sync-agent",
        "--hidden-import", "mysql.connector",
        "--hidden-import", "mysql.connector.locales.eng.client_error",
        "--hidden-import", "mysql.connector.plugins.mysql_native_password",
        "--hidden-import", "pymysql",
        "--hidden-import", "requests",
        "--collect-all", "mysql.connector",
        "sync_agent.py"
    ]
    
    subprocess.run(pyinstaller_args, check=True)
    
    # Create release folder if not exists
    release_dir = script_dir / "release" / "JHCISyncDesktop"
    release_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy CLI executable to release folder
    cli_src = script_dir / "dist" / "jhcis-sync-agent.exe"
    cli_dst = release_dir / "jhcis-sync-agent.exe"
    shutil.copy(cli_src, cli_dst)
    
    print("\n" + "=" * 60)
    print("CLI Build completed!")
    print(f"Executable: {cli_dst}")
    print("=" * 60)

if __name__ == "__main__":
    main()