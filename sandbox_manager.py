import base64
import ctypes
import ctypes.wintypes
import json
import os
import random
import shutil
import sqlite3
import string
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:  # pragma: no cover - dependency missing at runtime
    print("未找到 cryptography 库，请先运行 `pip install -r requirements.txt`。")
    sys.exit(1)


class DPAPIDecryptor:
    """使用 Windows DPAPI 解密数据。"""

    def __init__(self) -> None:
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", ctypes.wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    def decrypt(self, encrypted: bytes) -> bytes:
        if not encrypted:
            return b""
        buffer = ctypes.create_string_buffer(encrypted)
        blob_in = self._DATA_BLOB(len(encrypted), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        blob_out = self._DATA_BLOB()

        if not self._crypt32.CryptUnprotectData(
            ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        try:
            decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            self._kernel32.LocalFree(blob_out.pbData)
        return decrypted


def ensure_windows() -> None:
    if os.name != "nt":
        print("此脚本仅支持在 Windows 上运行。")
        sys.exit(1)


class SandboxManager:
    def __init__(self, config: Dict[str, object]) -> None:
        ensure_windows()
        self.config = config
        self.session_id = datetime.now().strftime("%Y%m%d%H%M%S") + f"_{random.randint(1000, 9999)}"
        prefix = f"ChromeSandbox_{self.session_id}_"
        self.base_dir = Path(tempfile.mkdtemp(prefix=prefix))
        self.created_directories: List[Path] = [self.base_dir]
        self.processes: List[subprocess.Popen] = []
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.chrome_closed_event = threading.Event()
        self._directory_record_path = Path(__file__).resolve().parent / "session_dirs.json"
        self._directory_record: Dict[str, object] = {
            "session_id": self.session_id,
            "created_at": self.started_at,
            "directories": [str(self.base_dir)],
        }
        self._dpapi = DPAPIDecryptor()

    def launch_chrome_instances(self, window_count: int) -> None:
        chrome_path = self._get_chrome_path()
        urls = self._get_default_urls()
        use_incognito = bool(self.config.get("use_incognito", False))

        for idx in range(1, window_count + 1):
            profile_dir = self.base_dir / f"P{idx}"
            profile_dir.mkdir(parents=True, exist_ok=True)
            self.created_directories.append(profile_dir)
            self._directory_record.setdefault("directories", []).append(str(profile_dir))

            cmd = [
                chrome_path,
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-sync",
                "--new-window",
            ]
            if use_incognito:
                cmd.append("--incognito")
            cmd.extend(urls)
            try:
                process = subprocess.Popen(cmd)
            except FileNotFoundError:
                print(f"未能找到 Chrome，可执行文件路径：{chrome_path}")
                raise
            except Exception as exc:  # pragma: no cover - subprocess errors
                print(f"启动 Chrome 时出现异常：{exc}")
                raise
            self.processes.append(process)

        self._write_directory_record()
        threading.Thread(target=self._monitor_processes, name="ChromeMonitor", daemon=True).start()

    def _monitor_processes(self) -> None:
        while not self.chrome_closed_event.is_set():
            active = [proc.poll() is None for proc in self.processes]
            if any(active):
                time.sleep(1.5)
            else:
                self.chrome_closed_event.set()
                break

    def interactive_loop(self) -> None:
        if not self.processes:
            return
        print("\nChrome 窗口已启动。可用命令：")
        print("  cookie <网址>  —— 导出该域名的 Cookie")
        print("  help          —— 查看帮助")
        print("  exit          —— 退出交互（不会关闭 Chrome）\n")

        while not self.chrome_closed_event.is_set():
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n收到退出指令，退出交互模式。")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit"}:
                print("已退出交互模式，Chrome 仍在运行。")
                break
            if user_input.lower() in {"help", "?"}:
                print("可用命令：")
                print("  cookie <网址> —— 导出该域名的 Cookie")
                print("  help          —— 查看帮助")
                print("  exit          —— 退出交互（不会关闭 Chrome）")
                continue
            if user_input.lower().startswith("cookie "):
                url = user_input[7:].strip()
                if not url:
                    print("请输入需要导出 Cookie 的网址，例如 `cookie https://example.com`。")
                    continue
                try:
                    domain = self._normalize_domain(url)
                except ValueError as exc:
                    print(f"无法解析域名：{exc}")
                    continue
                try:
                    output_file = self._export_cookies(domain)
                    if output_file:
                        print(f"Cookie 已导出到：{output_file}")
                    else:
                        print("未在任何临时目录中找到该域名的 Cookie。")
                except Exception as exc:  # pragma: no cover - runtime error
                    print(f"导出 Cookie 时出现错误：{exc}")
                continue

            print("未知命令，可输入 `help` 查看帮助。")

    def wait_for_chrome_exit(self) -> None:
        if not self.processes:
            return
        print("\n正在监控 Chrome 进程，关闭所有窗口后将执行清理流程……")
        self.chrome_closed_event.wait()

    def prompt_cleanup(self) -> None:
        if not self.created_directories:
            return
        print("\n检测到当前会话的 Chrome 已全部关闭。")
        print("本次将处理以下目录：")
        for path in self.created_directories:
            print(f"  - {path}")

        while True:
            choice = input("是否删除上述目录？[Y/n]: ").strip().lower()
            if choice in {"", "y", "yes"}:
                self._cleanup_directories()
                self._update_directory_record(cleaned=True)
                break
            if choice in {"n", "no"}:
                print("已选择保留临时目录，你可以稍后手动删除。")
                self._update_directory_record(cleaned=False)
                break
            print("请输入 Y 或 N。")

    def shutdown(self) -> None:
        # 用于 main 函数 finally 调用，当前无需额外操作
        pass

    def _cleanup_directories(self) -> None:
        print("\n正在清理……")
        for path in sorted(self.created_directories, key=lambda p: len(str(p)), reverse=True):
            if path.exists():
                try:
                    shutil.rmtree(path)
                    print(f"已删除 {path}")
                except Exception as exc:  # pragma: no cover - deletion error
                    print(f"删除 {path} 失败：{exc}")
        print("清理完成。")

    def _update_directory_record(self, cleaned: bool) -> None:
        self._directory_record["cleanup"] = {
            "performed": cleaned,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
        self._write_directory_record()

    def _write_directory_record(self) -> None:
        with open(self._directory_record_path, "w", encoding="utf-8") as fp:
            json.dump(self._directory_record, fp, indent=2, ensure_ascii=False)

    def _get_chrome_path(self) -> str:
        chrome_path = str(self.config.get("chrome_path", "")).strip()
        if not chrome_path:
            raise ValueError("请在 config.json 中配置 chrome_path。")
        if not os.path.exists(chrome_path):
            raise FileNotFoundError(f"Chrome 不存在：{chrome_path}")
        return chrome_path

    def _get_default_urls(self) -> List[str]:
        urls = self.config.get("default_urls", [])
        if not isinstance(urls, list):
            return []
        return [str(u).strip() for u in urls if str(u).strip()]

    def _normalize_domain(self, url: str) -> str:
        parsed = urlparse(url)
        netloc = parsed.netloc or parsed.path
        netloc = netloc.split("/")[0]
        if not netloc:
            raise ValueError("缺少域名信息。")
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if not netloc:
            raise ValueError("无法从输入中提取域名。")
        return netloc.lower()

    def _export_cookies(self, domain: str) -> Optional[Path]:
        if bool(self.config.get("use_incognito", False)):
            print("当前启用了无痕模式，Chrome 不会写入 Cookie，无法导出。")
            return None

        collected: List[Dict[str, object]] = []
        for profile_dir in self.created_directories[1:]:  # 忽略 base 目录
            if not profile_dir.exists():
                continue
            local_state = profile_dir / "Local State"
            if not local_state.exists():
                continue
            try:
                key = self._load_encryption_key(local_state)
            except Exception as exc:
                print(f"读取 {profile_dir} 的加密密钥失败：{exc}")
                continue

            cookie_db = self._locate_cookie_db(profile_dir)
            if not cookie_db:
                continue

            fd, temp_name = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            temp_copy = Path(temp_name)
            try:
                shutil.copy2(cookie_db, temp_copy)
                collected.extend(self._read_cookie_db(temp_copy, key, domain, profile_dir))
            finally:
                try:
                    temp_copy.unlink(missing_ok=True)
                except TypeError:
                    if temp_copy.exists():
                        temp_copy.unlink()

        if not collected:
            return None

        output_dir = Path(str(self.config.get("cookie_output_dir", "")).strip() or "D:/ai translate/cookie")
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "".join(random.choices(string.digits, k=4))
        sanitized_domain = self._sanitize_filename(domain)
        output_path = output_dir / f"{sanitized_domain}_{suffix}.txt"

        output_data = {
            "domain": domain,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "cookies": collected,
        }
        with open(output_path, "w", encoding="utf-8") as fp:
            json.dump(output_data, fp, ensure_ascii=False, indent=2)
        return output_path

    def _read_cookie_db(
        self,
        db_path: Path,
        key: bytes,
        domain: str,
        profile_dir: Path,
    ) -> List[Dict[str, object]]:
        records: List[Dict[str, object]] = []
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly, samesite "
                "FROM cookies"
            )
            for row in cursor.fetchall():
                host_key = row[0] or ""
                target_host = host_key.lstrip(".")
                if not target_host.endswith(domain):
                    continue
                name = row[1]
                value = row[2]
                encrypted_value = row[3]
                path_value = row[4]
                expires_utc = row[5]
                is_secure = bool(row[6])
                is_http_only = bool(row[7])
                same_site = row[8]

                if value:
                    cookie_value = value
                else:
                    cookie_value = self._decrypt_cookie_value(encrypted_value, key)

                records.append(
                    {
                        "source_profile": str(profile_dir),
                        "host": host_key,
                        "name": name,
                        "value": cookie_value,
                        "path": path_value,
                        "is_secure": is_secure,
                        "is_http_only": is_http_only,
                        "same_site": same_site,
                        "expires_utc": expires_utc,
                        "expires_iso": self._format_chrome_time(expires_utc),
                    }
                )
        finally:
            conn.close()
        return records

    def _decrypt_cookie_value(self, encrypted_value: bytes, key: bytes) -> str:
        if encrypted_value is None:
            return ""
        if encrypted_value.startswith(b"v10"):
            nonce = encrypted_value[3:15]
            cipher = AESGCM(key)
            decrypted = cipher.decrypt(nonce, encrypted_value[15:], None)
            return decrypted.decode("utf-8", errors="ignore")
        decrypted = self._dpapi.decrypt(encrypted_value)
        return decrypted.decode("utf-8", errors="ignore")

    def _load_encryption_key(self, local_state_path: Path) -> bytes:
        with open(local_state_path, "r", encoding="utf-8") as fp:
            local_state = json.load(fp)
        encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key_b64:
            raise ValueError("Local State 中缺少 encrypted_key。")
        encrypted_key = base64.b64decode(encrypted_key_b64)
        if encrypted_key.startswith(b"DPAPI"):
            encrypted_key = encrypted_key[5:]
        return self._dpapi.decrypt(encrypted_key)

    def _locate_cookie_db(self, profile_dir: Path) -> Optional[Path]:
        candidates = [
            profile_dir / "Default" / "Network" / "Cookies",
            profile_dir / "Default" / "Cookies",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _format_chrome_time(self, chrome_timestamp: int) -> Optional[str]:
        if not chrome_timestamp:
            return None
        try:
            epoch_start = datetime(1601, 1, 1)
            delta = timedelta(microseconds=chrome_timestamp)
            return (epoch_start + delta).isoformat()
        except OverflowError:
            return None

    def _sanitize_filename(self, name: str) -> str:
        invalid = '<>:\"/\\|?*'
        sanitized = "".join("_" if ch in invalid else ch for ch in name)
        return sanitized or "domain"


def load_config() -> Dict[str, object]:
    config_path = Path(__file__).resolve().parent / "config.json"
    if not config_path.exists():
        raise FileNotFoundError("未找到 config.json，请先复制 config.example.json 并按需修改。")
    with open(config_path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def ask_window_count() -> int:
    while True:
        raw = input("请输入需要打开的窗口数量: ").strip()
        try:
            value = int(raw)
        except ValueError:
            print("请输入有效的数字。")
            continue
        if value <= 0:
            print("数量必须大于 0。")
            continue
        return value


def main() -> None:
    ensure_windows()
    try:
        config = load_config()
    except Exception as exc:
        print(f"加载配置失败：{exc}")
        sys.exit(1)

    manager = SandboxManager(config)
    try:
        window_count = ask_window_count()
        manager.launch_chrome_instances(window_count)
        manager.interactive_loop()
        manager.wait_for_chrome_exit()
        manager.prompt_cleanup()
    finally:
        manager.shutdown()
        print("\n会话结束。")


if __name__ == "__main__":
    main()
