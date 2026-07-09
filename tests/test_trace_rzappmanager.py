"""Tests for the optional Frida trace formatter."""

from tools import trace_rzappmanager


def test_format_event_writefile_includes_length_path_and_hex():
    line = trace_rzappmanager.format_event(
        {
            "type": "WriteFile",
            "length": 12,
            "path": r"\\?\usb#vid_1532&pid_0114\2",
            "hex": "00 01",
        }
    )

    assert line == r"WriteFile len=12 path=\\?\usb#vid_1532&pid_0114\2 hex=00 01"


def test_format_event_createfile_formats_access_as_hex():
    line = trace_rzappmanager.format_event(
        {
            "type": "CreateFileW",
            "handle": "0x624",
            "access": 0xC0000000,
            "path": "device",
        }
    )

    assert line == "CreateFileW handle=0x624 access=0xc0000000 path=device"
