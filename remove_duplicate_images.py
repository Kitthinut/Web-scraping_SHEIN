import argparse
import hashlib
import os
import shutil
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
IMAGE_ROOT = PROJECT_DIR / "All_blouses"
QUARANTINE_ROOT = PROJECT_DIR / "duplicate_quarantine"
IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_duplicates(root: Path) -> list[tuple[Path, Path]]:
    if root.is_symlink() or not root.is_dir():
        raise FileNotFoundError(f"Image folder not found: {root}")

    files: list[Path] = []
    for current_directory, directory_names, file_names in os.walk(
        root, followlinks=False
    ):
        directory_names[:] = [
            name
            for name in directory_names
            if not (Path(current_directory) / name).is_symlink()
        ]
        files.extend(
            Path(current_directory) / name
            for name in file_names
            if (Path(current_directory) / name).suffix.lower() in IMAGE_EXTENSIONS
            and not (Path(current_directory) / name).is_symlink()
        )

    files.sort(
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )

    first_by_hash: dict[str, Path] = {}
    duplicates: list[tuple[Path, Path]] = []

    for path in files:
        digest = sha256_file(path)
        original = first_by_hash.get(digest)
        if original is None:
            first_by_hash[digest] = path
        else:
            duplicates.append((path, original))

    return duplicates


def quarantine_duplicate(path: Path, root: Path, quarantine: Path) -> Path:
    if quarantine.is_symlink():
        raise ValueError(f"Quarantine folder must not be a symlink: {quarantine}")

    relative_path = path.relative_to(root)
    destination = quarantine / relative_path
    parent = destination.parent
    while parent != quarantine.parent:
        if parent.is_symlink():
            raise ValueError(f"Quarantine path must not contain symlinks: {parent}")
        if parent == quarantine:
            break
        parent = parent.parent
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        number = 2
        while True:
            candidate = destination.with_name(
                f"{destination.stem}.duplicate-{number}{destination.suffix}"
            )
            if not candidate.exists():
                destination = candidate
                break
            number += 1

    shutil.move(str(path), str(destination))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Find byte-for-byte duplicate images anywhere under All_blouses. "
            "By default, only show what would be moved."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Move duplicate copies to duplicate_quarantine instead of previewing.",
    )
    args = parser.parse_args()

    duplicates = find_duplicates(IMAGE_ROOT)
    if not duplicates:
        print("No byte-for-byte duplicate images found.")
        return

    print(f"Found {len(duplicates)} duplicate image(s):")
    for duplicate, original in duplicates:
        print(
            f"  {duplicate.relative_to(IMAGE_ROOT)} matches "
            f"{original.relative_to(IMAGE_ROOT)}"
        )

    if not args.apply:
        print(
            "\nPreview only; no files were changed. "
            "Re-run with --apply to quarantine duplicates."
        )
        return

    for duplicate, _ in duplicates:
        destination = quarantine_duplicate(duplicate, IMAGE_ROOT, QUARANTINE_ROOT)
        print(
            f"Moved {duplicate.relative_to(IMAGE_ROOT)} to "
            f"{destination.relative_to(PROJECT_DIR)}"
        )

    print(f"\nMoved {len(duplicates)} duplicate image(s) to {QUARANTINE_ROOT}.")


if __name__ == "__main__":
    main()
