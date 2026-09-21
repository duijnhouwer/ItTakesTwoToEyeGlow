"""Headless activity batch analysis with atomic JSONL publication."""
from concurrent.futures import CancelledError
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import numpy as np
from eyeglow_egobody.egobody.loading import load_recording
from eyeglow_egobody.export.paths import safe_destination
from eyeglow_egobody.model.parameters import OpticalParameters
from eyeglow_egobody.model.panel_settings import setting_specs
from .visibility import analyze_recording


def segment_result(info, segment, recording, result):
    weights = np.diff(recording.timestamps)
    mask = (recording.frame_ids[:-1] >= segment.start) & (recording.frame_ids[:-1] < segment.end)
    selected = float(weights[mask].sum())
    directions = {}
    for p, name in enumerate(('a_sees_b_eyeglow', 'b_sees_a_eyeglow')):
        states = result.states[p, :-1]
        usable = float(weights[mask & (states >= 0)].sum())
        visible = float(weights[mask & (states > 0)].sum())
        directions[name] = dict(selected_duration_s=selected, usable_duration_s=usable,
                                excluded_invalid_duration_s=selected-usable,
                                visible_duration_s=visible,
                                percentage=100*visible/usable if usable else None)
    people = {}
    for p, name in enumerate(('a', 'b')):
        labels = segment.labels(p)
        people[name] = dict(body_index=info.body_indices[p], labels=labels,
                           original_labels=sorted({a.original for a in segment.annotations[p]}),
                           annotations=[asdict(a) for a in segment.annotations[p]],
                           multiple_annotations=len(segment.annotations[p]) > 1,
                           label_conflict=len(labels) > 1)
    return dict(record_type='segment', recording_id=info.name,
                motion_source_key=getattr(recording, 'metadata', {}).get('source_key'),
                source_frame_start=segment.start, source_frame_end_exclusive=segment.end,
                selected_duration_s=selected, **people, **directions)


def run_batch(infos, catalog, selections, settings, model_dir, destination,
              cancelled, progress=lambda current, total: None, overwrite=False):
    settings = deepcopy(settings)
    selections = tuple(tuple(sorted(s)) for s in selections)
    if not all(selections):
        raise ValueError('Select at least one action for each participant.')
    parameters = OpticalParameters.from_settings({k: v['value'] for k, v in setting_specs(settings).items()})
    destination = safe_destination(destination)
    if destination.suffix.lower() != '.jsonl':
        raise ValueError('Choose a .jsonl output file.')
    for info in infos:
        if destination.is_relative_to(info.root.resolve()):
            raise ValueError('The dataset is read-only.')
    jobs = [(info, tuple(catalog.segments(info, selections))) for info in infos]
    jobs = [(info, segments) for info, segments in jobs if segments]
    if not jobs:
        raise ValueError('No time matches both action selections.')
    def check():
        if cancelled.is_set():
            raise CancelledError()
    metadata = dict(record_type='metadata', schema_version=1,
                    created_at=datetime.now(timezone.utc).isoformat(), analysis_version='activity-eyeglow-v1',
                    annotation_source=dict(path=str(catalog.path.resolve()), sha256=catalog.sha256),
                    dataset_roots=sorted({str(i.root.resolve()) for i in infos}),
                    recording_ids=[i.name for i in infos],
                    normalization='Remove trailing _clip<number>; collapse whitespace/underscores to underscore',
                    interval_convention='[start, end); final sample has zero duration',
                    selection_rule='A matches AND B matches; any active label may match each side',
                    selections=dict(a=selections[0], b=selections[1]),
                    roles=dict(a='camera wearer', b='interactee'),
                    visibility_definition='Potential visibility of at least one active eye glow of the other participant',
                    settings_current=settings)
    temporary = None
    try:
        check()
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destination.parent,
                                         prefix='.activity-', suffix='.jsonl', delete=False) as stream:
            temporary = Path(stream.name)
            def write(record):
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + '\n')
            write(metadata)
            progress(0, len(jobs))
            for index, (info, segments) in enumerate(jobs):
                check()
                recording = load_recording(info, model_dir, cancelled=cancelled)
                check()
                result = analyze_recording(recording, parameters)
                for segment in segments:
                    check()
                    write(segment_result(info, segment, recording, result))
                progress(index+1, len(jobs))
        check()
        if overwrite:
            os.replace(temporary, destination)
        else:
            os.link(temporary, destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
