"""SonIA Core Modules"""
import logging

logger = logging.getLogger(__name__)


def patch_db_manager():
    """Monkey-patch DBManager.connect to load exclusions from txt files."""
    from modules.db_manager import DBManager
    from modules.load_exclusions import load_exclusions_from_files

    _original_connect = DBManager.connect

    def patched_connect(self):
        result = _original_connect(self)
        if self.conn:
            try:
                loaded = load_exclusions_from_files(self.conn)
                if loaded:
                    logger.info(f"Loaded {loaded} additional exclusions from txt files")
            except Exception as e:
                logger.warning(f"Could not load file-based exclusions: {e}")
        return result

    DBManager.connect = patched_connect
    logger.debug("DBManager.connect patched to load file-based exclusions")


try:
    patch_db_manager()
except Exception as e:
    logger.warning(f"Could not patch DBManager: {e}")
