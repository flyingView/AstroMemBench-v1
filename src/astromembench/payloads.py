"""Convert public task payloads to identical original image attachments."""
from __future__ import annotations

import base64
from hashlib import sha256
import mimetypes
import re
from pathlib import Path


def attach_images(value, asset_root: Path):
    return _attach_images(value, asset_root, [0])


def image_references(value):
    """Walk attachment arrays, retaining repeats and unseen runtime branches.

    Evaluator state may also use ``images`` for an inventory mapping (C3-O1).
    Those keys name simulated objects, not files to deliver.
    """
    if isinstance(value, list):
        for item in value:
            yield from image_references(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == 'images' and isinstance(item, list):
                yield from item
            else:
                yield from image_references(item)


def resolve_image(reference, asset_root, number):
    """The freeze and delivery paths share one attachment contract."""
    if isinstance(reference, dict):
        if set(reference) != {'id', 'path'} or not isinstance(reference['id'], str) or not re.fullmatch(r'(?:I[0-9]{2}|C01)', reference['id']):
            raise ValueError('Image references require a neutral identifier and evaluator-owned path')
        public_id, relative = reference['id'], reference['path']
    else:
        public_id, relative = f'image-{number}', reference
    if not isinstance(relative, str):
        raise ValueError('Image attachment path must be text')
    root = Path(asset_root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Image attachment must belong to the declared asset directory')
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in {'image/png', 'image/jpeg', 'image/webp'}:
        raise ValueError('Unsupported original image attachment format')
    return public_id, path, mime


def _attach_images(value, asset_root: Path, counter):
    if isinstance(value, list):
        return [_attach_images(item, asset_root, counter) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if key != "images":
            result[key] = _attach_images(item, asset_root, counter)
            continue
        if not isinstance(item, list):
            raise ValueError('Public images must be an attachment list')
        result[key] = []
        for reference in item:
            counter[0] += 1
            public_id, path, mime = resolve_image(reference, asset_root, counter[0])
            result[key].append({"id": public_id, "mime_type": mime,
                                "data_base64": base64.b64encode(path.read_bytes()).decode("ascii")})
    return result


PRIVATE_FIELDS = {"category", "execution", "world", "rubric", "design", "terminal_facts", "scoring_version",
                  "minimum_safe_energy", "correct_operation", "correct_action", "sufficient_evidence", "required_evidence",
                  "initial_status", "late_confirmations", "new_confirmations", "late_trigger", "snapshot_stage",
                  "correct_location", "match_index", "source_cluster", "source_record", "background_seed",
                  "tracker_xyz_m", "tracker_quaternion_xyzw", "camera_heading_deg", "original_path", "original_sha256",
                  "correct_landmark_id", "match_score", "match_rank", "offline_sift_diagnostic"}


def check_packet(value, image_hashes=None):
    if isinstance(value, list):
        for child in value:
            check_packet(child, image_hashes)
    elif isinstance(value, dict):
        if PRIVATE_FIELDS.intersection(value):
            raise ValueError("Evaluator fields leaked into public input: " + str(sorted(PRIVATE_FIELDS.intersection(value))))
        for key, child in value.items():
            if key == "images":
                if not isinstance(child, list):
                    raise ValueError('Public images must be an attachment list')
                for image in child:
                    if set(image) != {"id", "mime_type", "data_base64"}:
                        raise ValueError("Image packet contains source or evaluator metadata")
                    if (not isinstance(image['id'], str)
                            or not re.fullmatch(r'(?:I[0-9]{2}|C01|image-[1-9][0-9]*)', image['id'])
                            or image['mime_type'] not in {'image/png', 'image/jpeg', 'image/webp'}
                            or not isinstance(image['data_base64'], str)):
                        raise ValueError('Image packet requires a neutral identifier, image MIME type and encoded bytes')
                    pixels = base64.b64decode(image['data_base64'], validate=True)
                    if image_hashes is not None:
                        image_hashes.append(sha256(pixels).hexdigest())
            else:
                check_packet(child, image_hashes)
    elif isinstance(value, str) and any(marker in value for marker in (
            'landmarks/', 'NASA-地标-', 'question-bindings.json', 'source-and-pairing.md',
            'science.nasa.gov/', 'original_sha256')):
        raise ValueError("Visual source information leaked into public text")
