"""Build the pinned, already downloaded Whisper checkout and causal probe."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.cache/whisper.cpp'
COMMIT = 'd1be6fde11ac6e0407606b4e42fe72d34add8037'
actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
if actual != COMMIT:
    raise SystemExit('Expected whisper.cpp v1.9.5 commit ' + COMMIT)
subprocess.run(['cmake', '-S', str(SOURCE), '-B', str(SOURCE/'build'),
                '-DCMAKE_BUILD_TYPE=Release', '-DWHISPER_BUILD_TESTS=OFF',
                '-DWHISPER_BUILD_EXAMPLES=ON', '-DGGML_METAL=ON', '-DGGML_CCACHE=OFF'], check=True)
subprocess.run(['cmake', '--build', str(SOURCE/'build'), '--target', 'whisper-cli', '-j', '4'], check=True)
(ROOT/'.build').mkdir(exist_ok=True)
subprocess.run(['clang++', '-O2', '-std=c++17', '-I', str(SOURCE/'include'),
                '-I', str(SOURCE/'ggml/include'), str(ROOT/'spikes/native/local_stream.cpp'),
                '-L', str(SOURCE/'build/bin'), '-lwhisper',
                '-Wl,-rpath,' + str(SOURCE/'build/bin'), '-o', str(ROOT/'.build/whisper-replay')], check=True)
subprocess.run(['clang++', '-O2', '-std=c++17', '-I', str(SOURCE/'include'),
                '-I', str(SOURCE/'ggml/include'), str(ROOT/'spikes/native/stream_worker.cpp'),
                '-L', str(SOURCE/'build/bin'), '-lwhisper',
                '-Wl,-rpath,' + str(SOURCE/'build/bin'), '-o', str(ROOT/'.build/whisper-stream')], check=True)
subprocess.run(['clang++', '-O2', '-std=c++17', '-I', str(SOURCE/'include'),
                '-I', str(SOURCE/'ggml/include'), str(ROOT/'spikes/native/stream_worker_v2.cpp'),
                '-L', str(SOURCE/'build/bin'), '-lwhisper',
                '-Wl,-rpath,' + str(SOURCE/'build/bin'), '-o', str(ROOT/'.build/whisper-stream-v2')], check=True)
