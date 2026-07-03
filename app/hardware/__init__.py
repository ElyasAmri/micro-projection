"""Real-hardware drivers for the rig: the projector (used as a second screen)
and the camera (FLIR/Spinnaker, with USB and synthetic fallbacks), plus the
project-and-grab capture worker that ties them together.

Nothing here is imported at app startup -- the `HardwareBackend` pulls these in
lazily -- so the app runs unchanged on a machine without the Spinnaker SDK or a
projector attached.
"""
