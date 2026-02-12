#!/usr/bin/env python3
"""
OCBS Skill Installation Script

This script installs OCBS as an OpenClaw skill.
"""

import json
import shutil
from pathlib import Path
import sys


def get_openclaw_skills_dir() -> Path:
    """Get the OpenClaw skills directory."""
    # Check for workspace skills first
    workspace = Path.cwd()
    if (workspace / "skills").exists():
        return workspace / "skills"
    
    # Fall back to global skills
    return Path.home() / ".openclaw" / "skills"


def install_skill(skills_dir: Path = None):
    """Install OCBS skill to OpenClaw."""
    skills_dir = skills_dir or get_openclaw_skills_dir()
    skills_dir.mkdir(parents=True, exist_ok=True)
    
    # Create skill directory
    skill_dir = skills_dir / "ocbs_backup"
    skill_dir.mkdir(exist_ok=True)
    
    # Get OCBS source directory
    ocbs_src = Path(__file__).parent / "src" / "ocbs"
    skill_src = Path(__file__).parent / "skill"
    
    # Copy skill manifest
    if (skill_src / "skill.json").exists():
        shutil.copy(skill_src / "skill.json", skill_dir / "skill.json")
    
    # Copy skill module
    if (ocbs_src / "skill.py").exists():
        shutil.copy(ocbs_src / "skill.py", skill_dir / "skill.py")
    
    # Copy core module for skill functionality
    if (ocbs_src / "core.py").exists():
        shutil.copy(ocbs_src / "core.py", skill_dir / "core.py")
    
    # Copy integration module
    if (ocbs_src / "integration.py").exists():
        shutil.copy(ocbs_src / "integration.py", skill_dir / "integration.py")
    
    # Create __init__.py
    init_content = '''"""OCBS Backup Skill for OpenClaw."""

from .skill import OCBSBackupSkill, SKILL_MANIFEST

__all__ = ["OCBSBackupSkill", "SKILL_MANIFEST"]
'''
    (skill_dir / "__init__.py").write_text(init_content)
    
    print(f"✅ OCBS skill installed to: {skill_dir}")
    print(f"\nTo use the skill:")
    print(f"  1. Restart OpenClaw to load the new skill")
    print(f"  2. Use commands like: /ocbs backup, /ocbs restore --latest")
    print(f"")
    print(f"To verify installation:")
    print(f"  ocbs status")
    
    return str(skill_dir)


def install_package():
    """Install OCBS package and skill."""
    print("Installing OCBS package...")
    
    # Install the package
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        cwd=Path(__file__).parent,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ Failed to install package: {result.stderr}")
        return False
    
    print("✅ Package installed successfully")
    
    # Install skill
    install_skill()
    
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="OCBS Installation")
    parser.add_argument("--skill-only", action="store_true", 
                        help="Install skill only, not the package")
    parser.add_argument("--skills-dir", type=str, 
                        help="Custom skills directory")
    
    args = parser.parse_args()
    
    if args.skill_only:
        skills_dir = Path(args.skills_dir) if args.skills_dir else None
        install_skill(skills_dir)
    else:
        install_package()
