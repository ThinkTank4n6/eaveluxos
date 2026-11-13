# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Christopher A. Tankelewicz (ThinkTank4n6)
"""`python3 main.py make-cert`: a self-signed HTTPS certificate for the app.

The app already serves HTTPS when data/tls/cert.pem and key.pem exist. This
makes them, valid for this computer's names and home-network addresses, so the
app password and session token aren't sent in clear text over Wi-Fi.

Browsers warn about a self-signed certificate the first time ("not private").
That's expected on a home network; accept it once per device. For no warning
at all, use a certificate from mkcert or your own CA instead.
"""
import datetime
import ipaddress
import os
import socket
from pathlib import Path


def make_cert(tls_dir: Path, extra_names=(), addresses=(), force=False) -> Path:
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    except ImportError:
        raise RuntimeError("make-cert needs the \"cryptography\" package: python3 -m pip install cryptography") from None
    cert_path, key_path = tls_dir / "cert.pem", tls_dir / "key.pem"
    if cert_path.exists() and not force:
        raise RuntimeError(f"{cert_path} already exists. Add --force to replace it.")
    host = socket.gethostname().split(".")[0].lower()
    names = ["localhost", host, f"{host}.local", f"{host}.lan", f"{host}.home.arpa", *extra_names]
    ips = {"127.0.0.1", "::1", *addresses}
    san = [x509.DNSName(n) for n in dict.fromkeys(n for n in names if n)]
    san += [x509.IPAddress(ipaddress.ip_address(a)) for a in sorted(ips)]
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"EaveLuxOS on {host}")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=825))     # the longest Apple devices accept
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    tls_dir.mkdir(parents=True, exist_ok=True)
    # Both files are written in full first, then swapped in, so a failure
    # can't leave a key next to a certificate it doesn't match. The key's
    # temporary file is always new (O_EXCL), so it's private from the start:
    # reusing a leftover one would have kept that file's looser permissions.
    key_tmp, cert_tmp = key_path.with_suffix(".tmp"), cert_path.with_suffix(".tmp")
    for t in (key_tmp, cert_tmp):
        t.unlink(missing_ok=True)
    fd = os.open(key_tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    cert_tmp.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.replace(key_tmp, key_path)
    os.replace(cert_tmp, cert_path)
    return cert_path
