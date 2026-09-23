import json

import pytest

from eyeglow_egobody.ui.visibility_report import (PieChart, VisibilityReportDialog,
                                                   load_visibility_report)


def write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


def test_visibility_report_aggregates_durations_and_excludes_invalid(tmp_path):
    path = tmp_path / 'activity-analysis.jsonl'
    metadata = dict(record_type='metadata', schema_version=1,
                    analysis_version='activity-eyeglow-v1')
    def segment(a, b):
        return dict(record_type='segment', a_sees_b_eyeglow=a, b_sees_a_eyeglow=b)
    write_jsonl(path, [metadata,
        segment(dict(visible_duration_s=2, usable_duration_s=5,
                     excluded_invalid_duration_s=1),
                dict(visible_duration_s=4, usable_duration_s=5,
                     excluded_invalid_duration_s=1)),
        segment(dict(visible_duration_s=1.5, usable_duration_s=2,
                     excluded_invalid_duration_s=0),
                dict(visible_duration_s=0, usable_duration_s=2,
                     excluded_invalid_duration_s=0))])
    report = load_visibility_report(path)
    assert report.segment_count == 2
    assert report.a_sees_b.visible_s == 3.5
    assert report.a_sees_b.invisible_s == 3.5
    assert report.a_sees_b.excluded_invalid_s == 1
    assert report.b_sees_a.visible_s == 4
    assert report.b_sees_a.invisible_s == 3


@pytest.mark.parametrize('rows, message', [
    ([], 'empty'),
    ([{'record_type': 'metadata', 'schema_version': 2,
       'analysis_version': 'activity-eyeglow-v1'}], 'supported'),
    ([{'record_type': 'metadata', 'schema_version': 1,
       'analysis_version': 'activity-eyeglow-v1'}], 'no activity segments'),
])
def test_visibility_report_rejects_wrong_or_incomplete_files(tmp_path, rows, message):
    path = tmp_path / 'bad.jsonl'
    write_jsonl(path, rows)
    with pytest.raises(ValueError, match=message):
        load_visibility_report(path)


def test_visibility_report_dialog_contains_two_directional_charts(qt_app, tmp_path):
    path = tmp_path / 'activity-analysis.jsonl'
    direction = dict(visible_duration_s=3, usable_duration_s=4,
                     excluded_invalid_duration_s=2)
    write_jsonl(path, [
        dict(record_type='metadata', schema_version=1,
             analysis_version='activity-eyeglow-v1'),
        dict(record_type='segment', a_sees_b_eyeglow=direction,
             b_sees_a_eyeglow=direction)])
    dialog = VisibilityReportDialog(load_visibility_report(path), path, None)
    charts = dialog.findChildren(PieChart)
    assert [chart.title for chart in charts] == ["Person A: B's EyeGlow",
                                                 "Person B: A's EyeGlow"]
    assert charts[0].duration.visible_s == 3
    assert charts[0].duration.invisible_s == 1
    dialog.show()
    qt_app.processEvents()
    assert not dialog.grab().isNull()
    dialog.close()
