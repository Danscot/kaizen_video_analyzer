"""
frame_extractor.py
Extracts visually distinct frames from a video using Mean Absolute Error
between consecutive downscaled grayscale frames. Only triggers when a
significant change occurs, avoiding over-sampling during fluid animations.
"""

import cv2
import numpy as np
import PIL.Image
from pathlib import Path

from core.utils import log, log_warn


def extract_changed_frames(
    video_path: Path,
    threshold: float = 5.0,
    min_frame_gap: int = 30,
) -> list[tuple[int, PIL.Image.Image]]:
    """
    Extract frames that represent visual state changes.

    Args:
        video_path:    Path to the video file.
        threshold:     MAE threshold to trigger extraction (lower = more sensitive).
        min_frame_gap: Minimum frames to skip after each trigger (prevents over-sampling).

    Returns:
        List of (frame_index, PIL.Image) tuples, ordered chronologically.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Could not open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS) or 30
    log(f"  Video: {total} frames @ {fps:.1f} fps  ({total/fps:.1f}s)")

    frames: list[tuple[int, PIL.Image.Image]] = []
    prev_gray = None
    frames_since_trigger = min_frame_gap
    frame_index = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        gray_small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 180))

        if prev_gray is None:
            # Always capture the first frame as baseline
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append((frame_index, PIL.Image.fromarray(rgb)))
            prev_gray = gray_small
            frames_since_trigger = 0
        else:
            mae = np.mean(cv2.absdiff(gray_small, prev_gray))
            if mae > threshold and frames_since_trigger >= min_frame_gap:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append((frame_index, PIL.Image.fromarray(rgb)))
                prev_gray = gray_small
                frames_since_trigger = 0
            else:
                frames_since_trigger += 1

        frame_index += 1

    cap.release()

    if not frames:
        log_warn("No frames extracted. Try lowering the threshold.")

    return frames
