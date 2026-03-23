#!/usr/bin/env python3
"""
Build script for JHCIS Sync Agent Desktop App
Creates a standalone Windows executable using PyInstaller
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
    print("JHCIS Sync Agent - Desktop App Builder")
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
    print("\nCleaning previous build...")
    for folder in ["build", "dist", "__pycache__"]:
        path = script_dir / folder
        if path.exists():
            shutil.rmtree(path)
    
    # Build executable
    print("\nBuilding executable...")
    
    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--window",  # No console window
        "--name", "JHCISyncDesktop",
        "--add-data", ".env;.",
        "--add-data", "docs;docs",
        "--hidden-import", "mysql.connector",
        "--hidden-import", "mysql.connector.locales.eng.client_error",
        "--hidden-import", "mysql.connector.plugins.mysql_native_password",
        "--hidden-import", "pymysql",
        "--hidden-import", "requests",
        "--collect-all", "mysql.connector",
        "sync_agent_gui.py"
    ]
    
    subprocess.run(pyinstaller_args, check=True)
    
    # Create release folder
    release_dir = script_dir / "release" / "JHCISyncDesktop"
    release_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy executable
    exe_src = script_dir / "dist" / "JHCISyncDesktop.exe"
    exe_dst = release_dir / "JHCISyncDesktop.exe"
    shutil.copy(exe_src, exe_dst)
    
    # Copy env example
    env_example = script_dir / ".env.example"
    if env_example.exists():
        shutil.copy(env_example, release_dir / ".env.example")
    
    # Create default .env if not exists
    if not (release_dir / ".env").exists():
        shutil.copy(env_example, release_dir / ".env")
    
    # Copy docs folder
    docs_src = script_dir / "docs"
    docs_dst = release_dir / "docs"
    if docs_src.exists():
        if docs_dst.exists():
            shutil.rmtree(docs_dst)
        shutil.copytree(docs_src, docs_dst)
    
    # Create logs folder
    (release_dir / "logs").mkdir(exist_ok=True)
    
    print("\n" + "=" * 60)
    print("Build completed!")
    print(f"Executable: {exe_dst}")
    print(f"Release folder: {release_dir}")
    print("=" * 60)
    
    # Open release folder
    os.startfile(str(release_dir))

if __name__ == "__main__":
    main()