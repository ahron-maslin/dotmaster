"""
dotmaster/backup.py
Handles zipping existing managed configurations prior to a global sync to prevent data loss.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from dotmaster.config import DotmasterConfig

logger = logging.getLogger("dotmaster.backup")

def backup_managed_files(config: DotmasterConfig, output_dir: Path) -> Path | None:
    """
    Finds all generated files currently managed by dotmaster in output_dir,
    and copies them to a timestamped archive in .dotmaster/backups/.
    
    Returns the Path to the backup archive, or None if no files were backed up.
    """
    if not config.generated:
        logger.debug("No generated files recorded. Skipping backup.")
        return None

    # Collect existing files that the config claims to manage
    files_to_backup: list[Path] = []
    for entry in config.generated:
        file_path = output_dir / entry.path
        if file_path.exists() and file_path.is_file():
            files_to_backup.append(file_path)

    if not files_to_backup:
        logger.debug("No existing managed files found on disk. Skipping backup.")
        return None

    backup_dir = output_dir / ".dotmaster" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    staging_dir = backup_dir / f"staged_{timestamp}"
    staging_dir.mkdir()

    logger.info(f"Backing up {len(files_to_backup)} managed files before generation...")

    try:
        for f in files_to_backup:
            try:
                rel = f.relative_to(output_dir)
                dest = staging_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
            except ValueError:
                # file is not relative to output_dir, skip it
                pass

        # Create zip archive
        archive_name = backup_dir / f"backup_{timestamp}"
        shutil.make_archive(str(archive_name), 'zip', staging_dir)
        archive_path = archive_name.with_suffix(".zip")
        
        logger.info(f"Backup created at {archive_path.relative_to(output_dir)}")
        return archive_path
    finally:
        # Cleanup staging
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
