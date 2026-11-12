"""User-run Notebook only: no server, tunnel, Drive mount, polling or OAuth."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from colab.sorigul_colab_bootstrap import COLAB_MODEL, select_runtime_identity, transcribe_model
from src.services.notebook_bundle import build_archive, source_identity


def load_model(torch_module, model_factory):
    identity = select_runtime_identity(torch_module)
    if identity.device != "cuda":
        raise RuntimeError("무료 GPU를 사용할 수 없습니다. 유료로 전환하지 말고 중단하세요.")
    model = model_factory(COLAB_MODEL, device=identity.device, compute_type=identity.compute_type)
    if (model.model.device, model.model.compute_type) != (identity.device, identity.compute_type):
        raise RuntimeError("실제 모델의 device/compute_type이 요청한 설정과 다릅니다.")
    return model, identity


def transcribe_once(source, model, identity, output):
    source = Path(source)
    output = Path(output)
    if output.exists():
        raise FileExistsError("기존 결과 ZIP이 있어 추론을 다시 실행하지 않습니다.")
    before = source_identity(source)  # Bind results to the audio actually inferred.
    payload = transcribe_model(model, str(source))
    runtime = {key: value for key, value in identity.health_payload().items() if key != "status"}
    data = build_archive(source, payload, runtime, expected_identity=before)
    with output.open("xb") as handle:
        handle.write(data)
    return payload, runtime
