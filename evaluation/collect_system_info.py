from __future__ import annotations
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "evaluation" / "system_info.txt"


def command_output(command: list[str]) -> str:
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
        return result.stdout.strip() or f"returncode={result.returncode}"
    except Exception as exc:
        return f"unavailable: {exc}"


def main() -> None:
    lines = [
        f"Collected: {datetime.now().isoformat(timespec='seconds')}",
        f"Platform: {platform.platform()}",
        f"Machine: {platform.machine()}",
        f"Python: {sys.version.replace(chr(10), ' ')}",
        f"clang-morello: {command_output(['clang-morello', '--version']) if shutil.which('clang-morello') else 'not found'}",
        f"proccontrol: {command_output(['proccontrol', '-h']) if shutil.which('proccontrol') else 'not found'}",
        f"uname -a: {command_output(['uname', '-a'])}",
    ]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"System information saved to: {OUT}")


if __name__ == "__main__":
    main()
