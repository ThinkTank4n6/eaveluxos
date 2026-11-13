# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""Which certificate authorities to trust for the app's outgoing HTTPS
(Trimlight's cloud, the weather service, place search).

Python normally borrows the operating system's list. The Mac app bundles its
own OpenSSL, which looks for that list in a folder that doesn't exist inside
the app, so on a Mac it trusted nothing and every connection failed with
"CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate". This
adds two more sources: certifi (Mozilla's list, bundled with the app) and, on
a Mac, the list macOS itself ships. The system's own list still counts, so a
certificate the computer trusts (a home or work network's) keeps working.
"""
import functools
import os
import platform
import ssl

MAC_SYSTEM_BUNDLE = "/etc/ssl/cert.pem"

CERT_HELP = ("This computer couldn't confirm it's really connected to {who}: the secure "
             "connection's certificate check failed. This isn't a problem with your keys. Check that "
             "this computer's date and time are right, and whether antivirus or network filtering "
             "software checks secure connections.")


def _extra_bundles() -> list[str]:
    out = []
    try:
        import certifi
        out.append(certifi.where())
    except ImportError:
        pass
    if platform.system() == "Darwin" and os.path.exists(MAC_SYSTEM_BUNDLE):
        out.append(MAC_SYSTEM_BUNDLE)
    return out


@functools.lru_cache(maxsize=1)
def client_context() -> ssl.SSLContext:
    """One shared, verifying context (hostname and certificate checks stay on)."""
    ctx = ssl.create_default_context()
    for path in _extra_bundles():
        try:
            ctx.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError):
            pass   # a damaged extra list mustn't break the ones that work
    return ctx


def is_cert_failure(err) -> bool:
    """A urllib error caused by the server's certificate not checking out."""
    return isinstance(getattr(err, "reason", err), ssl.SSLCertVerificationError)
