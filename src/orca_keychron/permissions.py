from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionStatus:
    accessibility: bool
    input_monitoring: bool


def macos_permission_status(request: bool = False) -> PermissionStatus | None:
    if sys.platform != "darwin":
        return None

    try:
        import ApplicationServices
    except ImportError:
        accessibility = False
    else:
        accessibility = bool(ApplicationServices.AXIsProcessTrusted())
        if request and not accessibility:
            options = {ApplicationServices.kAXTrustedCheckOptionPrompt: True}
            accessibility = bool(
                ApplicationServices.AXIsProcessTrustedWithOptions(options)
            )

    try:
        import Quartz
    except ImportError:
        input_monitoring = False
    else:
        input_monitoring = bool(Quartz.CGPreflightListenEventAccess())
        if request and not input_monitoring:
            input_monitoring = bool(Quartz.CGRequestListenEventAccess())

    return PermissionStatus(
        accessibility=accessibility,
        input_monitoring=input_monitoring,
    )
