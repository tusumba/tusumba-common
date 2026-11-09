"""Хелперы для разработки и тестов: тестовая пара ключей и выпуск токенов."""
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate_keypair() -> tuple[str, str]:
    """Возвращает (private_pem, public_pem)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private, public


def make_token(private_pem: str, user_id: str = "1", roles: list[str] | None = None,
               expires_in: int = 3600, typ: str = "access") -> str:
    now = int(time.time())
    return jwt.encode(
        {"sub": user_id, "roles": roles or [], "typ": typ, "iat": now, "exp": now + expires_in},
        private_pem, algorithm="RS256",
    )


def main() -> None:
    """python -m tusumba_common.testing [каталог] — пишет private.pem и public.pem."""
    import sys
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dev-keys")
    out.mkdir(parents=True, exist_ok=True)
    private, public = generate_keypair()
    (out / "private.pem").write_text(private)
    (out / "public.pem").write_text(public)
    print(f"Ключи записаны в {out}/ (только для разработки)")


if __name__ == "__main__":
    main()
