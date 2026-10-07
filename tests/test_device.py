from __future__ import annotations

import pytest
import torch

from agridrone.core import device as device_mod
from agridrone.core.device import (
    DeviceUnavailableError,
    describe_device,
    resolve_device,
    to_ultralytics_device,
)


@pytest.fixture
def no_accelerator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(device_mod, "mps_available", lambda: False)


@pytest.mark.usefixtures("no_accelerator")
def test_auto_falls_back_to_cpu() -> None:
    assert resolve_device("auto") == torch.device("cpu")
    assert resolve_device(" CPU ") == torch.device("cpu")


def test_auto_prefers_mps_when_no_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(device_mod, "mps_available", lambda: True)
    assert resolve_device("auto") == torch.device("mps")


def test_auto_prefers_cuda(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(device_mod, "mps_available", lambda: True)
    assert resolve_device("auto") == torch.device("cuda", 0)


@pytest.mark.usefixtures("no_accelerator")
@pytest.mark.parametrize("request_", ["cuda", "cuda:0", "mps"])
def test_explicit_unavailable_device_raises(request_: str) -> None:
    with pytest.raises(DeviceUnavailableError):
        resolve_device(request_)


def test_cuda_index_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(torch.cuda, "device_count", lambda: 1)
    assert resolve_device("cuda") == torch.device("cuda", 0)
    with pytest.raises(DeviceUnavailableError, match="1 GPU"):
        resolve_device("cuda:3")


@pytest.mark.parametrize("bad", ["gpu", "tpu", ""])
def test_unknown_device_string(bad: str) -> None:
    with pytest.raises(ValueError, match="Device inconnu"):
        resolve_device(bad)


def test_ultralytics_device_strings() -> None:
    assert to_ultralytics_device(torch.device("cuda", 1)) == "1"
    assert to_ultralytics_device(torch.device("cuda")) == "0"
    assert to_ultralytics_device(torch.device("mps")) == "mps"
    assert to_ultralytics_device(torch.device("cpu")) == "cpu"


def test_describe_cpu_device() -> None:
    info = describe_device(torch.device("cpu"))
    assert info["device"] == "cpu"
    assert info["torch"] == torch.__version__
