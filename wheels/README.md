# Vendored wheels

`requirements.txt` installs the Spinnaker SDK from a wheel in this folder.
The wheel is **not** tracked in git — each person must place it here manually
before installing.

## Setup

1. Obtain `spinnaker_python-4.3.0.190-cp310-cp310-win_amd64.whl`
   (from the FLIR/Teledyne Spinnaker SDK download).
2. Copy it into this `wheels/` folder.
3. From the repo root, run:

   ```
   pip install -r requirements.txt
   ```

## Requirements

The wheel is platform-specific: **Windows 64-bit, Python 3.10** (`cp310`,
`win_amd64`). It will not install on other Python versions or operating systems.
