from __future__ import annotations

import argparse
import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx


def _content_length(url: str) -> int:
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        response = client.head(url)
        response.raise_for_status()
        return int(response.headers["content-length"])


def _download_part(url: str, part_path: Path, start: int, end: int) -> tuple[int, int]:
    expected_size = end - start + 1
    if part_path.exists() and part_path.stat().st_size == expected_size:
        return start, expected_size

    tmp_path = part_path.with_suffix(part_path.suffix + ".tmp")
    headers = {"Range": f"bytes={start}-{end}"}
    written = 0
    with httpx.Client(follow_redirects=True, timeout=None) as client:
        with client.stream("GET", url, headers=headers) as response:
            if response.status_code != 206:
                raise RuntimeError(f"server did not honor range request: {response.status_code}")
            response.raise_for_status()
            with tmp_path.open("wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    if not chunk:
                        continue
                    handle.write(chunk)
                    written += len(chunk)

    if written != expected_size:
        raise RuntimeError(f"part size mismatch for {part_path.name}: {written} != {expected_size}")
    tmp_path.replace(part_path)
    return start, written


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, output: Path, expected_md5: str | None, workers: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    total_size = _content_length(url)
    part_dir = output.with_suffix(output.suffix + ".parts")
    part_dir.mkdir(parents=True, exist_ok=True)

    part_size = (total_size + workers - 1) // workers
    ranges: list[tuple[Path, int, int]] = []
    for index in range(workers):
        start = index * part_size
        if start >= total_size:
            continue
        end = min(total_size - 1, start + part_size - 1)
        ranges.append((part_dir / f"part-{index:03d}", start, end))

    print(f"download_start url={url} size={total_size} workers={len(ranges)}")
    completed = 0
    with ThreadPoolExecutor(max_workers=len(ranges)) as executor:
        futures = [
            executor.submit(_download_part, url, part_path, start, end)
            for part_path, start, end in ranges
        ]
        for future in as_completed(futures):
            _, written = future.result()
            completed += written
            print(f"part_done downloaded={completed}/{total_size}")

    tmp_output = output.with_suffix(output.suffix + ".tmp")
    with tmp_output.open("wb") as out:
        for part_path, _, _ in ranges:
            with part_path.open("rb") as part:
                for chunk in iter(lambda: part.read(1024 * 1024), b""):
                    out.write(chunk)
    tmp_output.replace(output)

    actual_size = output.stat().st_size
    if actual_size != total_size:
        raise RuntimeError(f"final size mismatch: {actual_size} != {total_size}")

    actual_md5 = _md5(output)
    if expected_md5 and actual_md5.lower() != expected_md5.lower():
        raise RuntimeError(f"md5 mismatch: {actual_md5} != {expected_md5}")

    print(f"download_done path={output} size={actual_size} md5={actual_md5}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download one large file with HTTP range requests.")
    parser.add_argument("url")
    parser.add_argument("output", type=Path)
    parser.add_argument("--md5")
    parser.add_argument("--workers", type=int, default=max(2, min(8, (os.cpu_count() or 4))))
    args = parser.parse_args()
    download(args.url, args.output, args.md5, args.workers)


if __name__ == "__main__":
    main()
