import pytest
from pydantic import ValidationError

from youtube_automation.production.contracts import fingerprint
from youtube_automation.production.graphic_cues import timer_segments
from youtube_automation.production.pictograms import pictogram_ass
from youtube_automation.production.shots import (
    SCHULTE_6X6,
    Overlay,
    SemanticGraphic,
    _graphic_overlays,
)


def test_timer_freezes_before_start_and_keeps_absolute_phase_across_cuts():
    assert timer_segments(0, 100, 100, 220, 40, 10) == [(0, 100, '00:40')]
    assert timer_segments(0, 60, 200, 220, 40, 10) == [
        (0, 30, '00:40'), (30, 40, '00:39'), (40, 50, '00:38'), (50, 60, '00:37')]
    assert timer_segments(0, 15, 235, 220, 40, 10) == [(0, 5, '00:39'), (5, 15, '00:38')]
    assert timer_segments(0, 10, 700, 220, 40, 10) == [(0, 10, '00:00')]


@pytest.mark.parametrize('kwargs', [
    {'kind': 'pictogram'},
    {'kind': 'pictogram', 'icon': 'untrusted drawing commands'},
    {'kind': 'label', 'text': 'x', 'icon': 'eye'},
    {'kind': 'timer', 'text': '00:40', 'clock_start_frame': 100},
    {'kind': 'label', 'text': 'x', 'grid_layout': 'preview'},
])
def test_graphic_metadata_cannot_smuggle_unsupported_content(kwargs):
    with pytest.raises(ValidationError):
        Overlay(start_frame=0, end_frame=30, **kwargs)


def test_preview_keeps_canonical_values_and_ignores_untrusted_geometry():
    board = Overlay(kind='data_grid', preset='schulte_6x6', grid_layout='preview',
                    start_frame=0, end_frame=30, cells=['wrong'], x=.99, width=.99)
    assert board.cells == SCHULTE_6X6
    assert (board.rows, board.columns) == (6, 6)
    assert board.x + board.width <= 1 and board.y + board.height <= 1
    assert board.width < Overlay(kind='data_grid', preset='schulte_6x6', start_frame=0, end_frame=30).width


def test_object_composition_preserves_both_meanings_and_adds_visible_objects():
    graphic = SemanticGraphic(template='comparison', primary_text='وقت ممتع', secondary_text='تحدي انتباه',
                              icons=['phone', 'cursor'])
    overlays = _graphic_overlays(graphic, 90)
    assert {o.text for o in overlays if o.text} == {'وقت ممتع', 'تحدي انتباه'}
    assert {o.icon for o in overlays if o.kind == 'pictogram'} == {'phone', 'cursor'}
    assert all(o.start_frame == 0 and o.end_frame == 90 for o in overlays)


def test_preview_is_an_explanation_layout_not_an_arbitrary_visual_reposition():
    with pytest.raises(ValidationError, match='Only Schulte'):
        SemanticGraphic(template='kinetic_type', primary_text='x', grid_layout='preview')


LEGACY_OVERLAY_PACKETS = [
    {
        'kind': 'label', 'start_frame': 0, 'end_frame': 30, 'text': 'A', 'secondary_text': '',
        'x': 0.1, 'y': 0.1, 'width': 0.3, 'height': 0.15, 'preset': None, 'rows': 0,
        'columns': 0, 'cells': [], 'highlight_cells': [], 'reveal_cells': [], 'points': [],
        'progress': None, 'value_from': None, 'value_to': None, 'target_cell': None,
    },
    {
        'kind': 'timer', 'start_frame': 0, 'end_frame': 60, 'text': '00:40', 'secondary_text': '',
        'x': 0.1, 'y': 0.1, 'width': 0.3, 'height': 0.15, 'preset': None, 'rows': 0,
        'columns': 0, 'cells': [], 'highlight_cells': [], 'reveal_cells': [], 'points': [],
        'progress': None, 'value_from': 40, 'value_to': None, 'target_cell': None,
    },
]


@pytest.mark.parametrize('packet', LEGACY_OVERLAY_PACKETS)
def test_legacy_overlay_packets_keep_their_fingerprints(packet):
    overlay = Overlay.model_validate(packet)
    dumped = overlay.model_dump(mode='json')
    assert dumped == packet
    assert 'motion_to' not in dumped
    assert 'motion_end_frame' not in dumped
    assert fingerprint(overlay) == fingerprint(packet)


def test_pictogram_motion_fields_round_trip_without_changing_legacy_defaults():
    stationary = Overlay(kind='pictogram', icon='cursor', start_frame=0, end_frame=30)
    stationary_dump = stationary.model_dump(mode='json')
    assert 'motion_to' not in stationary_dump
    assert 'motion_end_frame' not in stationary_dump

    moving = Overlay(kind='pictogram', icon='cursor', start_frame=4, end_frame=30,
                     x=.2, y=.2, width=.2, height=.2, motion_to=(.6, .6), motion_end_frame=24)
    moving_dump = moving.model_dump(mode='json')
    assert moving_dump['motion_to'] == [.6, .6]
    assert moving_dump['motion_end_frame'] == 24
    assert Overlay.model_validate(moving_dump).model_dump(mode='json') == moving_dump
    assert fingerprint(moving) == fingerprint(moving_dump)


@pytest.mark.parametrize(('kwargs', 'message'), [
    ({'motion_to': (.5, .5)}, 'provided together'),
    ({'motion_end_frame': 20}, 'provided together'),
    ({'kind': 'label', 'text': 'x', 'motion_to': (.5, .5), 'motion_end_frame': 20},
     'Only pictograms'),
    ({'motion_to': (.9, .5), 'motion_end_frame': 20, 'x': .8, 'width': .2},
     'motion box extends beyond frame'),
    ({'motion_to': (float('nan'), .5), 'motion_end_frame': 20}, 'must be finite'),
    ({'motion_to': (.5, .5), 'motion_end_frame': 4}, 'arrive after start'),
    ({'motion_to': (.5, .5), 'motion_end_frame': 31}, 'by overlay end'),
])
def test_pictogram_motion_stays_paired_inside_its_overlay(kwargs, message):
    options = dict(kwargs)
    kind = options.pop('kind', 'pictogram')
    if kind == 'pictogram':
        options.setdefault('icon', 'cursor')
    with pytest.raises(ValidationError, match=message):
        Overlay(kind=kind, start_frame=4, end_frame=30, **options)


def test_pictogram_ass_moves_every_glyph_component_then_holds():
    stationary = pictogram_ass('cursor', 10, 20, 40, 50)
    moving = pictogram_ass('cursor', 10, 20, 40, 50, move_to=(30, 40), move_ms=500)
    move_tag = r'\move(10,20,30,40,0,500)'

    assert len(moving) == len(stationary) == 2
    assert all(move_tag in component for component in moving)
    assert all(r'\pos(' not in component for component in moving)
    assert [component.replace(move_tag, r'\pos(10,20)') for component in moving] == stationary


@pytest.mark.parametrize('kwargs', [
    {'move_to': (30, 40)},
    {'move_ms': 500},
    {'move_to': (30, 40), 'move_ms': 0},
    {'move_to': (-1, 40), 'move_ms': 500},
])
def test_pictogram_ass_rejects_unpaired_or_invalid_motion(kwargs):
    with pytest.raises(ValueError):
        pictogram_ass('cursor', 10, 20, 40, 50, **kwargs)


def test_non_default_overlay_lineage_fields_remain_serialized():
    full_grid = Overlay(kind='data_grid', preset='schulte_6x6', start_frame=0, end_frame=30)
    preview_grid = Overlay.model_validate({**full_grid.model_dump(mode='json'), 'grid_layout': 'preview'})
    assert preview_grid.model_dump(mode='json')['grid_layout'] == 'preview'
    assert fingerprint(preview_grid) != fingerprint(full_grid)
    assert Overlay.model_validate(preview_grid.model_dump(mode='json')).model_dump(mode='json') == preview_grid.model_dump(mode='json')

    phone = Overlay(kind='pictogram', icon='phone', start_frame=0, end_frame=30)
    eye = Overlay(kind='pictogram', icon='eye', start_frame=0, end_frame=30)
    assert phone.model_dump(mode='json')['icon'] == 'phone'
    assert fingerprint(phone) != fingerprint(eye)

    timer = Overlay(kind='timer', text='00:40', value_from=40, start_frame=0, end_frame=60)
    running = Overlay.model_validate({**timer.model_dump(mode='json'), 'clock_start_frame': 120})
    assert running.model_dump(mode='json')['clock_start_frame'] == 120
    assert fingerprint(running) != fingerprint(timer)
    assert Overlay.model_validate(running.model_dump(mode='json')).model_dump(mode='json') == running.model_dump(mode='json')


def test_preview_fixation_geometry_and_lineage_follow_the_preview_grid():
    preview_grid = Overlay(
        kind='data_grid', preset='schulte_6x6', grid_layout='preview',
        start_frame=0, end_frame=30,
    )
    fixation = Overlay(
        kind='fixation_cue', grid_layout=preview_grid.grid_layout,
        start_frame=0, end_frame=30,
    )

    assert preview_grid.x <= fixation.x
    assert preview_grid.y <= fixation.y
    assert fixation.x + fixation.width <= preview_grid.x + preview_grid.width
    assert fixation.y + fixation.height <= preview_grid.y + preview_grid.height
    assert fixation.model_dump(mode='json')['grid_layout'] == 'preview'

    full_fixation = Overlay(kind='fixation_cue', start_frame=0, end_frame=30)
    assert 'grid_layout' not in full_fixation.model_dump(mode='json')
