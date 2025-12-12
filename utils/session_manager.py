"""
session_manager.py - Session management class

Manages lifecycle of validation sessions including:
- Configuration
- Progress tracking
- State persistence
Each session is stored in sessions/{session_id}/ with:
- config.json: Session configuration
- progress.json: Validation progress and results
- excluded.json: Invalid files that failed schema validation
"""

import json
import random
import shutil
from pathlib import Path

from utils.models import Session
from utils.predictions_loader import get_prediction_files, validate_and_filter_files


class SessionManager:
    """
    Manages session configuration, progress, and validation state
    """

    SESSIONS_DIR = Path("sessions")

    def __init__(self, session_id):
        self.session_id = session_id
        self.session_path = self.SESSIONS_DIR / session_id

    # Configuration operations

    @classmethod
    def create_new(cls, session):
        """
        Create a new session and return manager instance
        """
        manager = cls(session.id)
        manager.session_path.mkdir(parents=True, exist_ok=True)

        config_path = manager.config_path
        with open(config_path, "w") as f:
            json.dump(session.model_dump(), f, indent=2, default=str)

        return manager

    def load_config(self):
        """
        Load session configuration from config.json
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Session {self.session_id} not found")

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)

            session = Session(**data)

            if not Path(session.predictions_folder).exists():
                raise FileNotFoundError(
                    f"Predictions folder not found: {session.predictions_folder}"
                )

            return session

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in session config: {e}")
        except Exception as e:
            raise ValueError(f"Error loading session: {e}")

    def delete(self):
        """
        Delete session folder and all associated data
        """
        if not self.session_path.exists():
            raise FileNotFoundError(f"Session {self.session_id} not found")

        shutil.rmtree(self.session_path)

    # Progress operations

    def load_progress(self):
        """
        Load progress data, returns default if not exists
        """
        if not self.progress_path.exists():
            return {
                "current_file_index": 0,
                "files": [],
                "results": {},
                "completed_files": [],
            }

        try:
            with open(self.progress_path, "r") as f:
                progress_data = json.load(f)
        except (json.JSONDecodeError, Exception):
            return {
                "current_file_index": 0,
                "files": [],
                "results": {},
                "completed_files": [],
            }

        return progress_data

    def save_progress(self, progress_data):
        """
        Save progress data to progress.json
        """
        with open(self.progress_path, "w") as f:
            json.dump(progress_data, f, indent=2)

    def save_results(self, file_path, results):
        """
        Save validation results for a single doc, returns updated progress
        """
        if not results:
            return self.load_progress()

        progress = self.load_progress()

        if file_path not in progress["results"]:
            progress["results"][file_path] = {}

        progress["results"][file_path].update(results)
        self.save_progress(progress)

        return progress

    # Exclusion operations for invalid files

    def load_excluded_files(self):
        """
        Load excluded invalid files log
        """
        if self.excluded_path.exists():
            with open(self.excluded_path, "r") as f:
                return json.load(f)
        return {}

    def save_excluded_files(self, excluded):
        """
        Save excluded invalid files log
        """
        with open(self.excluded_path, "w") as f:
            json.dump(excluded, f, indent=2)

    # Session initialisation

    def initialize_files(self, session):
        """
        Load session with validation
        """
        progress = self.load_progress()

        if not progress["files"]:
            all_files = get_prediction_files(session.predictions_folder)

            if len(all_files) > session.sample_size:
                sampled_files = random.sample(all_files, session.sample_size)
            else:
                sampled_files = all_files

            valid_files, excluded = validate_and_filter_files(sampled_files, session)

            progress["files"] = valid_files
            progress["current_file_index"] = 0
            self.save_progress(progress)

            if excluded:
                self.save_excluded_files(excluded)
        else:
            excluded = self.load_excluded_files()

        return progress, excluded

    # Listing sessions

    @classmethod
    def list_all(cls):
        """
        List all available sessions
        """
        if not cls.SESSIONS_DIR.exists():
            return []

        sessions = []
        for session_path in cls.SESSIONS_DIR.iterdir():
            if session_path.is_dir():
                config_path = session_path / "config.json"
                if config_path.exists():
                    try:
                        with open(config_path, "r") as f:
                            data = json.load(f)
                        sessions.append(Session(**data))
                    except Exception:
                        continue

        return sessions

    @classmethod
    def exists(cls, session_id):
        """
        Check if session exists
        """
        session_path = cls.SESSIONS_DIR / session_id
        config_path = session_path / "config.json"
        return config_path.exists()

    # Properties

    @property
    def config_path(self):
        """
        Path to session config file
        """
        return self.session_path / "config.json"

    @property
    def progress_path(self):
        """
        Path to progress file
        """
        return self.session_path / "progress.json"

    @property
    def excluded_path(self):
        """
        Path to excluded files log
        """
        return self.session_path / "excluded.json"

    def __repr__(self):
        """
        String representation for debugging
        """
        return f"SessionManager(session_id='{self.session_id}')"
