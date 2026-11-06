"""Unit tests for WhisperProtocol Offline SQLite Storage (Milestone G)."""

import os
import tempfile
import pytest

from whisper.storage.db import DatabaseManager


class TestDatabaseManager:
    def setup_method(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_whisper.db")
        self.db = DatabaseManager(db_path=self.db_path)

    def teardown_method(self):
        self.temp_dir.cleanup()

    def test_default_settings_initialized(self):
        settings = self.db.get_all_settings()
        assert "alias" in settings
        assert "profile" in settings
        assert settings["alias"].startswith("Whisper")
        assert len(settings["alias"]) > len("Whisper")
        assert settings["profile"] == "ultrasonic"

    def test_update_and_get_setting(self):
        self.db.set_setting("alias", "StudioMac")
        assert self.db.get_setting("alias") == "StudioMac"

        self.db.set_setting("ecc_symbols", "16")
        assert self.db.get_setting("ecc_symbols") == "16"

    def test_node_upsert_and_retrieval(self):
        self.db.upsert_node(
            alias="LaptopAir",
            session_id=0x1234,
            rssi_db=18.5,
            profile="ultrasonic",
            trust_status="trusted",
        )

        nodes = self.db.get_nodes()
        assert len(nodes) == 1
        assert nodes[0]["alias"] == "LaptopAir"
        assert nodes[0]["session_id"] == 0x1234
        assert nodes[0]["trust_status"] == "trusted"

        # Update node
        self.db.upsert_node(
            alias="LaptopAir",
            session_id=0x5678,
            rssi_db=22.0,
        )
        nodes_updated = self.db.get_nodes()
        assert len(nodes_updated) == 1
        assert nodes_updated[0]["session_id"] == 0x5678

        # Delete node
        deleted = self.db.delete_node("LaptopAir")
        assert deleted is True
        assert len(self.db.get_nodes()) == 0

    def test_transfer_history_recording(self):
        rec_id = self.db.record_transfer(
            session_id=0xABCDEF,
            direction="tx",
            peer_alias="PeerNode",
            file_name="invoice.pdf",
            file_size=2048,
            status="completed",
            sas_code="123-456",
        )
        assert rec_id > 0

        history = self.db.get_transfer_history()
        assert len(history) == 1
        item = history[0]
        assert item["session_id"] == 0xABCDEF
        assert item["direction"] == "tx"
        assert item["peer_alias"] == "PeerNode"
        assert item["file_name"] == "invoice.pdf"
        assert item["status"] == "completed"
        assert item["sas_code"] == "123-456"

        self.db.clear_history()
        assert len(self.db.get_transfer_history()) == 0
