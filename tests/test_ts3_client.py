import asyncio
import logging
import sqlite3
import urllib.parse
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from hermes_agent_ts3.ts3_client import TS3ClientConfig, TS3ClientManager


class TestTS3ClientConfig:
    def test_default_values(self):
        cfg = TS3ClientConfig()
        assert cfg.binary_path == ""
        assert cfg.data_dir == "ts3_client_data"
        assert cfg.identity_file == "ts3_identity"
        assert cfg.display == ":99"
        assert cfg.server_host == ""
        assert cfg.voice_port == 9987
        assert cfg.server_password == ""
        assert cfg.nickname == "Hermes"
        assert cfg.playback_device == "ts3_playback"
        assert cfg.capture_device == "bot_tts"
        assert cfg.reconnect_base == 1.0
        assert cfg.reconnect_max == 60.0


class TestTS3ClientManagerProperties:
    def test_running_false_initially(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        assert mgr.running is False

    def test_pid_none_initially(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        assert mgr.pid is None

    @pytest.mark.asyncio
    async def test_running_true_when_process_alive(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mgr._process = mock_proc
        assert mgr.running is True

    @pytest.mark.asyncio
    async def test_running_false_when_process_exited(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mgr._process = mock_proc
        assert mgr.running is False

    @pytest.mark.asyncio
    async def test_pid_returns_process_pid(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_proc = AsyncMock()
        mock_proc.pid = 12345
        mgr._process = mock_proc
        assert mgr.pid == 12345


class TestBuildEnv:
    def test_build_env_sets_display(self):
        cfg = TS3ClientConfig(display=":99")
        mgr = TS3ClientManager(cfg)
        env = mgr._build_env()
        assert env["DISPLAY"] == ":99"

    def test_build_env_copies_existing_env(self):
        import os
        cfg = TS3ClientConfig(display=":100")
        mgr = TS3ClientManager(cfg)
        with patch.dict(os.environ, {"HOME": "/home/test", "PATH": "/usr/bin"}):
            env = mgr._build_env()
            assert env["HOME"] == "/home/test"
            assert env["PATH"] == "/usr/bin"
            assert env["DISPLAY"] == ":100"


class TestEnsureTable:
    def test_ensure_table_creates_table(self):
        conn = sqlite3.connect(":memory:")
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._ensure_table(conn, "Playback")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Playback'"
        )
        assert cursor.fetchone() is not None

    def test_ensure_table_idempotent(self):
        conn = sqlite3.connect(":memory:")
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._ensure_table(conn, "Bookmarks")
        mgr._ensure_table(conn, "Bookmarks")
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Bookmarks'"
        )
        assert cursor.fetchone() is not None

    def test_ensure_table_schema(self):
        conn = sqlite3.connect(":memory:")
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._ensure_table(conn, "Capture")
        conn.execute(
            "INSERT INTO Capture (key, value) VALUES (?, ?)",
            ("test_key", "test_value"),
        )
        result = conn.execute(
            "SELECT value FROM Capture WHERE key = ?", ("test_key",)
        ).fetchone()
        assert result[0] == "test_value"

    def test_ensure_table_primary_key_uniqueness(self):
        conn = sqlite3.connect(":memory:")
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._ensure_table(conn, "Playback")
        conn.execute("INSERT INTO Playback (key, value) VALUES ('k', 'v1')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO Playback (key, value) VALUES ('k', 'v2')")


class TestConfigureSettingsDB:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        self.data_dir = tmp_path / "ts3_data"
        self.config = TS3ClientConfig(
            data_dir=str(self.data_dir),
            server_host="ts.example.com",
            voice_port=9987,
            server_password="secret123",
            nickname="TestBot",
            playback_device="custom_playback",
            capture_device="custom_capture",
        )

    def _read_db(self, table):
        db_path = self.data_dir / "settings.db"
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(f"SELECT key, value FROM {table}").fetchall()
        conn.close()
        return dict(rows)

    @pytest.mark.asyncio
    async def test_configures_bookmark_with_password(self):
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()

        bookmarks = self._read_db("Bookmarks")
        expected = (
            f"ts3server://ts.example.com?"
            f"port=9987"
            f"&nickname={urllib.parse.quote('TestBot', safe='')}"
            f"&password={urllib.parse.quote('secret123', safe='')}"
        )
        assert bookmarks["default"] == expected

    @pytest.mark.asyncio
    async def test_configures_bookmark_without_password(self):
        self.config.server_password = ""
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()

        bookmarks = self._read_db("Bookmarks")
        expected = (
            f"ts3server://ts.example.com?"
            f"port=9987"
            f"&nickname={urllib.parse.quote('TestBot', safe='')}"
        )
        assert bookmarks["default"] == expected
        assert "password" not in bookmarks["default"]

    @pytest.mark.asyncio
    async def test_configures_playback_device(self):
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()
        playback = self._read_db("Playback")
        assert playback["default"] == "custom_playback"

    @pytest.mark.asyncio
    async def test_configures_capture_device(self):
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()
        capture = self._read_db("Capture")
        assert capture["default"] == "custom_capture"

    @pytest.mark.asyncio
    async def test_creates_data_dir(self):
        assert not self.data_dir.exists()
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()
        assert self.data_dir.exists()

    @pytest.mark.asyncio
    async def test_bookmark_url_encodes_special_chars(self):
        self.config.nickname = "Test Bot & Co"
        self.config.server_password = "p@ss w/rd"
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()

        bookmarks = self._read_db("Bookmarks")
        url = bookmarks["default"]
        assert "Test%20Bot%20%26%20Co" in url
        assert "p%40ss%20w%2Frd" in url

    @pytest.mark.asyncio
    async def test_idempotent(self):
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()
        await mgr._configure_settings_db()

        bookmarks = self._read_db("Bookmarks")
        playback = self._read_db("Playback")
        capture = self._read_db("Capture")

        assert "default" in bookmarks
        assert "default" in playback
        assert "default" in capture

    @pytest.mark.asyncio
    async def test_creates_all_three_tables(self):
        mgr = TS3ClientManager(self.config)
        await mgr._configure_settings_db()

        db_path = self.data_dir / "settings.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        assert "Bookmarks" in tables
        assert "Capture" in tables
        assert "Playback" in tables


class TestEnsureIdentity:
    def _make_subprocess_mock(self, returncode=None):
        mock = AsyncMock()
        mock.returncode = returncode
        mock.wait = AsyncMock()
        mock.terminate = MagicMock()
        mock.kill = MagicMock()
        return mock

    @pytest.mark.asyncio
    async def test_identity_exists_noop(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        identity_file = data_dir / "my_identity"
        identity_file.write_text("dummy")

        cfg = TS3ClientConfig(data_dir=str(data_dir), identity_file="my_identity")
        mgr = TS3ClientManager(cfg)

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
        ) as mock_exec:
            await mgr._ensure_identity()
            mock_exec.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_identity_first_run(self, tmp_path):
        data_dir = tmp_path / "data"
        cfg = TS3ClientConfig(
            data_dir=str(data_dir),
            identity_file="ts3_identity",
            binary_path="/usr/bin/ts3client",
            display=":99",
        )
        mgr = TS3ClientManager(cfg)

        async def create_identity_file(*args, **kwargs):
            identity_path = data_dir / "ts3_identity"
            data_dir.mkdir(parents=True, exist_ok=True)
            identity_path.write_text("generated")
            return self._make_subprocess_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            side_effect=create_identity_file,
        ) as mock_exec:
            await mgr._ensure_identity()
            assert (data_dir / "ts3_identity").exists()
            mock_exec.assert_called_once()
            kwargs = mock_exec.call_args.kwargs
            assert kwargs["cwd"] == str(data_dir)
            assert kwargs["env"]["DISPLAY"] == ":99"

    @pytest.mark.asyncio
    async def test_identity_not_generated_raises(self, tmp_path):
        data_dir = tmp_path / "data"
        cfg = TS3ClientConfig(
            data_dir=str(data_dir),
            identity_file="ts3_identity",
            binary_path="/usr/bin/ts3client",
        )
        mgr = TS3ClientManager(cfg)

        mock_proc = self._make_subprocess_mock(returncode=0)
        mock_proc.pid = 9999

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            with pytest.raises(RuntimeError, match="Identity was not generated"):
                await mgr._ensure_identity()

    @pytest.mark.asyncio
    async def test_uses_default_binary_when_not_configured(self, tmp_path):
        data_dir = tmp_path / "data"
        cfg = TS3ClientConfig(
            data_dir=str(data_dir),
            identity_file="ts3_identity",
            binary_path="",
        )
        mgr = TS3ClientManager(cfg)

        async def create_identity(*args, **kwargs):
            identity_path = data_dir / "ts3_identity"
            data_dir.mkdir(parents=True, exist_ok=True)
            identity_path.write_text("generated")
            return self._make_subprocess_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            side_effect=create_identity,
        ) as mock_exec:
            await mgr._ensure_identity()
            call_args = mock_exec.call_args.args
            assert call_args[0] == "ts3client_linux_amd64"


class TestLaunchClient:
    def _make_process_mock(self, pid=1234):
        mock = AsyncMock()
        mock.pid = pid
        mock.returncode = None
        mock.stdout = AsyncMock()
        mock.stdout.readline = AsyncMock(side_effect=[b"", asyncio.CancelledError()])
        mock.stderr = AsyncMock()
        mock.stderr.readline = AsyncMock(side_effect=[b"", asyncio.CancelledError()])
        return mock

    @pytest.mark.asyncio
    async def test_launches_with_correct_binary(self):
        cfg = TS3ClientConfig(binary_path="/opt/ts3/client")
        mgr = TS3ClientManager(cfg)
        mock_proc = self._make_process_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            await mgr._launch_client()
            assert mock_exec.call_args.args[0] == "/opt/ts3/client"
            assert mgr._process is not None
            assert mgr._stdout_task is not None
            assert mgr._stderr_task is not None

    @pytest.mark.asyncio
    async def test_launches_with_default_binary(self):
        cfg = TS3ClientConfig(binary_path="")
        mgr = TS3ClientManager(cfg)
        mock_proc = self._make_process_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            await mgr._launch_client()
            assert mock_exec.call_args.args[0] == "ts3client_linux_amd64"

    @pytest.mark.asyncio
    async def test_sets_cwd_to_data_dir(self, tmp_path):
        cfg = TS3ClientConfig(data_dir=str(tmp_path / "ts3_data"))
        mgr = TS3ClientManager(cfg)
        mock_proc = self._make_process_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            await mgr._launch_client()
            assert mock_exec.call_args.kwargs["cwd"] == str(tmp_path / "ts3_data")

    @pytest.mark.asyncio
    async def test_sets_display_env(self):
        cfg = TS3ClientConfig(display=":105")
        mgr = TS3ClientManager(cfg)
        mock_proc = self._make_process_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as mock_exec:
            await mgr._launch_client()
            assert mock_exec.call_args.kwargs["env"]["DISPLAY"] == ":105"

    @pytest.mark.asyncio
    async def test_stdout_capture_logs_output(self, caplog):
        caplog.set_level(logging.DEBUG)
        cfg = TS3ClientConfig()
        mgr = TS3ClientManager(cfg)
        mock_proc = AsyncMock()
        mock_proc.pid = 999
        mock_proc.returncode = None
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[b"log line 1\n", b"log line 2\n", b""]
        )
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.readline = AsyncMock(return_value=b"")

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await mgr._launch_client()
            assert mgr._stdout_task is not None
            await mgr._stdout_task
            assert "TS3 stdout: log line 1" in caplog.text
            assert "TS3 stdout: log line 2" in caplog.text

    @pytest.mark.asyncio
    async def test_stderr_capture_logs_output(self, caplog):
        caplog.set_level(logging.DEBUG)
        cfg = TS3ClientConfig()
        mgr = TS3ClientManager(cfg)
        mock_proc = AsyncMock()
        mock_proc.pid = 999
        mock_proc.returncode = None
        mock_proc.stdout = AsyncMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.readline = AsyncMock(
            side_effect=[b"error 1\n", b"error 2\n", b""]
        )

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await mgr._launch_client()
            assert mgr._stderr_task is not None
            await mgr._stderr_task
            assert "TS3 stderr: error 1" in caplog.text
            assert "TS3 stderr: error 2" in caplog.text


class TestKillProcess:
    @pytest.mark.asyncio
    async def test_kill_process_none_noop(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._process = None
        mgr._kill_process()
        assert await mgr.is_healthy() is False

    @pytest.mark.asyncio
    async def test_kill_process_already_exited_noop(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock = AsyncMock()
        mock.returncode = 0
        mgr._process = mock
        mgr._kill_process()
        assert await mgr.is_healthy() is False


class TestReconnect:
    def _make_process_mock(self, pid=1234):
        mock = AsyncMock()
        mock.pid = pid
        mock.returncode = None
        mock.stdout = AsyncMock()
        mock.stdout.readline = AsyncMock(side_effect=[b"", asyncio.CancelledError()])
        mock.stderr = AsyncMock()
        mock.stderr.readline = AsyncMock(side_effect=[b"", asyncio.CancelledError()])
        return mock

    @pytest.mark.asyncio
    async def test_reconnect_returns_when_shutting_down_initially(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._shutting_down = True
        with patch("asyncio.sleep") as mock_sleep:
            await mgr._reconnect()
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_reconnect_exponential_backoff(self):
        cfg = TS3ClientConfig(reconnect_base=1.0, reconnect_max=60.0)
        mgr = TS3ClientManager(cfg)
        mgr._shutting_down = False

        sleep_delays = []

        async def mock_sleep(delay):
            sleep_delays.append(delay)

        async def mock_launch():
            raise RuntimeError("launch failed")

        mgr._ensure_identity = AsyncMock()
        mgr._configure_settings_db = AsyncMock()
        mgr._launch_client = AsyncMock(side_effect=mock_launch)
        mgr._monitor_loop = AsyncMock()

        original_sleep = asyncio.sleep
        sleep_count = 0

        async def tracking_sleep(delay):
            nonlocal sleep_count
            sleep_delays.append(delay)
            sleep_count += 1
            if sleep_count >= 7:
                mgr._shutting_down = True

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            await mgr._reconnect()

        assert len(sleep_delays) == 7
        assert sleep_delays[0] == 1.0
        assert sleep_delays[1] == 2.0
        assert sleep_delays[2] == 4.0
        assert sleep_delays[3] == 8.0
        assert sleep_delays[4] == 16.0
        assert sleep_delays[5] == 32.0
        assert sleep_delays[6] == 60.0

    @pytest.mark.asyncio
    async def test_reconnect_caps_at_max(self):
        cfg = TS3ClientConfig(reconnect_base=5.0, reconnect_max=10.0)
        mgr = TS3ClientManager(cfg)
        mgr._shutting_down = False

        sleep_delays = []

        mgr._ensure_identity = AsyncMock()
        mgr._configure_settings_db = AsyncMock()
        mgr._launch_client = AsyncMock(side_effect=RuntimeError("fail"))
        mgr._monitor_loop = AsyncMock()

        sleep_count = 0

        async def tracking_sleep(delay):
            nonlocal sleep_count
            sleep_delays.append(delay)
            sleep_count += 1
            if sleep_count >= 5:
                mgr._shutting_down = True

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            await mgr._reconnect()

        assert sleep_delays == [5.0, 10.0, 10.0, 10.0, 10.0]

    @pytest.mark.asyncio
    async def test_reconnect_success_breaks_loop(self):
        mgr = TS3ClientManager(TS3ClientConfig(reconnect_base=1.0))
        mgr._shutting_down = False

        sleep_delays = []

        call_count = 0

        async def mock_launch():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("fail")
            mgr._monitor_task = asyncio.current_task()
            return

        mgr._ensure_identity = AsyncMock()
        mgr._configure_settings_db = AsyncMock()
        mgr._launch_client = AsyncMock(side_effect=mock_launch)
        mgr._monitor_loop = AsyncMock()

        async def tracking_sleep(delay):
            sleep_delays.append(delay)

        with patch("asyncio.sleep", side_effect=tracking_sleep):
            await mgr._reconnect()

        assert len(sleep_delays) == 3
        assert sleep_delays[0] == 1.0
        assert sleep_delays[1] == 2.0
        assert sleep_delays[2] == 4.0
        assert call_count == 3


class TestMonitorLoop:
    @pytest.mark.asyncio
    async def test_monitor_triggers_reconnect_on_exit(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._shutting_down = False
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 42
        mgr._process = mock_proc

        mgr._reconnect = AsyncMock()

        await mgr._monitor_loop()

        assert mgr._process is None
        assert mgr._reconnect_task is not None
        await mgr._reconnect_task

        mgr._reconnect_task.cancel()

    @pytest.mark.asyncio
    async def test_monitor_does_not_reconnect_when_shutting_down(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._shutting_down = True
        mock_proc = AsyncMock()
        mock_proc.wait.return_value = 0
        mgr._process = mock_proc

        mgr._reconnect = AsyncMock()

        await mgr._monitor_loop()

        assert mgr._process is None
        mgr._reconnect.assert_not_called()


class TestStart:
    def _make_process_mock(self):
        mock = AsyncMock()
        mock.pid = 999
        mock.returncode = None
        mock.stdout = AsyncMock()
        mock.stdout.readline = AsyncMock(side_effect=[b"", asyncio.CancelledError()])
        mock.stderr = AsyncMock()
        mock.stderr.readline = AsyncMock(side_effect=[b"", asyncio.CancelledError()])
        return mock

    @pytest.mark.asyncio
    async def test_start_orchestrates_steps(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        identity = data_dir / "ts3_identity"
        identity.write_text("fake")

        cfg = TS3ClientConfig(data_dir=str(data_dir))
        mgr = TS3ClientManager(cfg)
        mock_proc = self._make_process_mock()

        with patch(
            "hermes_agent_ts3.ts3_client.asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            await mgr.start()

        assert mgr._shutting_down is False
        assert mgr._process is not None
        assert mgr._monitor_task is not None


class TestStop:
    @pytest.mark.asyncio
    async def test_stop_sets_shutting_down_flag(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._shutting_down = False
        mgr._reconnect_task = None
        mgr._monitor_task = None
        mgr._stdout_task = None
        mgr._stderr_task = None
        mgr._process = None

        await mgr.stop()
        assert mgr._shutting_down is True
        assert mgr._process is None

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_monitor = AsyncMock()
        mock_monitor.cancel = MagicMock()
        mock_stdout = AsyncMock()
        mock_stdout.cancel = MagicMock()
        mock_stderr = AsyncMock()
        mock_stderr.cancel = MagicMock()

        mgr._process = None
        mgr._reconnect_task = None
        mgr._monitor_task = mock_monitor
        mgr._stdout_task = mock_stdout
        mgr._stderr_task = mock_stderr

        await mgr.stop()

        mock_monitor.cancel.assert_called_once()
        mock_stdout.cancel.assert_called_once()
        mock_stderr.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cancels_reconnect_task(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_reconnect = AsyncMock()
        mock_reconnect.cancel = MagicMock()

        mgr._process = None
        mgr._reconnect_task = mock_reconnect
        mgr._monitor_task = None
        mgr._stdout_task = None
        mgr._stderr_task = None

        await mgr.stop()
        mock_reconnect.cancel.assert_called_once()


class TestIsHealthy:
    @pytest.mark.asyncio
    async def test_healthy_when_process_alive(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mgr._process = mock_proc
        assert await mgr.is_healthy() is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_process_exited(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mgr._process = mock_proc
        assert await mgr.is_healthy() is False

    @pytest.mark.asyncio
    async def test_unhealthy_when_no_process(self):
        mgr = TS3ClientManager(TS3ClientConfig())
        mgr._process = None
        assert await mgr.is_healthy() is False
