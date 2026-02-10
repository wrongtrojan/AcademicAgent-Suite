import logging
from enum import Enum
from threading import Lock

# Configure internationalized logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [SYSTEM-STATE] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("SystemStateManager")

class SystemStatus(Enum):
    IDLE = "IDLE"
    INGESTING = "INGESTING"  # Track A: Processing assets
    QUERYING = "QUERYING"    # Track B: RAG / Brain Reasoning
    ERROR = "ERROR"

class SystemStateManager:
    """
    Manages the global state of the AcademicAgent-Suite.
    Ensures mutual exclusion between asset ingestion and user querying
    to protect GPU VRAM and data integrity.
    """
    _instance = None
    _state_lock = Lock()

    def __new__(cls):
        with cls._state_lock:
            if cls._instance is None:
                cls._instance = super(SystemStateManager, cls).__new__(cls)
                cls._instance._current_status = SystemStatus.IDLE
                cls._instance._task_id = None
            return cls._instance

    def acquire_ingestion_lock(self, task_id: str) -> bool:
        """Attempt to lock the system for asset processing."""
        with self._state_lock:
            if self._current_status == SystemStatus.IDLE:
                self._current_status = SystemStatus.INGESTING
                self._task_id = task_id
                logger.info(f"Lock ACQUIRED for Ingestion Task: [{task_id}]")
                return True
            else:
                logger.warning(f"Lock DENIED for Task [{task_id}]. System is {self._current_status.value}")
                return False

    def release_lock(self):
        """Release the current lock and return to IDLE."""
        with self._state_lock:
            old_status = self._current_status
            self._current_status = SystemStatus.IDLE
            self._task_id = None
            logger.info(f"System state transitioned from {old_status.value} to IDLE.")

    @property
    def get_status(self) -> SystemStatus:
        return self._current_status

    def is_query_allowed(self) -> bool:
        """Check if the Brain is available for user questions."""
        # Ensure status is strictly IDLE to allow querying
        with self._state_lock:
            return self._current_status == SystemStatus.IDLE