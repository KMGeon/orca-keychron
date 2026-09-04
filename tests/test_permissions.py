import sys
from types import SimpleNamespace

from orca_keychron import permissions


def test_permission_status_is_not_applicable_outside_macos(monkeypatch):
    monkeypatch.setattr(permissions.sys, "platform", "linux")

    assert permissions.macos_permission_status() is None


def test_permission_status_requests_missing_macos_permissions(monkeypatch):
    application_services = SimpleNamespace(
        kAXTrustedCheckOptionPrompt="prompt",
        AXIsProcessTrusted=lambda: False,
        AXIsProcessTrustedWithOptions=lambda options: options == {"prompt": True},
    )
    quartz = SimpleNamespace(
        CGPreflightListenEventAccess=lambda: False,
        CGRequestListenEventAccess=lambda: True,
    )
    monkeypatch.setattr(permissions.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "ApplicationServices", application_services)
    monkeypatch.setitem(sys.modules, "Quartz", quartz)

    assert permissions.macos_permission_status(request=True) == permissions.PermissionStatus(
        accessibility=True,
        input_monitoring=True,
    )


def test_permission_status_reports_frameworks_independently(monkeypatch):
    application_services = SimpleNamespace(
        AXIsProcessTrusted=lambda: True,
    )
    monkeypatch.setattr(permissions.sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "ApplicationServices", application_services)
    monkeypatch.setitem(sys.modules, "Quartz", None)

    assert permissions.macos_permission_status() == permissions.PermissionStatus(
        accessibility=True,
        input_monitoring=False,
    )
