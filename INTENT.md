# EyeGlow EgoBody — Project Intent

## Deadline

The features in this document constitute the initial MVP targeted for completion before Tuesday, September 22, 2026.

## Purpose

Build a Python desktop application that uses EgoBody recordings to visualize and quantify whether two interacting people could have seen forward light leakage—EyeGlow—from one another’s smart glasses.

Both participants wear identical simulated smart glasses. The application plays their recorded movement in a third-person 3D view, attaches EyeGlow leakage frustums to their glasses, evaluates potential visibility in both directions, displays visibility events over time, and reports the percentage of the interaction during which each participant could have seen the other’s EyeGlow.

The MVP is a geometric visualization and analysis tool. It is not a calibrated optical or human-perception model.

## Core Experience

The user will:

1. Launch the application.
2. Select an EgoBody recording.
3. See both participants animated in a shared 3D space.
4. See identical generic smart-glasses frames on both participants.
5. See one or two EyeGlow frustums attached to each pair of glasses.
6. Adjust the shared EyeGlow parameters.
7. See when either participant could have seen the other’s EyeGlow.
8. Review visibility events on a synchronized timeline.
9. Read the percentage of the recording during which EyeGlow could have been seen.
10. Export a still image or shareable animation.

## Meaning of “Could Have Seen”

The MVP estimates opportunity for visibility, not actual gaze or conscious perception.

A participant could have seen the other participant’s EyeGlow when:

1. One or both of their eye-socket positions are inside an active EyeGlow frustum.
2. Their head is oriented sufficiently toward the emitting glasses.
3. They are within the configured maximum analysis distance.
4. The required body-pose data are valid.

The MVP will not consider:

- Eye-gaze direction.
- Eye rotations.
- Fixation.
- Blinking.
- Eyelid state.
- Attention.
- Conscious detection.
- Display readability.

This definition deliberately answers:

> Based on the relative positions and head orientations of the participants, was the EyeGlow geometrically available to be seen?

## Participants and Glasses

Both participants always wear identical simulated smart glasses.

One shared parameter set controls both pairs of glasses. The MVP will not support different optical configurations for the two participants.

The generic glasses frames will:

- Be locked to each participant’s head.
- Move and rotate with the head on every frame.
- Have a fixed visual pantoscopic tilt of 5°.
- Include a recognizable frame, bridge, and lenses.
- Include visible rectangular outcoupling waveguides.
- Provide visual context without representing a specific commercial product.

The fixed pantoscopic tilt of the rendered frames does not directly control EyeGlow direction. Effective vertical emission direction is controlled by chief-ray pitch.

## Monocular and Binocular Modes

The shared glasses configuration can be:

- Monocular left.
- Monocular right.
- Binocular.

A monocular configuration produces one active outcoupling waveguide and one EyeGlow frustum per participant.

A binocular configuration produces two active waveguides and two independently evaluated EyeGlow frustums per participant.

## Outcoupling Waveguide

Each active display has a rectangular outcoupling-waveguide area positioned in the corresponding lens.

The waveguide rectangle defines the narrow base of its EyeGlow frustum.

Its physical dimensions are controlled by:

- Outcoupling width.
- Outcoupling height.

The rectangle will:

- Be positioned and oriented with the glasses.
- Move with the participant’s head.
- Act as the geometric near plane of the frustum.
- Appear white when the third-person render camera is inside its frustum.
- Appear dark or transparent when the render camera is outside its frustum.
- Respond independently for the left and right displays.

The MVP will not add bloom, halos, glare, or other cosmetic optical effects.

## Chief Ray

Each EyeGlow frustum has a chief ray.

The chief ray:

- Originates at the center of the outcoupling-waveguide rectangle.
- Defines the central direction of the leakage volume.
- Has a configurable pitch.
- Has a configurable yaw.
- Extends to the configured maximum analysis distance.

Conceptually:

```text
far-plane center
       ●
      ╱
     ╱ chief ray
    ╱
┌──●──┐
│     │  outcoupling-waveguide rectangle
└─────┘
```

The far-plane center is:

```text
far_center =
    waveguide_center
    + chief_ray_direction × maximum_distance
```

Chief-ray pitch represents the effective vertical emission direction produced by the combined optical and mechanical design. Pantoscopic tilt will not be exposed as a separate interactive control.

A diagnostic option will show the chief ray as a line.

## EyeGlow Frustum Geometry

Each EyeGlow volume is a rectangular frustum rather than a point-origin cone.

It is defined by:

- The outcoupling-waveguide rectangle as its narrow base.
- The chief ray as its central axis.
- Horizontal leakage field of view.
- Vertical leakage field of view.
- Maximum analysis distance.

The frustum expands outward from the four corners of the waveguide rectangle around the chief ray.

The translucent frustum geometry will be toggleable:

- Frustums on: inspect and explain the geometry.
- Frustums off: observe EyeGlow by moving the render camera and watching the waveguide rectangles appear white.

## Shared Optical Controls

One control panel affects both pairs of glasses identically.

The MVP controls are:

- Monocular left, monocular right, or binocular.
- Outcoupling-waveguide width.
- Outcoupling-waveguide height.
- Horizontal leakage field of view.
- Vertical leakage field of view.
- Chief-ray pitch.
- Chief-ray yaw.
- Maximum analysis distance.
- Head-facing-angle threshold.
- Frustum opacity.
- Show or hide frustums.
- Show or hide chief rays.
- Reset to default settings.

Changes should update the geometry, rendering, visibility timeline, and scores without reloading the recording.

## Bidirectional Visibility

Potential visibility is evaluated independently in both directions:

```text
Participant A’s EyeGlow → Participant B
Participant B’s EyeGlow → Participant A
```

The application will evaluate these geometric combinations:

- A’s left waveguide frustum contains B’s left eye socket.
- A’s left waveguide frustum contains B’s right eye socket.
- A’s right waveguide frustum contains B’s left eye socket.
- A’s right waveguide frustum contains B’s right eye socket.
- B’s left waveguide frustum contains A’s left eye socket.
- B’s left waveguide frustum contains A’s right eye socket.
- B’s right waveguide frustum contains A’s left eye socket.
- B’s right waveguide frustum contains A’s right eye socket.

Only active waveguides are evaluated.

A positional intersection counts as potential visibility only when the receiving participant’s head is also oriented sufficiently toward the emitting participant’s glasses.

## Head-Orientation Test

The receiving participant’s head-forward direction will be compared with the direction from the receiving head to the emitting glasses.

Conceptually:

```text
receiving head-forward direction
                compared with
direction from receiver to emitting glasses
```

If the angle between those directions is within the configured head-facing-angle threshold, the directional test passes.

The test uses head orientation only.

It does not use eye rotations, measured gaze, inferred gaze, blinking, or eyelid state.

## Participant Visibility States

Each participant will have one of these states:

- EyeGlow not potentially visible.
- Potentially visible to the left eye socket only.
- Potentially visible to the right eye socket only.
- Potentially visible to both eye sockets.

The state indicates geometric opportunity, not actual perception.

## Participant Visibility Indicators

Each participant will have an indicator above their head.

The indicator describes what that participant could currently see:

- Marker above A: A could see B’s EyeGlow.
- Marker above B: B could see A’s EyeGlow.

Suggested presentation:

- Hidden or gray: not potentially visible.
- Yellow: potentially visible to one eye socket.
- Red: potentially visible to both eye sockets.

The indicator may contain left, right, or both-eye symbols.

## Render-Camera EyeGlow

The third-person render camera acts as an additional, non-scored observer.

For every rendered frame, the application will test whether the camera position is inside each active EyeGlow frustum.

When the camera is inside a frustum:

- The corresponding outcoupling-waveguide rectangle appears white.

When the camera is outside a frustum:

- The corresponding rectangle appears dark or transparent.

Left and right waveguides respond independently.

The render camera does not require a head-orientation test. Normal rendering already determines whether the glasses are in view.

Render-camera visibility does not affect participant visibility scores or timelines.

## Visibility Timeline

A synchronized visibility timeline will appear below the 3D viewport.

It will contain at least two lanes:

```text
Time ───────────────────────────────────────────▶

A could see B:  ─────████████────██────────████─
B could see A:  ─────────████────────██████─────
```

The timeline will:

- Remain synchronized with playback.
- Show potentially visible and invisible periods.
- Distinguish one-eye and two-eye-socket visibility if practical.
- Display the current playhead.
- Allow scrubbing or clicking to jump to another moment.
- Recalculate when optical parameters change.

## Per-Recording Scores

The principal scores are:

```text
A could see B percentage =
time A met the geometric visibility conditions
─────────────────────────────────────────────── × 100
             total time with valid data
```

```text
B could see A percentage =
time B met the geometric visibility conditions
─────────────────────────────────────────────── × 100
             total time with valid data
```

The recording summary will report:

- Percentage of time A could have seen B’s EyeGlow.
- Percentage of time B could have seen A’s EyeGlow.
- Percentage of time EyeGlow could have been seen in either direction.
- Percentage of time both participants could have seen one another’s EyeGlow simultaneously.
- Percentage of one-eye-socket visibility.
- Percentage of two-eye-socket visibility.
- Longest continuous potential-visibility event.
- Number of distinct potential-visibility events.

If frame timing is uniform, frame percentages may be used. If timestamps are irregular, scores should use elapsed duration.

Results will be labeled as potential visibility or could-have-seen percentages.

## Dataset Browser

The application will discover EgoBody recordings for which both participants have matching motion data.

The recording selector will show available information such as:

- Recording name.
- Dataset split.
- Participant identifiers.
- Scene name when available.
- Frame range.
- Number of paired frames.
- Cache status.

Unpaired or invalid frames will be excluded from scoring.

## Motion Playback

Both participants will be animated synchronously.

Playback controls will include:

- Play and pause.
- Timeline scrubbing.
- Step forward one frame.
- Step backward one frame.
- Playback speed.
- Loop on or off.
- Current frame display.
- Total frame count.
- Reset to the beginning.

The viewer should remain responsive after a recording has loaded.

## Participant Representation

The baseline representation will use:

- Point-light figures, or
- Connected stick-figure skeletons.

The participants will use distinct colors and labels.

Full SMPL-X body meshes may be added if the licensed body-model files become available and mesh support does not threaten the MVP deadline. Skeleton playback remains an acceptable MVP result.

## Shared Coordinate System

Both participants must appear in the same physically plausible coordinate system.

The implementation will:

- Match the same recording and frame numbers.
- Test whether wearer and interactee fits already share master-Kinect coordinates.
- Avoid applying transformations twice.
- Use EgoBody transformations only where required.
- Keep distances and dimensions in consistent physical units.
- Validate relative position, orientation, and floor height.

Validation will check:

- Whether the participants face and approach one another plausibly.
- Whether interaction and contact moments align.
- Whether body heights and separation are reasonable.
- Whether either participant is mirrored or incorrectly rotated.

## Head, Eye-Socket, and Glasses Placement

The application will derive or approximate:

- Head position.
- Head orientation.
- Head-forward direction.
- Left eye-socket position.
- Right eye-socket position.
- Glasses coordinate frame.
- Left waveguide position.
- Right waveguide position.

The eye sockets are geometric sample points used for frustum-containment testing. They are not treated as measured gaze origins or viewing directions.

If precise eye-socket positions cannot be reconstructed initially, documented head-relative offsets may be used. Approximated values must not be presented as measured data.

## Third-Person Camera

Only third-person viewing is required for the MVP.

Camera controls will include:

- Orbit.
- Pan.
- Zoom.
- Reset.
- Fit both participants in view.
- Front view.
- Side view.
- Top view.

First-person, eye, cyclopean, and anaglyph cameras are deferred.

## Application Layout

The provisional application layout is:

```text
┌────────────────────────────────┬───────────────────────┐
│                                │ Recording             │
│                                │ Playback settings     │
│      Third-person 3D view      │ Glasses parameters    │
│                                │ Current visibility    │
│                                │ Recording scores      │
├────────────────────────────────┴───────────────────────┤
│ A could see B timeline                                 │
│ B could see A timeline                                 │
│ Playback controls and playhead                         │
└────────────────────────────────────────────────────────┘
```

Clarity and functionality take priority over visual polish.

## Export

The target MVP will provide:

- Screenshot export.
- Export of the third-person animation.
- EyeGlow frustums when enabled.
- White waveguide rectangles when visible to the render camera.
- Participant visibility indicators.
- Recording name.
- Selected optical settings.
- Current visibility status or timeline.

Preferred animation output is MP4.

If direct MP4 encoding is not ready by the deadline, exporting numbered image frames for conversion with FFmpeg is acceptable.

## Caching and Dataset Protection

`egobody-data` is strictly read-only.

The application must not create, modify, rename, move, or delete anything inside that directory.

Derived data will be stored in `code-repo`, including:

- Dataset indexes.
- Converted joint sequences.
- Playback caches.
- Visibility caches.
- Logs.
- Screenshots.
- Exported animations.

The application should preprocess recordings into compact arrays rather than repeatedly opening thousands of individual pickle files during playback.

## Diagnostics

A debug mode will show:

- World axes.
- Ground plane.
- Skeleton joints.
- Head-forward directions.
- Eye-socket positions.
- Head-facing-angle test.
- Glasses coordinate frames.
- Waveguide rectangles.
- Chief rays.
- Frustum boundaries.
- Eye-socket/frustum containment results.
- Render-camera/frustum containment results.
- Frame number.
- Transformation information.

Diagnostic overlays may be hidden during presentations and exports.

## Explicitly Deferred

The following are outside the pre-Tuesday MVP:

- Eye-gaze vectors.
- HoloLens gaze integration.
- SMPL-X eye-rotation analysis.
- Fixation analysis.
- Blinking and eyelid state.
- Attention estimation.
- First-person camera views.
- Left-eye, right-eye, and cyclopean rendering.
- Red/cyan anaglyph.
- RGB or depth backgrounds.
- Kinect video overlays.
- Scene meshes and environmental occlusion.
- Photorealistic body rendering.
- Clothing.
- Different glasses configurations for A and B.
- Adjustable rendered-frame pantoscopic tilt.
- Bloom, halos, glare, or lens flare.
- Physically calibrated brightness.
- Measured angular-intensity distributions.
- Readability prediction.
- Conscious-detection prediction.
- Detailed eyebox-expander optics.
- Facial occlusion by glasses or lenses.
- Polished Windows, macOS, and Linux installers.
- Code signing and automatic updates.

## Acceptance Criteria

The MVP is complete when a reviewer can:

1. Launch the Python application.
2. Select a paired EgoBody recording.
3. See both participants moving synchronously.
4. Navigate the scene in third person.
5. Play, pause, scrub, loop, and step through frames.
6. See identical generic glasses on both participants.
7. See the fixed 5° pantoscopic tilt of the rendered frames.
8. Switch between monocular-left, monocular-right, and binocular modes.
9. Adjust waveguide dimensions, leakage FOV, chief-ray pitch, chief-ray yaw, and maximum distance.
10. See the head-locked frustums and chief rays update immediately.
11. Move the render camera into a frustum and see its waveguide rectangle become white.
12. Move the render camera outside the frustum and see the rectangle become dark or transparent.
13. See left and right waveguides respond independently.
14. See a marker above A when A could see B’s EyeGlow.
15. See a marker above B when B could see A’s EyeGlow.
16. See both potential-visibility histories on the synchronized timeline.
17. Read the could-have-seen percentage for each direction.
18. Identify periods of simultaneous mutual visibility.
19. Export a still image and a shareable animation or frame sequence.
20. Complete all of the above without modifying `egobody-data`.

## Guiding Statement

The MVP plays two recorded EgoBody participants in a third-person 3D scene. Both wear identical generic smart glasses with rectangular outcoupling waveguides. Each active waveguide forms the narrow base of a head-locked EyeGlow frustum centered on a configurable chief ray.

The application determines when either participant’s eye-socket positions fall inside the other participant’s frustums while their head is oriented sufficiently toward the emitting glasses. It visualizes those opportunities above the participants and on a synchronized timeline, then reports the percentage of the interaction during which each participant could have seen the other’s EyeGlow.

When the user’s third-person camera enters a frustum, the corresponding outcoupling-waveguide rectangle appears white.
