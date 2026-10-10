"""Build an ad-hoc signed macOS diagnostic app using the installed Apple SDK."""

from pathlib import Path
import os
import plistlib
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / '.build'
APP = BUILD / 'CrackitProbe.app'
CONTENTS = APP / 'Contents'
(CONTENTS / 'MacOS').mkdir(parents=True, exist_ok=True)
(BUILD / 'module-cache').mkdir(parents=True, exist_ok=True)
info = {
    'CFBundleExecutable': 'CrackitProbe',
    'CFBundleIdentifier': 'dev.crackit.feasibility-probe',
    'CFBundleName': 'Crackit Probe',
    'CFBundleDisplayName': 'Crackit Probe',
    'CFBundlePackageType': 'APPL',
    'CFBundleShortVersionString': '0.1.0',
    'CFBundleVersion': '1',
    'LSMinimumSystemVersion': '15.0',
    'NSMicrophoneUsageDescription': 'Capture microphone audio only after you explicitly start a diagnostic; live transcription is local, and raw audio is not saved or uploaded.',
    'NSHighResolutionCapable': True,
}
with (CONTENTS / 'Info.plist').open('wb') as f:
    plistlib.dump(info, f)
subprocess.run([
    'xcrun', 'swiftc', '-swift-version', '5', '-parse-as-library', '-O',
    '-module-cache-path', str(BUILD / 'module-cache'),
    '-target', 'arm64-apple-macosx15.0',
    str(ROOT / 'spikes/native/Probe.swift'),
    str(ROOT / 'spikes/native/LiveFrames.swift'),
    '-o', str(CONTENTS / 'MacOS/CrackitProbe'),
], check=True, cwd=ROOT)
identity = os.environ.get('CRACKIT_CODESIGN_IDENTITY', '-').strip() or '-'
subprocess.run(['codesign', '--force', '--sign', identity, str(APP)], check=True)
print(str(APP))
if identity == '-':
    print('Ad-hoc development signature: each rebuild can invalidate macOS capture permissions.')
    print('Set CRACKIT_CODESIGN_IDENTITY to a stable Apple Development identity when available.')
else:
    print('Signed with configured development identity; this diagnostic is not notarized.')
print('Capture starts only from explicit app controls or --live-frames.')
