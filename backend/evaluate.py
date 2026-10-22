"""Evaluate Gemini transcription using character and word error rates.

Folder layout: sample1.jpg + sample1.txt, sample2.png + sample2.txt, ...
Usage: python evaluate.py test_data
Requires GEMINI_API_KEY.
"""
import os
import re
import statistics

from PIL import Image
from ocr_utils import extract_text_with_gemini


def edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def cer(ref, hyp):
    ref, hyp = normalize(ref), normalize(hyp)
    return edit_distance(ref, hyp) / max(len(ref), 1)


def wer(ref, hyp):
    ref, hyp = normalize(ref).split(), normalize(hyp).split()
    return edit_distance(ref, hyp) / max(len(ref), 1)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    args = ap.parse_args()

    cers, wers = [], []
    for name in sorted(os.listdir(args.folder)):
        stem, ext = os.path.splitext(name)
        truth = os.path.join(args.folder, stem + ".txt")
        if ext.lower() not in (".jpg", ".jpeg", ".png", ".webp") or not os.path.exists(truth):
            continue
        hyp = extract_text_with_gemini(Image.open(os.path.join(args.folder, name)))
        with open(truth, encoding="utf-8") as handle:
            ref = handle.read()
        cers.append(cer(ref, hyp))
        wers.append(wer(ref, hyp))
        print(f"{name}: CER {cers[-1]:.3f}  WER {wers[-1]:.3f}")
    if not cers:
        raise SystemExit("No image + .txt pairs found.")
    print(f"\nEngine: Gemini  Images: {len(cers)}")
    print(f"Mean CER: {statistics.mean(cers):.3f}  (character accuracy about {100 * (1 - statistics.mean(cers)):.1f}%)")
    print(f"Mean WER: {statistics.mean(wers):.3f}  (word accuracy about {100 * (1 - statistics.mean(wers)):.1f}%)")


if __name__ == "__main__":
    main()
