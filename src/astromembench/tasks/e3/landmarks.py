"""Shared visual attachment and offline audit mechanics, never a scoring judge."""
import base64
from hashlib import sha256
import json
from pathlib import Path

from ..decisions import DecisionRuntime
from .locations import report_command

HISTORY_FILES = ('a01', 'a03', 'a05', 'a07', 'a09', 'a10', 'a11', 'a12', 'a13')
QUERY_FILES = ('a02', 'a04', 'a06', 'a08')
VISUAL_REVISION = 'NASA-landmark-20261010-sized'
VISUAL_INPUT_NOTE = ('照片保留完整画面，使用 LANCZOS 等比例缩小；常规主图长边为1280或1536，'
                     '宽幅全景为4096，原本较小的三张JPEG保持原样。JPEG质量92、4:4:4；'
                     'P1当前参考图册长边640，a07保留PNG，其余使用同参数JPEG。')


def attachment(identifier, stem):
    return {'id': identifier, 'path': f'landmarks/{stem}.jpg'}


def gallery_attachment(identifier, stem):
    extension = 'png' if stem == 'a07' else 'jpg'
    return {'id': identifier, 'path': f'landmarks/p1-gallery/{stem}.{extension}'}


def report_cases(task, facts, solution):
    return [([{'action': 'select', 'option': row['option']}],
             100 if row['operation']['location'] == facts['current_location'] else 0)
            for row in task.public['actions']] + [([{}], 0), ([{'action': 'end'}], 0)]


class LandmarkRuntime(DecisionRuntime):
    """Grade the first report against the simulated location, using exact identity."""
    receipt = ''

    def execute(self, operation):
        self.state['reported_location'] = operation['location']
        self.feedback = self.receipt
        return 100 if operation['location'] == self.task.world['current_location'] else 0


def next_action(facts, current):
    return report_command(facts['current_location'])


def image_identity(history, current, assets, *, gallery_derivatives=False):
    """Audit delivered pixels against the independently documented photograph pairs.

    This uses author-reviewed image correspondence only, never a question's N,
    answer, query index or naming book. It verifies the image part of a public
    reconstruction; it does not claim machine vision or run during grading.
    """
    manifest = json.loads((Path(assets)/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('revision') != VISUAL_REVISION:
        raise ValueError('Visual reconstruction requires the reviewed photograph manifest')
    known = {row['sha256']: row for row in manifest['assets']}

    def identity(image, *, gallery=False):
        digest = sha256(base64.b64decode(image['data_base64'], validate=True)).hexdigest()
        if digest not in known:
            raise ValueError('Delivered image has no reviewed correspondence')
        if known[digest].get('derived_from') and not (gallery and gallery_derivatives):
            raise ValueError('Historical and query photographs must use reviewed main images')
        return digest, known[digest]['object']

    images = {}
    for event in history:
        for record in event['data']['records']:
            for image in record.get('images', []):
                if image['id'] in images:
                    raise ValueError('Historical image identifier is not unique')
                images[image['id']] = identity(image)
    queries = [image for image in current['images'] if image['id'] == 'C01']
    if len(queries) != 1:
        raise ValueError('Exactly one current image is required')
    query_hash, query_object = identity(queries[0])
    matches = [identifier for identifier, (_, obj) in images.items() if obj == query_object]
    if len(matches) != 1:
        raise ValueError('Current photograph needs one reviewed historical counterpart')
    gallery = [image for image in current['images'] if image['id'] != 'C01']
    if gallery:
        if len(gallery) != len(images) or {image['id'] for image in gallery} != images.keys():
            raise ValueError('Current gallery must contain every historical image exactly once')
        for image in gallery:
            digest, obj = identity(image,gallery=True)
            original_hash, original_object = images[image['id']]
            if digest == original_hash:
                continue
            if (obj != original_object or known[digest].get('derived_from') != {
                    'path':known[original_hash]['path'],'sha256':original_hash}):
                raise ValueError('Current gallery does not derive from its historical photograph')
    return {'matched_image': matches[0], 'query_sha256': query_hash,
            'gallery_images': {image['id']: {'sha256':identity(image,gallery=True)[0]} for image in gallery},
            'history_images': {identifier: {'sha256': digest} for identifier, (digest, _) in images.items()}}


def check_world(task, facts):
    if facts['current_location'] != task.world['current_location']:
        raise ValueError('Public visual registration disagrees with the physical location')
    if facts['registrations'] != task.world['registrations']:
        raise ValueError('Public registration chain differs from the authored map')
