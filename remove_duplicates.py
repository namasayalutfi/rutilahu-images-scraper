#!/usr/bin/env python3
"""
remove_duplicates.py

Detect and optionally remove or move duplicate images in a folder.

Usage examples:
# Dry run (default moves duplicates to <folder>/duplicates):
python remove_duplicates.py --folder "C:\path\to\images"

# Move duplicates to custom folder:
python remove_duplicates.py --folder "C:\path\to\images" --move-to "C:\path\to\dups"

# Permanently delete duplicates (be careful):
python remove_duplicates.py --folder "C:\path\to\images" --delete

# Change perceptual threshold (smaller = stricter):
python remove_duplicates.py --folder "C:\path\to\images" --threshold 4
"""

import os
import sys
import argparse
import hashlib
import shutil
from PIL import Image

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff'}


def is_image_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in IMAGE_EXTS


def compute_md5(path: str, block_size: int = 65536) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(block_size), b''):
            h.update(block)
    return h.hexdigest()


def average_hash(path: str, hash_size: int = 8) -> int:
    """
    Compute average hash (aHash) and return as integer.
    Steps:
    - convert to grayscale
    - resize to (hash_size x hash_size)
    - compute mean and set bits above mean to 1
    """
    try:
        with Image.open(path) as img:
            img = img.convert('L').resize((hash_size, hash_size), Image.Resampling.LANCZOS)
            pixels = list(img.getdata())
    except Exception as e:
        raise RuntimeError(f"Cannot process image {path}: {e}")

    avg = sum(pixels) / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p > avg:
            bits |= 1 << i
    return bits  # integer representation


def hamming_distance(a: int, b: int) -> int:
    x = a ^ b
    # Python 3.8+: int.bit_count(); fallback for older versions:
    try:
        return x.bit_count()
    except AttributeError:
        # portable fallback
        return bin(x).count("1")


def find_images(folder: str):
    files = []
    for root, _, filenames in os.walk(folder):
        for fn in filenames:
            p = os.path.join(root, fn)
            if is_image_file(p):
                files.append(p)
    return sorted(files)


def main(args):
    folder = os.path.abspath(args.folder)
    if not os.path.isdir(folder):
        print("Folder not found:", folder)
        sys.exit(1)

    move_to = args.move_to or os.path.join(folder, "duplicates")
    os.makedirs(move_to, exist_ok=True)

    files = find_images(folder)
    print(f"Found {len(files)} image files in {folder}")

    # 1) exact duplicates via MD5
    md5_map = {}
    print("Computing MD5 for exact duplicates...")
    for p in files:
        try:
            md5 = compute_md5(p)
        except Exception as e:
            print("  [MD5 error] ", p, "->", e)
            continue
        md5_map.setdefault(md5, []).append(p)

    to_remove = set()
    # mark exact duplicates (keep first occurrence)
    for md5, paths in md5_map.items():
        if len(paths) > 1:
            keeper = paths[0]
            dups = paths[1:]
            for d in dups:
                to_remove.add(d)
            print(f"Exact duplicates ({len(paths)}): keep {os.path.basename(keeper)}; mark {len(dups)} duplicates")

    # 2) perceptual duplicates for remaining files
    print("Computing perceptual hashes for remaining images...")
    hash_map = {}      # path -> ahash_int
    seen = {}          # ahash_int -> keeper_path (representative)
    hash_size = args.hash_size
    threshold = args.threshold

    # Only check images not already marked for remove (exact dups)
    remaining_files = [p for p in files if p not in to_remove]

    for p in remaining_files:
        try:
            ah = average_hash(p, hash_size=hash_size)
            hash_map[p] = ah
        except Exception as e:
            print("  [aHash error]", p, "->", e)
            continue

    print(f"Computed perceptual hash for {len(hash_map)} images. Comparing with threshold={threshold}...")

    # compare each image against current keepers
    keepers = []
    for p, ah in hash_map.items():
        matched = False
        for k_path, k_ah in keepers:
            dist = hamming_distance(ah, k_ah)
            if dist <= threshold:
                # mark p as duplicate of k_path
                to_remove.add(p)
                matched = True
                print(f"Perceptual duplicate: {os.path.basename(p)} ~= {os.path.basename(k_path)} (hamming={dist})")
                break
        if not matched:
            keepers.append((p, ah))

    # Summary
    print(f"\nTOTAL images: {len(files)}")
    print(f"Marked for removal (exact + perceptual): {len(to_remove)}")

    if not to_remove:
        print("No duplicates found. Exiting.")
        return

    # Action: move or delete
    if args.delete:
        confirm = args.yes
        if not confirm:
            ans = input("Are you sure you want to PERMANENTLY DELETE the duplicates? Type YES to confirm: ")
            if ans.strip() != "YES":
                print("Aborted by user.")
                return
        print("Permanently deleting duplicates...")
        deleted = 0
        for p in sorted(to_remove):
            try:
                os.remove(p)
                deleted += 1
                print("Deleted:", p)
            except Exception as e:
                print("Failed to delete:", p, "->", e)
        print(f"Deleted {deleted} files.")
    else:
        print(f"Moving duplicates to: {move_to}")
        moved = 0
        for p in sorted(to_remove):
            try:
                base = os.path.basename(p)
                dest = os.path.join(move_to, base)
                # avoid overwriting
                i = 1
                orig_dest = dest
                while os.path.exists(dest):
                    name, ext = os.path.splitext(base)
                    dest = os.path.join(move_to, f"{name}_{i}{ext}")
                    i += 1
                shutil.move(p, dest)
                moved += 1
                print("Moved:", p, "->", dest)
            except Exception as e:
                print("Failed to move:", p, "->", e)
        print(f"Moved {moved} files to {move_to}")

    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove or move duplicate images in a folder.")
    parser.add_argument("--folder", "-f", required=True, help="Target folder containing images.")
    parser.add_argument("--move-to", "-m", default=None, help="Folder to move duplicates into (default: <folder>/duplicates).")
    parser.add_argument("--delete", action="store_true", help="Permanently delete duplicates instead of moving.")
    parser.add_argument("--yes", action="store_true", help="Assume YES for delete confirmation.")
    parser.add_argument("--hash-size", dest="hash_size", type=int, default=8, help="Hash size for aHash (default 8 -> 64-bit).")
    parser.add_argument("--threshold", type=int, default=5, help="Hamming distance threshold for perceptual duplicates (default 5). Smaller = stricter.")
    args = parser.parse_args()
    main(args)