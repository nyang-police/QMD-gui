#!/usr/bin/env python3
"""
embed_runner.py — PTY proxy for qmd embed
Runs qmd embed in a PTY and outputs parsed progress to stdout as JSON lines.
"""
import pty
import os
import sys
import re
import select
import json


def main():
    force = "--force" in sys.argv

    cmd = ["qmd", "embed"]
    if force:
        cmd.append("-f")

    master, slave = pty.openpty()
    pid = os.fork()

    if pid == 0:
        os.close(master)
        os.dup2(slave, 0)
        os.dup2(slave, 1)
        os.dup2(slave, 2)
        os.close(slave)
        os.execvp(cmd[0], cmd)
    else:
        os.close(slave)
        last_pct = -1

        while True:
            try:
                r, _, _ = select.select([master], [], [], 0.5)
                if r:
                    data = os.read(master, 4096)
                    if not data:
                        break
                    text = data.decode("utf-8", errors="replace")
                    # ANSI escape 제거
                    clean = re.sub(r"\x1b\[[^a-zA-Z]*[a-zA-Z]", "", text)
                    clean = re.sub(r"\x1b\][^\x07]*\x07", "", clean)

                    # 퍼센트 파싱
                    pct_match = re.search(r"(\d{1,3})%", clean)
                    if pct_match:
                        pct = min(int(pct_match.group(1)), 100)
                        if pct != last_pct:
                            last_pct = pct
                            detail = ""
                            detail_match = re.search(
                                r"(\d+/\d+)\s+.*?([\d.]+\s*KB/s)\s+ETA\s+(\w+)", clean
                            )
                            if detail_match:
                                detail = f"{detail_match.group(1)}  {detail_match.group(2)}  ETA {detail_match.group(3)}"
                            msg = {"type": "progress", "pct": pct, "detail": detail}
                            print(json.dumps(msg), flush=True)

                    # 로그 라인 (Done!, Model:, Force 등)
                    for line in clean.split("\n"):
                        line = line.strip().replace("\r", "")
                        if (
                            line
                            and "%" not in line
                            and "█" not in line
                            and "░" not in line
                        ):
                            msg = {"type": "log", "text": line}
                            print(json.dumps(msg), flush=True)

            except OSError:
                break

        _, status = os.waitpid(pid, 0)
        exit_code = os.WEXITSTATUS(status)
        msg = {"type": "done", "exit_code": exit_code}
        print(json.dumps(msg), flush=True)


if __name__ == "__main__":
    main()
