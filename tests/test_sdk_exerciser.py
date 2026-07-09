"""Tests for tools.sdk_exerciser."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import sdk_exerciser


def test_selected_keys_defaults_to_first_key():
    args = SimpleNamespace(all_keys=False, key=None)
    assert sdk_exerciser.selected_keys(args) == [1]


def test_selected_keys_all_keys():
    args = SimpleNamespace(all_keys=True, key=[3])
    assert sdk_exerciser.selected_keys(args) == list(range(1, 11))


def test_selected_keys_rejects_out_of_range():
    args = SimpleNamespace(all_keys=False, key=[0, 11])
    with pytest.raises(ValueError, match="1-10"):
        sdk_exerciser.selected_keys(args)


def test_build_csc_command_uses_x86_platform():
    cmd = sdk_exerciser.build_csc_command(
        Path("csc.exe"),
        Path("SdkExerciser.cs"),
        Path("SdkExerciser.exe"),
    )

    assert "/platform:x86" in cmd
    assert "/out:SdkExerciser.exe" in cmd


def test_build_exerciser_args_uses_dash_without_touchpad():
    args = sdk_exerciser.build_exerciser_args(
        Path(r"C:\SDK"),
        12,
        None,
        [(1, Path("one.png")), (10, Path("ten.png"))],
    )

    assert args == [r"C:\SDK", "12", "-", "1", "one.png", "10", "ten.png"]
