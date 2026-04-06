"""Pretty-print progress, countdown, and pass/fail output."""

import sys
import time


# ANSI colors
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def header(title: str) -> None:
    print(f"\n{_BOLD}{_CYAN}{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}{_RESET}\n")


def step(n: int, total: int, msg: str) -> None:
    print(f"  {_BOLD}[{n}/{total}]{_RESET} {msg}")


def info(msg: str) -> None:
    print(f"         {msg}")


def passed(msg: str) -> None:
    print(f"         {_GREEN}\u2713 PASS{_RESET}  {msg}")


def failed(msg: str, detail: str = "") -> None:
    print(f"         {_RED}\u2717 FAIL{_RESET}  {msg}")
    if detail:
        print(f"                {_RED}{detail}{_RESET}")


def skipped(msg: str) -> None:
    print(f"         {_YELLOW}- SKIP{_RESET}  {msg}")


def countdown(seconds: int, msg: str) -> None:
    for remaining in range(seconds, 0, -1):
        sys.stdout.write(f"\r         {msg} {remaining}s remaining...  ")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(f"\r         {msg} done.{' ' * 20}\n")
    sys.stdout.flush()


def summary(results: list[tuple[str, bool]]) -> None:
    total = len(results)
    passed_count = sum(1 for _, ok in results if ok)
    failed_count = total - passed_count

    print(f"\n{_BOLD}{'=' * 60}")
    print(f"  RESULTS: {passed_count} passed, {failed_count} failed, {total} total")
    print(f"{'=' * 60}{_RESET}")

    for name, ok in results:
        status = f"{_GREEN}PASS{_RESET}" if ok else f"{_RED}FAIL{_RESET}"
        print(f"  {status}  {name}")

    print()
